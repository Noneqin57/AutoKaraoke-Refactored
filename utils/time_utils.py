# -*- coding: utf-8 -*-
"""时间格式化工具模块"""
from functools import lru_cache


def format_ms(ms: float) -> str:
    """格式化毫秒为 mm:ss.mmm
    
    Args:
        ms: 毫秒数
        
    Returns:
        格式化的时间字符串
    """
    seconds = ms / 1000.0
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def parse_time_tag(tag: str) -> int:
    """解析 [mm:ss.xx] 或 [mm:ss:xx] 格式为毫秒
    
    Args:
        tag: 时间标签字符串，如 [01:23.45]
        
    Returns:
        毫秒数，解析失败返回 -1
    """
    if not tag:
        return -1
        
    try:
        # 移除方括号
        clean = tag.strip("[]")
        
        # 分割分:秒
        parts = clean.split(':')
        if len(parts) != 2:
            return -1
            
        minutes = int(parts[0])
        # 处理秒和毫秒（支持 . 和 : 两种分隔符）
        seconds_str = parts[1].replace(':', '.')
        seconds = float(seconds_str)
        
        # 转换为毫秒
        total_ms = int((minutes * 60 + seconds) * 1000)
        return max(0, total_ms)  # 确保非负
        
    except (ValueError, IndexError, AttributeError):
        return -1


@lru_cache(maxsize=1024)
def format_time(seconds: float, time_offset: float = 0) -> str:
    """格式化秒数为 mm:ss.mmm，支持时间偏移
    
    此函数使用LRU缓存优化性能，避免重复计算相同的时间值。
    
    Args:
        seconds: 秒数
        time_offset: 时间偏移量（秒）
        
    Returns:
        格式化的时间字符串 mm:ss.mmm
    """
    final_sec = max(0.0, float(seconds) + float(time_offset))
    minutes = int(final_sec // 60)
    secs = int(final_sec % 60)
    milliseconds = int((final_sec % 1) * 1000)
    return f"{minutes:02d}:{secs:02d}.{milliseconds:03d}"


def seconds_to_ms(seconds: float) -> int:
    """将秒转换为毫秒
    
    Args:
        seconds: 秒数
        
    Returns:
        毫秒数
    """
    return int(seconds * 1000)


def ms_to_seconds(milliseconds: int) -> float:
    """将毫秒转换为秒
    
    Args:
        milliseconds: 毫秒数
        
    Returns:
        秒数
    """
    return milliseconds / 1000.0
