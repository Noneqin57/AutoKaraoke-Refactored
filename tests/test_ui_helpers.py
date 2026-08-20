# -*- coding: utf-8 -*-
"""
前端辅助逻辑单元测试 (ThemeManager, Token Parser, Undo Commands, Waveform Extractor)
无需 GPU 与音频硬件，纯逻辑快速测试。
"""
import pytest
import numpy as np
from ui.styles.tokens import DARK_THEME_TOKENS, LIGHT_THEME_TOKENS
from ui.styles.theme_manager import ThemeManager
from ui.commands.lrc_commands import WordTimestampCommand, BatchTimeShiftCommand, BatchLineShiftCommand
from utils.waveform_extractor import extract_waveform_peaks

def test_theme_tokens():
    assert "bg_window" in DARK_THEME_TOKENS
    assert "bg_window" in LIGHT_THEME_TOKENS
    assert DARK_THEME_TOKENS["bg_window"] != LIGHT_THEME_TOKENS["bg_window"]
    assert DARK_THEME_TOKENS["accent_primary"] == "#F25378"

def test_theme_manager():
    tm = ThemeManager(default_theme="dark")
    assert tm.is_dark() is True
    assert tm.current_theme == "dark"
    
    qss = tm.generate_stylesheet()
    assert "QMainWindow" in qss
    assert DARK_THEME_TOKENS["bg_window"] in qss
    
    # 切换为浅色模式
    tm.set_theme("light")
    assert tm.is_dark() is False
    assert tm.current_theme == "light"
    qss_light = tm.generate_stylesheet()
    assert LIGHT_THEME_TOKENS["bg_window"] in qss_light

def test_word_timestamp_undo_redo():
    history = []
    
    def callback(idx, new_time):
        history.append((idx, new_time))

    cmd = WordTimestampCommand(
        token_index=2,
        old_time_ms=1000,
        new_time_ms=1500,
        update_callback=callback,
        description="测试打点"
    )
    
    # redo
    cmd.redo()
    assert history[-1] == (2, 1500)
    
    # undo
    cmd.undo()
    assert history[-1] == (2, 1000)

def test_batch_time_shift_undo_redo():
    current_offset = [0]
    
    def apply_shift(delta):
        current_offset[0] += delta

    cmd = BatchTimeShiftCommand(
        tokens_backup=[],
        delta_ms=200,
        apply_callback=apply_shift,
        description="测试平移"
    )
    
    cmd.redo()
    assert current_offset[0] == 200
    
    cmd.undo()
    assert current_offset[0] == 0

def test_batch_line_shift_undo_redo():
    state = {}
    
    old_data = [
        (0, "[00:10.000]", "第一行歌词"),
        (1, "[00:15.000]", "第二行歌词[00:16.000]测试")
    ]
    new_data = [
        (0, "[00:10.200]", "第一行歌词"),
        (1, "[00:15.200]", "第二行歌词[00:16.200]测试")
    ]
    
    def apply_callback(data_list):
        for r, t, c in data_list:
            state[r] = (t, c)

    cmd = BatchLineShiftCommand(
        old_data=old_data,
        new_data=new_data,
        apply_callback=apply_callback,
        description="批量时间偏移 +200ms"
    )
    
    # redo
    cmd.redo()
    assert state[0] == ("[00:10.200]", "第一行歌词")
    assert state[1] == ("[00:15.200]", "第二行歌词[00:16.200]测试")
    
    # undo
    cmd.undo()
    assert state[0] == ("[00:10.000]", "第一行歌词")
    assert state[1] == ("[00:15.000]", "第二行歌词[00:16.000]测试")

def test_waveform_extractor_nonexistent_file():
    peaks, dur = extract_waveform_peaks("nonexistent_file.mp3")
    assert isinstance(peaks, np.ndarray)
    assert len(peaks) == 0
    assert dur == 0.0

def test_parse_word_line():
    import re
    from utils.time_utils import parse_time_tag
    
    line = "[00:10.000]夜[00:12.300]空[00:12.600]中"
    clean_text = re.sub(r'^\[\d{2}:\d{2}\.\d{2,3}\]', '', line)
    parts = re.split(r'(\[\d{2}:\d{2}\.\d{2,3}\])', clean_text)
    tokens = []
    current_time = 10000
    for part in parts:
        if not part: continue
        if re.match(r'^\[\d{2}:\d{2}\.\d{2,3}\]$', part):
            current_time = parse_time_tag(part)
        else:
            for char in part:
                tokens.append({'char': char, 'time': current_time, 'edited': False})
                
    assert len(tokens) == 3
    assert tokens[0]['char'] == '夜' and tokens[0]['time'] == 10000
    assert tokens[1]['char'] == '空' and tokens[1]['time'] == 12300
    assert tokens[2]['char'] == '中' and tokens[2]['time'] == 12600

def test_word_chip_format_time():
    from ui.components.word_chip import WordChip
    
    # 59秒 -> 00:59.42
    assert WordChip._format_chip_time(59420) == "00:59.42"
    # 1分59秒 -> 01:59.80
    assert WordChip._format_chip_time(119800) == "01:59.80"
    # 2分00秒28 -> 02:00.28 (完整显示分，不被截断为 00.28)
    assert WordChip._format_chip_time(120280) == "02:00.28"
    assert WordChip._format_chip_time(120770) == "02:00.77"


