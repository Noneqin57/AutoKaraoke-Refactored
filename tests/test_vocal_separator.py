# -*- coding: utf-8 -*-
"""core.vocal_separator 轻量单元测试（不依赖实际 GPU 推理，纯 CPU 快速执行）。"""
import os
import pytest
from multiprocessing import Event, Queue

from core.vocal_separator import (
    VocalSeparator,
    resolve_model_filename,
    MODEL_ALIASES
)


def test_resolve_model_filename():
    """测试人声分离模型别名解析"""
    assert resolve_model_filename("mel_band_roformer") == "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt"
    assert resolve_model_filename("BS-Roformer-Viperx-1297.ckpt") == "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
    assert resolve_model_filename("UVR-MDX-NET-Inst_HQ_3.onnx") == "UVR-MDX-NET-Inst_HQ_3.onnx"
    assert resolve_model_filename("custom_model.ckpt") == "custom_model.ckpt"
    assert resolve_model_filename("") == "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt"


def test_vocal_separator_init(tmp_path):
    """测试分离器路径初始化"""
    model_dir = str(tmp_path / "models")
    output_dir = str(tmp_path / "vocals")
    separator = VocalSeparator(
        model_dir=model_dir,
        model_name="mel_band_roformer",
        output_dir=output_dir
    )
    assert separator.model_name == "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt"
    assert os.path.exists(model_dir)
    assert os.path.exists(output_dir)


def test_vocal_separator_file_not_found(tmp_path):
    """测试输入音频不存在时的报错行为"""
    separator = VocalSeparator(output_dir=str(tmp_path))
    if not separator.is_available():
        with pytest.raises(RuntimeError, match="audio-separator"):
            separator.separate("non_existent_audio.wav")
    else:
        with pytest.raises(FileNotFoundError):
            separator.separate("non_existent_audio.wav")


def test_vocal_separator_stop_event_early_return(tmp_path):
    """测试 stop_event 触发时的中断退出行为"""
    fake_audio = tmp_path / "test.mp3"
    fake_audio.write_bytes(b"dummy")
    
    stop_event = Event()
    stop_event.set()
    
    separator = VocalSeparator(output_dir=str(tmp_path))
    if separator.is_available():
        res = separator.separate(str(fake_audio), stop_event=stop_event)
        assert res == str(fake_audio)


def test_vocal_separator_release_safe():
    """测试 release 方法的幂等性与安全释放"""
    separator = VocalSeparator()
    # 多次调用 release 不应抛出异常
    separator.release()
    separator.release()


def test_librosa_get_duration_compatibility():
    """测试 librosa.get_duration 向前兼容补丁"""
    try:
        import librosa
        if hasattr(librosa, "get_duration"):
            # 测试转发逻辑
            import numpy as np
            y = np.zeros(22050)
            assert librosa.get_duration(y=y, sr=22050) == 1.0
    except ImportError:
        pass
