# -*- coding: utf-8 -*-
"""WorkerArgs 轻量测试（不导入 torch / stable-whisper）。"""
from core.worker_types import WorkerArgs


def _make_args(**overrides):
    values = {
        "audio_path": "a.mp3",
        "model_size": "tiny",
        "language": "zh",
        "ref_text": "",
        "lrc_parser_data": {"headers": [], "lines_text": [], "translations": {}},
        "time_offset": 0.0,
        "initial_prompt_input": "",
    }
    values.update(overrides)
    return WorkerArgs(**values)


def test_defaults():
    args = _make_args()
    assert args.model_dir is None
    assert args.release_vram is True
    assert args.lrc_timestamps == []
    assert args.enable_force_calibration is True
    assert args.enable_avg_distribution is False
    assert args.calibration_threshold == 1.5
    assert args.aligner_engine == "whisper"
    assert args.enable_vocal_separation is False
    assert args.vocal_separation_model == "mel_band_roformer_vocals.ckpt"


def test_vocal_separation_args():
    args = _make_args(enable_vocal_separation=True, vocal_separation_model="BS-Roformer-Viperx-1297.ckpt")
    assert args.enable_vocal_separation is True
    assert args.vocal_separation_model == "BS-Roformer-Viperx-1297.ckpt"

    # 空值兜底回退
    args_empty = _make_args(vocal_separation_model="")
    assert args_empty.vocal_separation_model == "mel_band_roformer_vocals.ckpt"


def test_aligner_engine_validation():
    assert _make_args(aligner_engine="ctc").aligner_engine == "ctc"
    assert _make_args(aligner_engine="CTC").aligner_engine == "ctc"
    assert _make_args(aligner_engine="WHISPER").aligner_engine == "whisper"
    assert _make_args(aligner_engine="invalid_engine").aligner_engine == "whisper"
    assert _make_args(aligner_engine=None).aligner_engine == "whisper"


def test_calibration_threshold_clamps_non_positive():
    assert _make_args(calibration_threshold=0).calibration_threshold == 1.5
    assert _make_args(calibration_threshold=-1).calibration_threshold == 1.5


def test_calibration_threshold_rejects_invalid():
    assert _make_args(calibration_threshold="bad").calibration_threshold == 1.5


def test_lrc_timestamps_none_becomes_empty_list():
    assert _make_args(lrc_timestamps=None).lrc_timestamps == []

