# -*- coding: utf-8 -*-
"""
极速音频波形提取器 (Waveform Extractor)
基于 PyAV (av) 或标准库快速提取音频振幅峰值数据，用于 UI 界面波形绘制。
"""
import os
import logging
from typing import Tuple, Optional, Dict
import numpy as np

logger = logging.getLogger(__name__)

# 内存缓存：(file_path, mtime, samples_per_second) -> (peaks_array, duration_seconds)
_CACHE: Dict[Tuple[str, float, int], Tuple[np.ndarray, float]] = {}

def extract_waveform_peaks(
    audio_path: str,
    samples_per_second: int = 100
) -> Tuple[np.ndarray, float]:
    """
    快速提取音频文件的归一化波形峰值数据与总时长。

    Args:
        audio_path: 音频文件路径
        samples_per_second: 每秒提取的峰值采样点数（默认 100，即 10ms 一个点）

    Returns:
        (peaks, duration_seconds):
        - peaks: shape (N,) 的 float32 numpy 数组，取值范围 [0.0, 1.0]
        - duration_seconds: 音频总时长（秒）
    """
    if not audio_path or not os.path.exists(audio_path):
        return np.zeros(0, dtype=np.float32), 0.0

    try:
        mtime = os.path.getmtime(audio_path)
    except OSError:
        mtime = 0.0

    cache_key = (os.path.abspath(audio_path), mtime, samples_per_second)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    peaks, duration = _extract_via_av(audio_path, samples_per_second)
    if peaks is None or len(peaks) == 0:
        peaks, duration = _extract_via_wave(audio_path, samples_per_second)

    if peaks is None:
        peaks = np.zeros(0, dtype=np.float32)
        duration = 0.0

    _CACHE[cache_key] = (peaks, duration)
    return peaks, duration


def _extract_via_av(audio_path: str, samples_per_second: int) -> Tuple[Optional[np.ndarray], float]:
    """使用 PyAV 快速解码并按窗口提取最大峰值"""
    try:
        import av
    except ImportError:
        return None, 0.0

    try:
        container = av.open(audio_path)
        stream = next((s for s in container.streams if s.type == 'audio'), None)
        if not stream:
            container.close()
            return None, 0.0

        sample_rate = stream.codec_context.sample_rate or 44100
        hop_size = max(1, int(sample_rate / samples_per_second))
        
        peak_list = []
        buffer = []
        buffer_len = 0
        total_samples = 0

        for frame in container.decode(stream):
            # 转为单声道 numpy 数组
            arr = frame.to_ndarray() # shape: (channels, samples) or (samples,)
            if arr.ndim == 2:
                # 多声道取均值
                mono = arr.mean(axis=0)
            else:
                mono = arr

            # 转为 float 并取绝对值
            if mono.dtype != np.float32 and mono.dtype != np.float64:
                # 针对 int16, int32 归一化
                if mono.dtype == np.int16:
                    mono = np.abs(mono.astype(np.float32) / 32768.0)
                elif mono.dtype == np.int32:
                    mono = np.abs(mono.astype(np.float32) / 2147483648.0)
                elif mono.dtype == np.uint8:
                    mono = np.abs((mono.astype(np.float32) - 128.0) / 128.0)
                else:
                    mono = np.abs(mono.astype(np.float32))
            else:
                mono = np.abs(mono.astype(np.float32))

            total_samples += len(mono)
            buffer.append(mono)
            buffer_len += len(mono)

            # 当缓冲区累积足够时，按 hop_size 分批计算 max
            while buffer_len >= hop_size * 50:
                full_buf = np.concatenate(buffer)
                num_chunks = len(full_buf) // hop_size
                if num_chunks > 0:
                    usable_samples = num_chunks * hop_size
                    reshaped = full_buf[:usable_samples].reshape(num_chunks, hop_size)
                    chunk_peaks = reshaped.max(axis=1)
                    peak_list.extend(chunk_peaks.tolist())
                    
                    remainder = full_buf[usable_samples:]
                    buffer = [remainder]
                    buffer_len = len(remainder)
                else:
                    break

        if buffer:
            full_buf = np.concatenate(buffer)
            if len(full_buf) > 0:
                num_chunks = len(full_buf) // hop_size
                if num_chunks > 0:
                    usable = num_chunks * hop_size
                    reshaped = full_buf[:usable].reshape(num_chunks, hop_size)
                    peak_list.extend(reshaped.max(axis=1).tolist())
                    rem = full_buf[usable:]
                    if len(rem) > 0:
                        peak_list.append(float(rem.max()))
                else:
                    peak_list.append(float(full_buf.max()))

        container.close()

        duration = total_samples / float(sample_rate) if sample_rate > 0 else 0.0
        if not peak_list:
            return np.zeros(0, dtype=np.float32), duration

        peaks = np.array(peak_list, dtype=np.float32)
        # 整体自适应归一化 (防爆音)
        max_val = float(peaks.max()) if len(peaks) > 0 else 1.0
        if max_val > 1e-4:
            peaks = peaks / max_val
        peaks = np.clip(peaks, 0.0, 1.0)

        return peaks, duration

    except Exception as e:
        logger.warning("Failed to extract waveform peaks via av from %s: %s", audio_path, e)
        return None, 0.0


def _extract_via_wave(audio_path: str, samples_per_second: int) -> Tuple[Optional[np.ndarray], float]:
    """针对标准 .wav 文件的纯标准库降级提取"""
    import wave
    try:
        with wave.open(audio_path, 'rb') as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            if nframes == 0 or framerate == 0:
                return None, 0.0

            raw_bytes = wf.readframes(nframes)
            duration = nframes / float(framerate)

            if sampwidth == 2:
                data = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            elif sampwidth == 1:
                data = (np.frombuffer(raw_bytes, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
            elif sampwidth == 4:
                data = np.frombuffer(raw_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                return None, duration

            if channels > 1:
                data = data.reshape(-1, channels).mean(axis=1)

            hop_size = max(1, int(framerate / samples_per_second))
            num_chunks = len(data) // hop_size
            if num_chunks == 0:
                return np.array([float(np.abs(data).max())], dtype=np.float32), duration

            reshaped = np.abs(data[:num_chunks * hop_size]).reshape(num_chunks, hop_size)
            peaks = reshaped.max(axis=1)
            max_val = float(peaks.max()) if len(peaks) > 0 else 1.0
            if max_val > 1e-4:
                peaks = peaks / max_val
            peaks = np.clip(peaks, 0.0, 1.0)
            return peaks, duration

    except Exception:
        return None, 0.0
