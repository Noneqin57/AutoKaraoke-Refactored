# -*- coding: utf-8 -*-

def format_ms(ms: float) -> str:
    """格式化毫秒为 mm:ss.mmm"""
    seconds = ms / 1000
    m = int(seconds // 60)
    s = int(seconds % 60)
    rem = int((seconds % 1) * 1000)
    return f"{m:02d}:{s:02d}.{rem:03d}"

def parse_time_tag(tag: str) -> int:
    """解析 [mm:ss.xx] 格式为毫秒"""
    try:
        clean = tag.strip("[]")
        parts = clean.split(':')
        return int((int(parts[0]) * 60 + float(parts[1])) * 1000)
    except:
        return -1

def format_time(seconds: float, time_offset: float = 0) -> str:
    """格式化秒数为 mm:ss.mmm，支持偏移"""
    final_sec = max(0, float(seconds) + time_offset)
    m = int(final_sec // 60)
    s = int(final_sec % 60)
    ms = int((final_sec % 1) * 1000)
    return f"{m:02d}:{s:02d}.{ms:03d}"
