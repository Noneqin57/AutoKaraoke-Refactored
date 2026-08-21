# -*- coding: utf-8 -*-
import os
import re
import gc
import torch
import traceback
import time
import stable_whisper
from multiprocessing import Queue, Event


from core.lrc_parser import LrcParser
from core.lrc_aligner_v2 import LrcAligner
from core.ctc_aligner import CTCAligner
from core.vocal_separator import VocalSeparator

from config import DEFAULT_VOCAL_MODEL
from utils.logger_v2 import setup_logger

from core.worker_types import WorkerArgs
def get_attr(obj, key, default=None):
    if isinstance(obj, dict): return obj.get(key, default)
    return getattr(obj, key, default)

def preprocess_cjk_spaces(text):
    if not text: return text
    pattern = r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff])'
    spaced = re.sub(pattern, r' \1 ', text)
    return re.sub(r'\s+', ' ', spaced).strip()

class ModelCache:
    """模型缓存管理类，封装全局模型状态"""
    
    def __init__(self):
        self.model = None
        self.model_size = None
        self.logger = setup_logger("ModelCache")
    
    def get(self):
        """获取缓存的模型"""
        return self.model, self.model_size
    
    def set(self, model, model_size):
        """设置缓存的模型"""
        if model is None:
            return
        self.model = model
        self.model_size = model_size
        self.logger.info(f"Model cached: {model_size}")
    
    def clear(self, force=True):
        """清理显存并重置缓存"""
        if not force:
            return
        
        try:
            if self.model:
                if hasattr(self.model, 'to'):
                    self.model.to("cpu")
                del self.model
        except (AttributeError, RuntimeError) as e:
            self.logger.debug(f"Expected error during VRAM cleanup: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during VRAM cleanup: {e}")
        
        self.model = None
        self.model_size = None
        
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def is_cached(self, model_size):
        """检查指定模型是否已缓存"""
        return self.model is not None and self.model_size == model_size


# 全局模型缓存实例
_model_cache = ModelCache()

def daemon_worker(input_queue: Queue, result_queue: Queue, progress_queue: Queue, stop_event: Event):
    """常驻后台的工作进程，监听任务队列并执行"""
    global _model_cache
    
    # 初始化日志
    logger = setup_logger("WorkerDaemon")
    logger.info("Daemon worker process started, waiting for tasks...")
    
    while True:
        try:
            task = input_queue.get()
            
            if task == "EXIT":
                logger.info("Received EXIT signal. Shutting down daemon.")
                _model_cache.clear(force=True)
                break
                
            if isinstance(task, WorkerArgs):
                logger.info("Received new task.")
                stop_event.clear()
                
                # 执行任务
                run_inference_task(task, result_queue, progress_queue, stop_event)
                
                # 任务结束后进行轻量级清理，但保留模型
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    
        except Exception as e:
            logger.error(f"Daemon loop error: {traceback.format_exc()}")
            # 防止死循环，稍作休眠
            # time 已在模块顶部导入
            time.sleep(1)

def run_inference_task(args: WorkerArgs, result_queue: Queue, progress_queue: Queue, stop_event: Event):
    """执行单次推理任务"""
    global _model_cache
    
    logger = setup_logger("Worker")
    
    # 解包参数
    audio_path = args.audio_path
    model_size = args.model_size
    language = args.language
    ref_text = args.ref_text
    lrc_parser_data = args.lrc_parser_data
    time_offset = args.time_offset
    initial_prompt_input = args.initial_prompt_input
    model_dir = args.model_dir or os.path.join(os.getcwd(), "models")
    release_vram_flag = args.release_vram

    try:
        logger.info(f"Worker started. Audio: {audio_path}, Model: {model_size}")
        
        # 恢复解析器状态
        parser = LrcParser()
        parser.headers = lrc_parser_data.get('headers', [])
        parser.lines_text = lrc_parser_data.get('lines_text', [])
        parser.translations = lrc_parser_data.get('translations', {})
        parser.lines_timestamps = args.lrc_timestamps
        
        local_model_path = model_dir
        os.makedirs(local_model_path, exist_ok=True)
        
        # 记录时间戳信息
        if parser.lines_timestamps:
            valid_ts_count = sum(1 for t in parser.lines_timestamps if t > 0)
            logger.info(f"Received timestamps for {valid_ts_count} lines out of {len(parser.lines_timestamps)}")
            first_few = [t for t in parser.lines_timestamps if t > 0][:5]
            if first_few:
                logger.info(f"First 5 valid timestamps: {first_few}")
        else:
            logger.info("No timestamps received from parser.")
        
        is_cuda = torch.cuda.is_available()
        device = "cuda" if is_cuda else "cpu"
        progress_queue.put(f"运行设备: {device.upper()}")
        logger.info(f"Device: {device}")
        
        # 1. 前置人声提取（MSST / RoFormer）
        align_target_audio = audio_path
        enable_vocal_sep = getattr(args, "enable_vocal_separation", False)
        vocal_model_name = getattr(args, "vocal_separation_model", DEFAULT_VOCAL_MODEL)

        if enable_vocal_sep:
            logger.info("Vocal separation enabled. Model: %s", vocal_model_name)
            vocal_model_dir = os.path.join(local_model_path, "vocal_models")
            vocal_sep = VocalSeparator(
                model_dir=vocal_model_dir,
                model_name=vocal_model_name,
                device=device
            )
            try:
                extracted_vocal_path = vocal_sep.separate(
                    audio_path=audio_path,
                    progress_queue=progress_queue,
                    stop_event=stop_event
                )
                if stop_event.is_set():
                    result_queue.put(("aborted", None))
                    return
                if extracted_vocal_path and os.path.exists(extracted_vocal_path):
                    align_target_audio = extracted_vocal_path
                    logger.info("Using separated vocals for alignment: %s", align_target_audio)
            finally:
                # 分离完成后立即释放分离器显存，确保后续对齐模型有足够显存
                vocal_sep.release()

        aligner_engine = getattr(args, "aligner_engine", "whisper")
        logger.info(f"Selected aligner engine: {aligner_engine}")
        result = None

        if aligner_engine == "ctc" and ref_text and ref_text.strip():
            progress_queue.put("正在使用【CTC 歌声强制对齐】引擎...")
            progress_queue.put("PROGRESS:35" if enable_vocal_sep else "PROGRESS:15")
            ctc_aligner = CTCAligner(device=device)
            try:
                result = ctc_aligner.align(
                    audio_path=align_target_audio,
                    parser=parser,
                    ref_text=ref_text,
                    stop_event=stop_event,
                    progress_queue=progress_queue,
                    time_offset=time_offset
                )
            finally:
                if release_vram_flag:
                    ctc_aligner.release()
        else:
            if aligner_engine == "ctc" and (not ref_text or not ref_text.strip()):
                progress_queue.put("未检测到底稿文本，CTC 模式自动切换至 Whisper 语音识别...")

            model = None
            
            # 使用模型缓存管理器
            if _model_cache.is_cached(model_size):
                logger.info("Using cached model.")
                model, _ = _model_cache.get()
                progress_queue.put(f"使用缓存模型 ({model_size})")
            else:
                cached_model, cached_size = _model_cache.get()
                if cached_model:
                    logger.info(f"Model mismatch (cached: {cached_size}, req: {model_size}). Clearing cache.")
                    progress_queue.put("切换模型中，释放旧模型显存...")
                    _model_cache.clear(force=True)
            
            # 加载新模型（原版 OpenAI Whisper，stable-whisper 封装）
            if not model:
                try:
                    if not stop_event.is_set():
                        progress_queue.put(f"加载模型 ({model_size})...")
                        progress_queue.put("PROGRESS:40" if enable_vocal_sep else "PROGRESS:10")
                        model = stable_whisper.load_model(model_size, download_root=local_model_path, device=device)

                    # 更新缓存
                    if model is not None and not release_vram_flag:
                        _model_cache.set(model, model_size)
                        
                except Exception as e:
                    raise RuntimeError(f"模型加载失败: {str(e)}")
                
            # 语言参数处理
            lang_param = language 
            
            progress_queue.put("PROGRESS:55" if enable_vocal_sep else "PROGRESS:30")
            if stop_event.is_set():
                result_queue.put(("aborted", None))
                return
            
            if ref_text and ref_text.strip():
                progress_queue.put("正在进行【结构化强制对齐】...")
                spaced_ref_text = preprocess_cjk_spaces(ref_text)
                
                align_args = {
                    "language": lang_param, 
                    "suppress_silence": True, 
                    "regroup": False
                }
                result = model.align(align_target_audio, spaced_ref_text, **align_args)
            else:
                progress_queue.put("正在进行语音识别...")
                transcribe_args = {"language": lang_param, "word_timestamps": True, "vad": True, "regroup": False}
                if initial_prompt_input and initial_prompt_input.strip():
                    transcribe_args["initial_prompt"] = initial_prompt_input.strip()
                
                result = model.transcribe(align_target_audio, **transcribe_args)
        
        if stop_event.is_set():
            result_queue.put(("aborted", None))
            return
        
        progress_queue.put("正在合成结果...")
        progress_queue.put("PROGRESS:90")
        
        aligner = LrcAligner(
            parser, 
            time_offset, 
            enable_force_calibration=args.enable_force_calibration,
            enable_avg_distribution=args.enable_avg_distribution,
            calibration_threshold=args.calibration_threshold
        )
        lrc_content = aligner.run(result, stop_event, progress_queue)
        
        if stop_event.is_set():
            result_queue.put(("aborted", None))
        else:
            result_queue.put(("success", lrc_content))
            progress_queue.put("PROGRESS:100")
            logger.info("Task completed successfully.")

    except torch.cuda.OutOfMemoryError:
        logger.error("OOM Error")
        result_queue.put(("error", "显存不足！请尝试更小的模型"))
        _model_cache.clear(force=True)
    except Exception as e:
        if not stop_event.is_set():
            logger.error(f"Error: {traceback.format_exc()}")
            result_queue.put(("error", f"错误: {str(e)}"))
    finally:
        # 根据设置决定是否释放显存
        if release_vram_flag:
            _model_cache.clear(force=True)
