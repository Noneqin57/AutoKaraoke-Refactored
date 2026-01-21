# -*- coding: utf-8 -*-
import os
import re
import gc
import torch
import traceback
import stable_whisper
from multiprocessing import Queue, Event
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

from config import MIN_DURATION
from core.lrc_parser import LrcParser
from core.lrc_aligner import LrcAligner
from utils.time_utils import format_time
from utils.logger import setup_logger

try:
    import faster_whisper
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False

@dataclass
class WorkerArgs:
    audio_path: str
    model_size: str
    language: str
    ref_text: str
    lrc_parser_data: Dict[str, Any]
    time_offset: float
    initial_prompt_input: str
    model_dir: str = None
    release_vram: bool = True
    lrc_timestamps: List[float] = field(default_factory=list) # 传递行时间戳列表
    enable_force_calibration: bool = True
    enable_avg_distribution: bool = False

def get_attr(obj, key, default=None):
    if isinstance(obj, dict): return obj.get(key, default)
    return getattr(obj, key, default)

def preprocess_cjk_spaces(text):
    if not text: return text
    pattern = r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff])'
    spaced = re.sub(pattern, r' \1 ', text)
    return re.sub(r'\s+', ' ', spaced).strip()

# 全局变量用于缓存模型（仅在子进程内有效）
_cached_model = None
_cached_model_size = None

def clear_vram(model, force=True):
    global _cached_model, _cached_model_size
    if not force:
        return

    logger = setup_logger("Worker")
    try:
        if model:
            if hasattr(model, 'to'):
                model.to("cpu")
            del model
    except (AttributeError, RuntimeError) as e:
        logger.debug(f"Expected error during VRAM cleanup: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during VRAM cleanup: {e}")
    
    _cached_model = None
    _cached_model_size = None
    
    gc.collect()
    if torch.cuda.is_available(): torch.cuda.empty_cache()

def daemon_worker(input_queue: Queue, result_queue: Queue, progress_queue: Queue, stop_event: Event):
    """
    常驻后台的工作进程，监听任务队列并执行
    """
    global _cached_model, _cached_model_size
    
    # 初始化日志
    logger = setup_logger("WorkerDaemon")
    logger.info("Daemon worker process started, waiting for tasks...")
    
    while True:
        try:
            task = input_queue.get()
            
            if task == "EXIT":
                logger.info("Received EXIT signal. Shutting down daemon.")
                break
                
            if isinstance(task, WorkerArgs):
                logger.info("Received new task.")
                # 重置 stop_event
                stop_event.clear()
                # 执行任务
                run_inference_task(task, result_queue, progress_queue, stop_event)
                
                # 任务结束后，主动进行一次轻量级 GC，但保留模型
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    
        except Exception as e:
            logger.error(f"Daemon loop error: {traceback.format_exc()}")
            # 防止死循环，稍作休眠
            import time
            time.sleep(1)

def run_inference_task(args: WorkerArgs, result_queue: Queue, progress_queue: Queue, stop_event: Event):
    """
    执行单次推理任务 (原 worker_process 逻辑)
    """
    global _cached_model, _cached_model_size
    
    # 初始化日志 (每次任务可能需要更新上下文，或者直接使用 global logger)
    logger = setup_logger("Worker")
    
    # Unpack args
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
        
        parser = LrcParser()
        parser.headers = lrc_parser_data.get('headers', [])
        parser.lines_text = lrc_parser_data.get('lines_text', [])
        parser.translations = lrc_parser_data.get('translations', {})
        parser.lines_timestamps = args.lrc_timestamps # 恢复时间戳信息
        
        local_model_path = model_dir
        os.makedirs(local_model_path, exist_ok=True)
        
        # 记录传入的时间戳信息
        if parser.lines_timestamps:
            valid_ts_count = sum(1 for t in parser.lines_timestamps if t > 0)
            logger.info(f"Received timestamps for {valid_ts_count} lines out of {len(parser.lines_timestamps)}")
            # Log first 5 valid timestamps for debugging
            first_few = [t for t in parser.lines_timestamps if t > 0][:5]
            if first_few:
                logger.info(f"First 5 valid timestamps: {first_few}")
        else:
            logger.info("No timestamps received from parser.")
        
        is_cuda = torch.cuda.is_available()
        device = "cuda" if is_cuda else "cpu"
        progress_queue.put(f"⚙️ 运行设备: {device.upper()}")
        logger.info(f"Device: {device}")

        model = None
        
        # 尝试使用缓存模型
        if _cached_model:
            if _cached_model_size == model_size:
                logger.info("Using cached model.")
                model = _cached_model
                progress_queue.put(f"⚡ 使用缓存模型 ({model_size})")
            else:
                logger.info(f"Model mismatch (cached: {_cached_model_size}, req: {model_size}). Clearing cache.")
                progress_queue.put("🔄 切换模型中，释放旧模型显存...")
                # 显式清理旧模型，防止双倍显存占用导致 OOM
                clear_vram(_cached_model, force=True)
                _cached_model = None
                _cached_model_size = None
        
        # 加载新模型
        if not model:
            try:
                use_faster = False
                if HAS_FASTER_WHISPER and not stop_event.is_set():
                    progress_queue.put(f"🚀 加载 Faster-Whisper ({model_size})...")
                    progress_queue.put("PROGRESS:10")
                    try:
                        model = stable_whisper.load_faster_whisper(
                            model_size, download_root=local_model_path, device=device,
                            compute_type="float16" if device=="cuda" else "int8"
                        )
                        use_faster = True
                    except Exception as fw_error:
                        logger.warning(f"Faster-Whisper load failed: {fw_error}")
                        model = None
                
                if not model and not stop_event.is_set():
                    progress_queue.put(f"加载标准模型 ({model_size})...")
                    progress_queue.put("PROGRESS:10")
                    model = stable_whisper.load_model(model_size, download_root=local_model_path, device=device)
                
                # 更新缓存
                if not release_vram_flag:
                    _cached_model = model
                    _cached_model_size = model_size
                    
            except Exception as e:
                raise RuntimeError(f"模型加载失败: {str(e)}")
            
        # 语言参数处理
        lang_param = language 
        # 移除 Auto 检测逻辑，因为 UI 已经强制选择了语言
        
        progress_queue.put("PROGRESS:30")
        result = None
        if stop_event.is_set():
            result_queue.put(("aborted", None))
            return
        
        if ref_text and ref_text.strip():
            progress_queue.put("正在进行【结构化强制对齐】...")
            spaced_ref_text = preprocess_cjk_spaces(ref_text)
            
            # 使用更严格的参数调用 align
            # 注意: vad=True 需要下载 Silero VAD 模型，如果网络不通会导致 502/ConnectTimeout
            # 这里我们先禁用 vad 参数以确保国内网络下的稳定性，
            # 依靠 suppress_silence 和全局对齐算法来处理静音。
            align_args = {
                "language": lang_param, 
                "suppress_silence": True, 
                "regroup": False
            }
            
            # 只有当确实已经下载了 VAD 模型或者网络环境允许时才建议开启 vad=True
            # result = model.align(audio_path, spaced_ref_text, **align_args)
            
            # 如果是 faster-whisper，align 方法参数可能略有不同，但 stable-whisper 做了封装
            result = model.align(audio_path, spaced_ref_text, **align_args)
        else:
            progress_queue.put("正在进行语音识别...")
            transcribe_args = {"language": lang_param, "word_timestamps": True, "vad": True, "regroup": False}
            if initial_prompt_input and initial_prompt_input.strip():
                transcribe_args["initial_prompt"] = initial_prompt_input.strip()
            if hasattr(model, "model") and "FasterWhisper" in str(type(model.model)): # Check if faster whisper
                 transcribe_args["beam_size"] = 5
            
            result = model.transcribe(audio_path, **transcribe_args)
        
        if stop_event.is_set():
            result_queue.put(("aborted", None))
            return
        
        progress_queue.put("正在合成结果...")
        progress_queue.put("PROGRESS:90")
        
        aligner = LrcAligner(
            parser, 
            time_offset, 
            enable_force_calibration=args.enable_force_calibration,
            enable_avg_distribution=args.enable_avg_distribution
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
        result_queue.put(("error", "❌ 显存不足！请尝试更小的模型"))
        clear_vram(model, force=True) # OOM 时强制清理
    except Exception as e:
        if not stop_event.is_set():
            logger.error(f"Error: {traceback.format_exc()}")
            result_queue.put(("error", f"错误: {str(e)}"))
    finally:
        # 根据设置决定是否释放显存
        if release_vram_flag:
            clear_vram(model, force=True)
        else:
            # 如果保留显存，不做任何操作，让 _cached_model 保持引用
            pass
