# -*- coding: utf-8 -*-
"""
CTC 对齐器及辅助工具函数测试（遵循轻量级解耦风格）。
"""
from core.ctc_aligner import split_text_into_phonetic_units, CTCModelCache


def test_split_text_chinese():
    units = split_text_into_phonetic_units("海阔天空")
    assert len(units) == 4
    words = [u[0] for u in units]
    assert words == ["海", "阔", "天", "空"]
    # 拼音可能在有/无 pypinyin 模式下转换
    pinyins = [u[1] for u in units]
    assert len(pinyins) == 4


def test_split_text_japanese():
    units = split_text_into_phonetic_units("初音ミク 妄想感傷代償連盟 ありがとう")
    assert len(units) > 0
    words = [u[0] for u in units]
    assert "ミ" in words and "ク" in words


def test_split_text_mixed_english():
    units = split_text_into_phonetic_units("Hello 世界 2026!")
    words = [u[0] for u in units]
    assert words == ["Hello", "世", "界"]
    pinyins = [u[1] for u in units]
    assert pinyins[0] == "hello"


def test_split_text_empty_and_punctuations():
    assert split_text_into_phonetic_units("") == []
    assert split_text_into_phonetic_units("，。！？；：、~") == []


def test_fallback_even_distribution_mock():
    # 测试均摊分配纯算法逻辑
    units = [("海", "hai"), ("阔", "kuo")]
    from core.ctc_aligner import CTCAligner
    try:
        aligner = CTCAligner(device="cpu")
        words = aligner._fallback_even_distribution(units, start_sec=1.0, duration_sec=2.0)
        assert len(words) == 2
        assert words[0]["word"] == "海"
        assert words[0]["start"] == 1.0
        assert words[0]["end"] == 2.0
        assert words[1]["word"] == "阔"
        assert words[1]["start"] == 2.0
        assert words[1]["end"] == 3.0
    except ImportError:
        # 在无 torch 极简测试环境中跳过
        pass


def test_ctc_model_cache():
    cache = CTCModelCache()
    assert cache.get("cpu") is None
    cache.set("dummy_model", "dummy_tok", "dummy_aligner", {}, "cpu")
    cached = cache.get("cpu")
    assert cached is not None
    assert cached[0] == "dummy_model"
    assert cache.get("cuda") is None
    cache.clear()
    assert cache.get("cpu") is None
