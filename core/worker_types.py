# -*- coding: utf-8 -*-
"""后台任务参数类型（与 torch/stable-whisper 解耦，便于轻量测试）。"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from config import CALIBRATION_THRESHOLD


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
    lrc_timestamps: List[float] = field(default_factory=list)  # 传递行时间戳列表
    enable_force_calibration: bool = True
    enable_avg_distribution: bool = False
    calibration_threshold: float = CALIBRATION_THRESHOLD
    aligner_engine: str = "whisper"  # "whisper" 或 "ctc"
    enable_vocal_separation: bool = False  # 是否先进行 MSST 人声提取
    vocal_separation_model: str = "mel_band_roformer_vocals.ckpt"  # 人声分离模型文件名

    def __post_init__(self):
        """任务参数合法性兜底。"""
        if self.lrc_timestamps is None:
            self.lrc_timestamps = []
        if not self.aligner_engine or str(self.aligner_engine).lower() not in ("whisper", "ctc"):
            self.aligner_engine = "whisper"
        else:
            self.aligner_engine = str(self.aligner_engine).lower()
        if not self.vocal_separation_model:
            self.vocal_separation_model = "mel_band_roformer_vocals.ckpt"
        try:
            if self.calibration_threshold is None or float(self.calibration_threshold) <= 0:
                self.calibration_threshold = CALIBRATION_THRESHOLD
        except (TypeError, ValueError):
            self.calibration_threshold = CALIBRATION_THRESHOLD
