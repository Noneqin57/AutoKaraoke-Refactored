# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""
MSST / RoFormer 人声分离前处理器 (Vocal Separator)
负责调用 SOTA 人声提取模型（如 Mel-Band RoFormer、BS-RoFormer、MDX-Net），
将伴奏混响复杂的音频分离出纯净干声（Vocals Stem），显著提升后续 Whisper / CTC 歌词对齐精度。
"""
import os
import gc
import logging
from typing import Optional, List, Tuple
from multiprocessing import Queue, Event

try:
    import torch
except ImportError:
    torch = None

_IMPORT_ERROR = None
try:
    import librosa
    # 防御性补丁：librosa 1.0.0+ 移除了 filename 参数并改用 path，此处增加向前兼容代理
    _orig_get_duration = getattr(librosa, "get_duration", None)
    if _orig_get_duration is not None:
        def _safe_get_duration(*args, **kwargs):
            if "filename" in kwargs and "path" not in kwargs:
                kwargs["path"] = kwargs.pop("filename")
            return _orig_get_duration(*args, **kwargs)
        librosa.get_duration = _safe_get_duration
except Exception:
    pass

try:
    from audio_separator.separator import Separator
    AUDIO_SEPARATOR_AVAILABLE = True
except Exception as e:
    Separator = None
    AUDIO_SEPARATOR_AVAILABLE = False
    _IMPORT_ERROR = e

from utils.logger_v2 import setup_logger
from config import VOCAL_MODEL_REGISTRY, DEFAULT_VOCAL_MODEL

logger = setup_logger("VocalSeparator")

# 支持的常见高质量人声分离模型映射（支持传入简写或完整文件名）
# 主映射派生自 config.VOCAL_MODEL_REGISTRY（单一数据源），
# 历史简写别名与注册表键互不冲突，故合并顺序无影响
MODEL_ALIASES = {
    **{key: meta["filename"] for key, meta in VOCAL_MODEL_REGISTRY.items()},
    # 历史简写别名（不含于注册表键）
    "mel_band_roformer": "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
    "mel_band_roformer_vocals": "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
    "bs_roformer": "model_bs_roformer_ep_317_sdr_12.9755.ckpt",
    "mdx_net": "UVR-MDX-NET-Inst_HQ_3.onnx",
}
_DEFAULT_MODEL_FILENAME = VOCAL_MODEL_REGISTRY[DEFAULT_VOCAL_MODEL]["filename"]


def resolve_model_filename(model_name: str) -> str:
    """将模型别名解析为标准模型文件名"""
    if not model_name:
        return _DEFAULT_MODEL_FILENAME
    return MODEL_ALIASES.get(model_name.strip(), model_name.strip())


class VocalSeparator:
    """人声提取分离器封装"""

    def __init__(
        self,
        model_dir: Optional[str] = None,
        model_name: str = DEFAULT_VOCAL_MODEL,
        output_dir: Optional[str] = None,
        device: Optional[str] = None
    ):
        self.model_dir = model_dir or os.path.join(os.getcwd(), "models", "vocal_models")
        self.model_name = resolve_model_filename(model_name)
        self.output_dir = output_dir or os.path.join(os.getcwd(), "output", "temp_vocals")
        self.device = device
        self.separator = None

        os.makedirs(self.model_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)

    def is_available(self) -> bool:
        """检查当前环境是否支持人声分离"""
        return AUDIO_SEPARATOR_AVAILABLE

    def separate(
        self,
        audio_path: str,
        progress_queue: Optional[Queue] = None,
        stop_event: Optional[Event] = None
    ) -> str:
        """
        执行人声分离，提取人声干声并返回干声 WAV 文件路径。

        :param audio_path: 待分离的原始音乐路径
        :param progress_queue: 进度和消息队列
        :param stop_event: 停止信号
        :return: 提取得到的人声干声音频文件绝对路径
        """
        if not self.is_available():
            err_detail = f" (详细错误: {_IMPORT_ERROR})" if _IMPORT_ERROR else ""
            raise RuntimeError(f"未检测到 audio-separator 依赖或缺少子依赖{err_detail}，请在当前虚拟环境执行 `pip install audio-separator audioread` 安装人声分离组件。")

        if not os.path.isfile(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        if stop_event and stop_event.is_set():
            return audio_path

        if progress_queue:
            progress_queue.put("PROGRESS:5")
            progress_queue.put(f"正在准备人声提取模型 ({self.model_name})...")

        logger.info("Initializing Separator with model_dir=%s, output_dir=%s", self.model_dir, self.output_dir)

        # 初始化 Separator
        self.separator = Separator(
            model_file_dir=self.model_dir,
            output_dir=self.output_dir,
            output_format="WAV",
            normalization_threshold=0.9,
            output_single_stem="Vocals",  # 仅输出 Vocals 人声轨，大幅提升速度并减少磁盘开销
            log_level=logging.INFO
        )

        if stop_event and stop_event.is_set():
            self.release()
            return audio_path

        if progress_queue:
            progress_queue.put("PROGRESS:10")
            progress_queue.put("加载人声分离模型权重...")

        logger.info("Loading separation model: %s", self.model_name)
        self.separator.load_model(model_filename=self.model_name)

        if stop_event and stop_event.is_set():
            self.release()
            return audio_path

        if progress_queue:
            progress_queue.put("PROGRESS:15")
            progress_queue.put("正在进行 MSST / RoFormer 人声提取...")

        logger.info("Starting audio separation for: %s", audio_path)
        output_files = self.separator.separate(audio_path)

        if not output_files:
            raise RuntimeError("人声分离未产生有效输出文件。")

        # 寻找生成的人声干声文件
        vocal_file = None
        for filename in output_files:
            full_path = os.path.join(self.output_dir, filename) if not os.path.isabs(filename) else filename
            if "vocals" in filename.lower() or "vocal" in filename.lower():
                vocal_file = full_path
                break
        
        # 兜底：如果文件名不含 vocals，取第一个输出文件
        if not vocal_file:
            vocal_file = os.path.join(self.output_dir, output_files[0]) if not os.path.isabs(output_files[0]) else output_files[0]

        logger.info("Vocal extraction completed: %s", vocal_file)
        if progress_queue:
            progress_queue.put("PROGRESS:25")
            progress_queue.put("人声提取完成，准备进入歌词打轴...")

        return vocal_file

    def release(self):
        """显式清理分离器并释放显存"""
        logger.info("Releasing VocalSeparator and cleaning VRAM...")
        try:
            if self.separator is not None:
                del self.separator
                self.separator = None
        except Exception as e:
            logger.debug("Error releasing separator: %s", e)

        gc.collect()
        if torch is not None and hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()
