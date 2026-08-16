# -*- coding: utf-8 -*-
"""utils.time_utils 单元测试。"""
from utils.time_utils import format_ms, format_time, parse_time_tag, seconds_to_ms


class TestParseTimeTag:
    def test_parse_mm_ss(self):
        assert parse_time_tag("[01:23]") == 83000

    def test_parse_dot_fraction(self):
        assert parse_time_tag("[01:23.45]") == 83450

    def test_parse_colon_fraction(self):
        # [mm:ss:xx] 与 [mm:ss.xx] 等价
        assert parse_time_tag("[01:23:45]") == 83450

    def test_parse_milliseconds(self):
        assert parse_time_tag("[01:23.456]") == 83456

    def test_parse_invalid(self):
        assert parse_time_tag("") == -1
        assert parse_time_tag("not a tag") == -1
        assert parse_time_tag("[aa:bb]") == -1

    def test_parse_negative_clamps_to_zero(self):
        assert parse_time_tag("[-01:00.00]") == 0


class TestFormatTime:
    def test_format_zero(self):
        assert format_time(0.0) == "00:00.000"

    def test_format_minutes_seconds(self):
        assert format_time(61.5) == "01:01.500"

    def test_format_with_offset(self):
        assert format_time(1.0, -0.5) == "00:00.500"

    def test_format_negative_clamps(self):
        assert format_time(-5.0) == "00:00.000"


class TestFormatMs:
    def test_format_ms(self):
        assert format_ms(0) == "00:00.000"
        assert format_ms(83450) == "01:23.450"


    def test_format_ms_rounds_near_boundary(self):
        assert format_ms(83450.6) == "01:23.451"
        assert format_ms(-1) == "00:00.000"


def test_format_time_carries_into_next_minute():
    assert format_time(119.9999) == "02:00.000"
    assert format_time(59.9996) == "01:00.000"


def test_seconds_to_ms_rounds():
    assert seconds_to_ms(1.0009) == 1001
    assert seconds_to_ms(1.0004) == 1000