# -*- coding: utf-8 -*-
import os
import re
import gc
import time
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

# 预编译 CJK 正则表达式
_CJK_PATTERN = re.compile(r'([\u4e00-\u9fa5\u3040-\u309f\u30a0-\u30ff])')
_MULTI_SPACE = re.compile(r'\s+')

@dataclass
class WorkerArgs:
    audio_path: str
    model_size: str
    language: str
    ref_text: str
    lrc_parser_data: Dict[str, Any]
    time_offset: float
    initial_prompt_input: str
    model_dir: Optional[str] = None
    release_vram: bool = True
    lrc_timestamps: List[float] = field(default_factory=list) # 传递行时间戳列表
    enable_force_calibration: bool = True
    enable_avg_distribution: bool = False
    enable_msst: bool = False
    msst_model_key: str = ""
    msst_model_dir: Optional[str] = None

def get_attr(obj: Any, key: str, default: Any = None) -> Any:
    """安全获取对象属性或字典值"""
    if isinstance(obj, dict): return obj.get(key, default)
    return getattr(obj, key, default)

def preprocess_cjk_spaces(text: str) -> str:
    """为 CJK 字符添加空格，便于 Whisper 对齐"""
    if not text: return text
    spaced = _CJK_PATTERN.sub(r' \1 ', text)
    return _MULTI_SPACE.sub(' ', spaced).strip()

class ModelCache:
    """模型缓存管理类，封装全局模型状态"""
    
    def __init__(self) -> None:
        self.model: Any = None
        self.model_size: Optional[str] = None
        self.logger = setup_logger("ModelCache")
    
    def get(self) -> tuple[Any, Optional[str]]:
        """获取缓存的模型"""
        return self.model, self.model_size

    def set(self, model: Any, model_size: str) -> None:
        """设置缓存的模型"""
        self.model = model
        self.model_size = model_size
        self.logger.info(f"Model cached: {model_size}")
    
    def clear(self, force: bool = True) -> None:
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
    
    def is_cached(self, model_size: str) -> bool:
        """检查指定模型是否已缓存"""
        return self.model is not None and self.model_size == model_size


# 全局模型缓存实例
_model_cache = ModelCache()

def daemon_worker(input_queue: Queue, result_queue: Queue, progress_queue: Queue, stop_event: Event) -> None:
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
            try:
                result_queue.put(("error", f"内部错误: {str(e)}"))
            except Exception:
                pass
            time.sleep(1)

def run_inference_task(args: WorkerArgs, result_queue: Queue, progress_queue: Queue, stop_event: Event) -> None:
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

    # MSST 人声分离产生的临时文件，用于最终清理
    msst_temp_path = None

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

        # 确保 HuggingFace 下载也落入指定目录
        os.environ["HF_HOME"] = local_model_path
        os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(local_model_path, "hub")

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
        progress_queue.put(f"⚙️ 运行设备: {device.upper()}")
        logger.info(f"Device: {device}")

        # === MSST 人声分离预处理 ===
        actual_audio_path = audio_path
        if args.enable_msst and args.msst_model_key:
            try:
                from core.msst_separator import run_vocal_separation

                msst_dir = args.msst_model_dir or os.path.join(os.getcwd(), "models", "msst_vocal")
                logger.info(f"MSST separation enabled. Model: {args.msst_model_key}")

                actual_audio_path = run_vocal_separation(
                    audio_path=audio_path,
                    model_key=args.msst_model_key,
                    msst_model_dir=msst_dir,
                    device=device,
                    progress_queue=progress_queue,
                    stop_event=stop_event,
                    release_vram=release_vram_flag,
                )
                msst_temp_path = actual_audio_path if actual_audio_path != audio_path else None

            except Exception as e:
                if stop_event.is_set():
                    result_queue.put(("aborted", None))
                    return
                raise RuntimeError(f"人声分离失败: {str(e)}")

        if stop_event.is_set():
            result_queue.put(("aborted", None))
            return

        model = None
        
        # 使用模型缓存管理器
        if _model_cache.is_cached(model_size):
            logger.info("Using cached model.")
            model, _ = _model_cache.get()
            progress_queue.put(f"⚡ 使用缓存模型 ({model_size})")
        else:
            cached_model, cached_size = _model_cache.get()
            if cached_model:
                logger.info(f"Model mismatch (cached: {cached_size}, req: {model_size}). Clearing cache.")
                progress_queue.put("🔄 切换模型中，释放旧模型显存...")
                _model_cache.clear(force=True)
        
        # 加载新模型
        if not model:
            try:
                use_faster = False
                if HAS_FASTER_WHISPER and not stop_event.is_set():
                    progress_queue.put(f"🚀 加载 Faster-Whisper ({model_size})...")
                    progress_queue.put("PROGRESS:10")
                    try:
                        # 尝试使用本地下载的模型路径
                        faster_whisper_path = os.path.join(local_model_path, f"faster-whisper-{model_size}")
                        if os.path.exists(faster_whisper_path):
                            logger.info(f"Loading from local path: {faster_whisper_path}")
                            model = stable_whisper.load_faster_whisper(
                                faster_whisper_path, device=device,
                                compute_type="float16" if device=="cuda" else "int8"
                            )
                        else:
                            # 回退到原始逻辑，让 stable_whisper 自动下载
                            logger.info(f"Local model not found, falling back to auto-download")
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
                    _model_cache.set(model, model_size)
                    
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
            result = model.align(actual_audio_path, spaced_ref_text, **align_args)
        else:
            progress_queue.put("正在进行语音识别...")
            transcribe_args = {"language": lang_param, "word_timestamps": True, "vad": True, "regroup": False}
            if initial_prompt_input and initial_prompt_input.strip():
                transcribe_args["initial_prompt"] = initial_prompt_input.strip()
            if hasattr(model, "model") and "FasterWhisper" in str(type(model.model)): # Check if faster whisper
                 transcribe_args["beam_size"] = 5
            
            result = model.transcribe(actual_audio_path, **transcribe_args)
        
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
        _model_cache.clear(force=True)
    except Exception as e:
        if not stop_event.is_set():
            logger.error(f"Error: {traceback.format_exc()}")
            result_queue.put(("error", f"错误: {str(e)}"))
    finally:
        # 清理 MSST 临时文件
        if msst_temp_path and os.path.exists(msst_temp_path):
            try:
                os.remove(msst_temp_path)
                logger.info(f"Cleaned up MSST temp file: {msst_temp_path}")
            except OSError:
                pass
        # 根据设置决定是否释放显存
        if release_vram_flag:
            _model_cache.clear(force=True)
