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

    def __post_init__(self):
        """任务参数合法性兜底。"""
        if self.lrc_timestamps is None:
            self.lrc_timestamps = []
        try:
            if self.calibration_threshold is None or float(self.calibration_threshold) <= 0:
                self.calibration_threshold = CALIBRATION_THRESHOLD
        except (TypeError, ValueError):
            self.calibration_threshold = CALIBRATION_THRESHOLD
