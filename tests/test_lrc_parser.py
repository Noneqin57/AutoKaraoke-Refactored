# -*- coding: utf-8 -*-
"""core.lrc_parser 单元测试。"""
from core.lrc_parser import LrcParser


LRC_SAMPLE = """[ti:Test Song]
[ar:Test Artist]
[00:01.00]第一行
[00:01.00]第一行翻译
[00:05.50]第二行
[00:09.00]作词：某人
"""


def test_parse_basic():
    parser = LrcParser()
    text = parser.parse(LRC_SAMPLE, ".lrc")

    assert text == "第一行\n第二行"
    assert parser.headers == ["[ti:Test Song]", "[ar:Test Artist]", "[00:09.00]作词：某人"]
    assert parser.lines_timestamps == [1.0, 5.5]
    assert parser.translations == {0: ["第一行翻译"]}


def test_parse_plain_text():
    parser = LrcParser()
    text = parser.parse("你好\n世界", ".txt")
    assert text == "你好\n世界"
    assert parser.lines_timestamps == [-1.0, -1.0]


def test_parse_strips_bom_and_html():
    parser = LrcParser()
    text = parser.parse("\ufeff[00:01.00]<span>你好</span>", ".lrc")
    assert text == "你好"
    assert parser.lines_timestamps == [1.0]
SRT_SAMPLE = """1
00:00:01,000 --> 00:00:03,000
第一句

2
00:00:04,500 --> 00:00:06,000
第二句
"""


def test_parse_srt():
    parser = LrcParser()
    text = parser.parse(SRT_SAMPLE, ".srt")

    assert text == "第一句\n第二句"
    assert parser.lines_timestamps == [1.0, 4.5]
    assert parser.headers == []
    assert parser.translations == {}


def test_parse_resets_timestamps_on_reparse():
    parser = LrcParser()
    parser.parse("[00:01.00]第一行", ".lrc")
    text = parser.parse("[00:02.00]第二行", ".lrc")

    assert text == "第二行"
    assert parser.lines_timestamps == [2.0]


def test_parse_srt_with_hour_timestamp():
    parser = LrcParser()
    text = parser.parse(
        "1\n01:00:01,000 --> 01:00:03,000\n超长音频\n",
        ".srt",
    )

    assert text == "超长音频"
    assert parser.lines_timestamps == [3601.0]

def test_parse_colon_fraction_timestamp():
    parser = LrcParser()
    text = parser.parse("[00:01:50]歌词", ".lrc")

    assert text == "歌词"
    assert parser.lines_timestamps == [1.5]