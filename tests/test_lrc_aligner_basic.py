# -*- coding: utf-8 -*-
"""core.lrc_aligner 基础冒烟测试（不加载 torch/whisper 模型）。"""
from multiprocessing import Event
import pytest

from core.lrc_aligner_v2 import LrcAligner
from core.lrc_parser import LrcParser
class _DummyQueue:
    """替代 multiprocessing.Queue：对齐逻辑仅调用 put()。"""

    def __init__(self):
        self.messages = []

    def put(self, msg):
        self.messages.append(msg)


def make_result_with_words():
    return {
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "你好世界",
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                    {"word": "世界", "start": 1.0, "end": 2.0},
                ],
            }
        ]
    }


def test_no_reference_generates_raw_lrc():
    parser = LrcParser()
    parser.lines_text = []
    aligner = LrcAligner(parser)

    lrc = aligner.run(
        {"segments": [{"start": 1.0, "text": "你好"}]},
        Event(),
        _DummyQueue(),
    )

    assert lrc == "[00:01.000]你好"


def test_perfect_match_fills_word_timestamps():
    parser = LrcParser()
    parser.parse("你好世界", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    lrc = aligner.run(make_result_with_words(), Event(), _DummyQueue())

    assert "[00:00.000]你" in lrc
    assert "[00:00.500]好" in lrc
    assert "[00:01.000]世" in lrc
    assert "[00:01.500]界" in lrc
def test_english_words_align_at_word_level():
    parser = LrcParser()
    parser.parse("hello world", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "hello", "start": 0.0, "end": 0.5},
                    {"word": "world", "start": 0.5, "end": 1.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:00.000]hello" in lrc
    assert "[00:00.500]world" in lrc


def test_mixed_cjk_english_alignment():
    parser = LrcParser()
    parser.parse("你好 world", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                    {"word": "world", "start": 1.0, "end": 2.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:00.000]你" in lrc
    assert "[00:00.500]好" in lrc
    assert "[00:01.000]world" in lrc


def test_insert_region_is_ignored():
    parser = LrcParser()
    parser.parse("你好", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 0.5},
                    {"word": "世界", "start": 0.5, "end": 1.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert lrc == "[00:00.000]你[00:00.250]好"


def test_replace_region_falls_back_to_interpolation():
    parser = LrcParser()
    parser.parse("你好世界", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                    {"word": "地球", "start": 1.0, "end": 2.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    # 你/好 精确匹配；世/界 无匹配，由行内插值补出（晚于 0.5s）
    assert "[00:00.000]你" in lrc
    assert "[00:00.500]好" in lrc
    assert "世" in lrc and "界" in lrc

def test_segments_without_words_fall_back_to_text_distribution():
    parser = LrcParser()
    parser.parse("你好世界", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "你好世界"}
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:00.000]你" in lrc
    assert "[00:00.500]好" in lrc
    assert "[00:01.000]世" in lrc
    assert "[00:01.500]界" in lrc

def make_lrc_result():
    return {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                    {"word": "世界", "start": 1.0, "end": 2.0},
                ]
            }
        ]
    }


def test_force_calibration_default_threshold_keeps_small_deviation():
    parser = LrcParser()
    parser.parse("[00:01.00]你好世界", ".lrc")
    aligner = LrcAligner(parser, enable_force_calibration=True)

    lrc = aligner.run(make_lrc_result(), Event(), _DummyQueue())

    # 偏差 1.0s < 默认阈值 1.5s，不触发强制校准
    assert "[00:00.000]你" in lrc


def test_force_calibration_custom_threshold_shifts_line():
    parser = LrcParser()
    parser.parse("[00:01.00]你好世界", ".lrc")
    aligner = LrcAligner(parser, enable_force_calibration=True, calibration_threshold=0.5)

    lrc = aligner.run(make_lrc_result(), Event(), _DummyQueue())

    # 偏差 1.0s > 阈值 0.5s，整行平移到原始时间戳
    assert "[00:01.000]你" in lrc
    assert "[00:01.500]好" in lrc

def test_hard_boundary_compresses_overflow_line():
    parser = LrcParser()
    parser.parse("[00:00.00]你好\n[00:01.00]世界", ".lrc")
    aligner = LrcAligner(parser, enable_force_calibration=True, calibration_threshold=1.5)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 2.0},
                    {"word": "世界", "start": 2.0, "end": 3.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    # 第一行“好”原本在 1.0s，越过下一行 1.0s 边界，最终硬边界检查压缩到 0.475s
    assert "[00:00.000]你" in lrc
    assert "[00:00.475]好" in lrc


def test_avg_distribution_fills_gap_after_force_calibration():
    parser = LrcParser()
    parser.parse("[00:01.00]你好\n[00:03.00]世界", ".lrc")
    aligner = LrcAligner(
        parser,
        enable_force_calibration=True,
        enable_avg_distribution=True,
        calibration_threshold=0.5,
    )

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                    {"word": "世界", "start": 1.0, "end": 2.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    # 第一行触发校准后平均铺到下一行前（1.0s -> 2.9s 区间）
    assert "[00:01.000]你" in lrc
    assert "[00:01.950]好" in lrc
    # 第二行同样被校准回原始时间戳
    assert "[00:03.000]世" in lrc


def test_japanese_mixed_tokenization():
    parser = LrcParser()
    parser.parse("こんにちは world", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "こんにちは", "start": 0.0, "end": 2.0},
                    {"word": "world", "start": 2.0, "end": 3.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    # 假名逐字：こ(0.0)、ん(0.4)、に(0.8)、ち(1.2)、は(1.6)；world 在 2.0s
    assert "[00:00.000]こ" in lrc
    assert "[00:01.600]は" in lrc
    assert "[00:02.000]world" in lrc


def test_punctuation_preserved_between_tokens():
    parser = LrcParser()
    parser.parse("你好，世界！", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 0.5},
                    {"word": "世界", "start": 0.5, "end": 1.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:00.000]你" in lrc
    # 逗号保留在“世”之前，不丢失标点
    assert "，[00:00.500]世" in lrc

def test_repeated_english_words_use_cursor_correctly():
    parser = LrcParser()
    parser.parse("hello hello", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "hello", "start": 0.0, "end": 1.0},
                    {"word": "hello", "start": 1.0, "end": 2.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:00.000]hello" in lrc
    assert "[00:01.000]hello" in lrc


def test_no_words_fallback_preserves_punctuation_gap():
    parser = LrcParser()
    parser.parse("你好，世界", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "你好，世界"}
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:00.000]你" in lrc
    assert "好，[00:00.500]世" in lrc

def test_stop_event_returns_empty_result():
    parser = LrcParser()
    parser.parse("你好世界", ".txt")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    stop_event = Event()
    stop_event.set()

    lrc = aligner.run(make_result_with_words(), stop_event, _DummyQueue())

    assert lrc == ""

def test_translation_lines_use_effective_start_time():
    parser = LrcParser()
    parser.parse("[00:01.00]你好\n[00:01.00]Hello", ".lrc")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:00.000]你" in lrc
    assert "[00:00.000]Hello" in lrc

def test_time_offset_applies_to_output():
    parser = LrcParser()
    parser.parse("你好", ".txt")
    aligner = LrcAligner(parser, time_offset=1.0, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert "[00:01.000]你" in lrc
    assert "[00:01.500]好" in lrc

def test_headers_are_preserved_in_output():
    parser = LrcParser()
    parser.parse("[ti:Test Song]\n[ar:Artist]\n[00:00.50]你好", ".lrc")
    aligner = LrcAligner(parser, enable_force_calibration=False)

    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.5, "end": 1.0},
                ]
            }
        ]
    }

    lrc = aligner.run(result, Event(), _DummyQueue())

    assert lrc.startswith("[ti:Test Song]\n[ar:Artist]\n\n")
    assert "[00:00.500]你" in lrc

def test_match_replace_region_rescues_local_equal_tokens():
    parser = LrcParser()
    aligner = LrcAligner(parser, enable_force_calibration=False)

    user_seq = [
        {"clean_text": "a", "time": None},
        {"clean_text": "b", "time": None},
    ]
    ai_seq = [
        {"text": "x", "start": 1.0},
        {"text": "b", "start": 2.0},
    ]

    last_time = aligner._match_replace_region(user_seq, ai_seq, 0, 2, 0, 2, 0.0)

    assert user_seq[0]["time"] is None
    assert user_seq[1]["time"] == 2.0
    assert last_time == 2.0

def test_interpolate_timestamps_smooth_and_right_absorb():
    aligner = LrcAligner(LrcParser(), enable_force_calibration=False)

    smooth = [
        {"time": None},
        {"time": None},
        {"time": 1.0},
    ]
    aligner._interpolate_timestamps(smooth, 0.0)
    assert smooth[0]["time"] == pytest.approx(1 / 3)
    assert smooth[1]["time"] == pytest.approx(2 / 3)

    absorb = [{"time": None}, {"time": 5.0}]
    aligner._interpolate_timestamps(absorb, 0.0)
    assert absorb[0]["time"] == pytest.approx(4.7)


def test_clean_hallucinations_removes_long_gap():
    aligner = LrcAligner(LrcParser(), enable_force_calibration=False)

    tokens = [{"time": 0.0}, {"time": 4.0}]
    aligner._clean_hallucinations(tokens)
    assert tokens[0]["time"] is None
    assert tokens[1]["time"] == 4.0

    ok = [{"time": 0.0}, {"time": 2.0}]
    aligner._clean_hallucinations(ok)
    assert ok[0]["time"] == 0.0

def test_extract_words_uses_word_timestamps():
    aligner = LrcAligner(LrcParser(), enable_force_calibration=False)
    result = {
        "segments": [
            {
                "words": [
                    {"word": "你好", "start": 0.0, "end": 1.0},
                    {"word": "世界", "start": 1.0, "end": 2.0},
                ]
            }
        ]
    }

    aligner._extract_words_from_result(result)

    assert len(aligner.ai_words_pool) == 2
    assert aligner.ai_words_pool[0]["word"] == "你好"


def test_extract_words_fallback_creates_pseudo_words():
    aligner = LrcAligner(LrcParser(), enable_force_calibration=False)
    result = {"segments": [{"start": 0.0, "end": 2.0, "text": "你好世界"}]}

    aligner._extract_words_from_result(result)

    assert [w["word"] for w in aligner.ai_words_pool] == ["你", "好", "世", "界"]
    assert aligner.ai_words_pool[0]["start"] == 0.0
    assert aligner.ai_words_pool[-1]["end"] == 2.0

def test_raw_lrc_path_honors_stop_event():
    parser = LrcParser()
    parser.lines_text = []
    aligner = LrcAligner(parser, enable_force_calibration=False)

    stop_event = Event()
    stop_event.set()

    lrc = aligner.run(
        {"segments": [{"start": 0.0, "text": "你好"}]},
        stop_event,
        _DummyQueue(),
    )

    assert lrc == ""