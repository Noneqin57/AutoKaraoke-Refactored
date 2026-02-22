# -*- coding: utf-8 -*-
"""
人声分离核心模块

使用 audio-separator 库提供人声分离功能，作为 Whisper 对齐的预处理步骤。
支持 UVR MDX-Net ONNX 模型，首次使用时自动下载。
"""
import os
import gc
import tempfile
import torch
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from multiprocessing import Queue, Event

from utils.logger import setup_logger
from utils.ssl_bypass import ssl_bypass_context, patched_requests_verify

logger = setup_logger("VocalSeparator")

# ============ 模型注册表 ============

@dataclass
class VocalModelInfo:
    """人声分离模型元数据"""
    name: str          # 显示名称
    key: str           # 唯一标识符
    model_filename: str  # 模型文件名 (audio-separator 自动管理)
    size_mb: float     # 近似大小 (MB)


# 支持的人声分离模型（audio-separator 内置 UVR 模型）
VOCAL_MODELS: Dict[str, VocalModelInfo] = {
    "UVR-MDX-NET-Voc_FT": VocalModelInfo(
        name="UVR MDX-Net Vocal FT",
        key="UVR-MDX-NET-Voc_FT",
        model_filename="UVR-MDX-NET-Voc_FT.onnx",
        size_mb=67,
    ),
    "UVR_MDXNET_KARA_2": VocalModelInfo(
        name="UVR MDX-Net Karaoke 2",
        key="UVR_MDXNET_KARA_2",
        model_filename="UVR_MDXNET_KARA_2.onnx",
        size_mb=67,
    ),
    "Kim_Vocal_2": VocalModelInfo(
        name="Kim Vocal 2",
        key="Kim_Vocal_2",
        model_filename="Kim_Vocal_2.onnx",
        size_mb=67,
    ),
}


# ============ 模型缓存 ============

class SeparatorCache:
    """分离器模型缓存管理"""

    def __init__(self) -> None:
        self.separator: Any = None
        self.model_key: Optional[str] = None

    def get(self) -> Any:
        return self.separator

    def set(self, separator: Any, model_key: str) -> None:
        self.separator = separator
        self.model_key = model_key
        logger.info(f"Separator model cached: {model_key}")

    def clear(self, force: bool = True) -> None:
        if not force:
            return
        try:
            if self.separator is not None:
                del self.separator
        except Exception as e:
            logger.debug(f"Separator cache cleanup: {e}")

        self.separator = None
        self.model_key = None

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def is_cached(self, model_key: str) -> bool:
        return self.separator is not None and self.model_key == model_key


# 模块级缓存实例
_separator_cache = SeparatorCache()


def _load_separator(model_key: str):
    """
    加载人声分离器模型。

    使用 audio-separator 库，模型首次使用时自动下载。
    """
    model_info = VOCAL_MODELS.get(model_key)
    if not model_info:
        raise ValueError(f"未知的分离模型: {model_key}")

    try:
        from audio_separator.separator import Separator
    except ImportError:
        raise ImportError(
            "未安装 audio-separator 库。\n"
            "请运行: pip install audio-separator[cpu]"
        )

    # 创建临时输出目录
    output_dir = tempfile.mkdtemp(prefix="reatk_sep_")

    separator = Separator(
        output_dir=output_dir,
        output_format="WAV",
        output_single_stem="vocals",
    )

    # 临时绕过 SSL 验证以支持下载模型
    with ssl_bypass_context(True), patched_requests_verify():
        separator.load_model(model_info.model_filename)

    return separator


def run_vocal_separation(
    audio_path: str,
    model_key: str,
    msst_model_dir: str,  # 保留参数兼容性，但不再使用
    device: str,
    progress_queue: Queue,
    stop_event: Event,
    release_vram: bool = True,
) -> str:
    """
    执行人声分离，返回分离后的人声音频临时文件路径。

    Args:
        audio_path: 原始音频文件路径
        model_key: 模型标识符
        msst_model_dir: (已弃用) 保留兼容性
        device: 运算设备
        progress_queue: 进度消息队列
        stop_event: 取消信号
        release_vram: 是否在完成后释放显存

    Returns:
        分离后人声音频的临时 WAV 文件路径
    """
    global _separator_cache

    model_info = VOCAL_MODELS.get(model_key)
    if not model_info:
        raise ValueError(f"未知的分离模型: {model_key}")

    # 加载模型
    if _separator_cache.is_cached(model_key):
        logger.info("Using cached separator model.")
        separator = _separator_cache.get()
        progress_queue.put("⚡ 使用缓存的人声分离模型")
    else:
        if _separator_cache.separator is not None:
            logger.info("Clearing old separator cache.")
            _separator_cache.clear(force=True)

        progress_queue.put(f"正在加载人声分离模型 ({model_info.name})...")
        progress_queue.put("PROGRESS:5")

        separator = _load_separator(model_key)

        if not release_vram:
            _separator_cache.set(separator, model_key)

    if stop_event.is_set():
        return audio_path

    # 执行分离
    progress_queue.put("正在分离人声（这可能需要一些时间）...")
    progress_queue.put("PROGRESS:10")

    try:
        output_files = separator.separate(audio_path)
    except Exception as e:
        raise RuntimeError(f"人声分离失败: {str(e)}")

    if stop_event.is_set():
        return audio_path

    progress_queue.put("PROGRESS:18")

    # audio-separator 返回输出文件列表，找到人声文件
    if not output_files or len(output_files) == 0:
        raise RuntimeError("人声分离结果为空")

    # output_single_stem="vocals" 时只输出一个文件
    vocal_path = output_files[0]

    # audio-separator 返回的可能是相对路径（文件名），尝试拼接 output_dir
    if not os.path.exists(vocal_path):
        if hasattr(separator, 'output_dir') and separator.output_dir:
            possible_path = os.path.join(separator.output_dir, vocal_path)
            if os.path.exists(possible_path):
                vocal_path = possible_path
    
    if not os.path.exists(vocal_path):
        raise RuntimeError(f"人声分离输出文件不存在: {vocal_path}")

    # 清理
    if release_vram:
        _separator_cache.clear(force=True)

    progress_queue.put("人声分离完成")
    progress_queue.put("PROGRESS:20")

    logger.info(f"Vocal separation complete. Output: {vocal_path}")
    return vocal_path


def get_available_models() -> List[Dict[str, Any]]:
    """获取可用的人声分离模型列表"""
    return [
        {
            "key": m.key,
            "name": m.name,
            "model_filename": m.model_filename,
            "size_mb": m.size_mb,
            "is_downloaded": True,  # audio-separator 自动管理，视为始终可用
        }
        for m in VOCAL_MODELS.values()
    ]
