# -*- coding: utf-8 -*-

import logging
import os
import json
from threading import Lock
from typing import Any

# 镜像源配置
logger = logging.getLogger(__name__)

# 常量配置
MIN_DURATION = 0.06  # 最小时间间隔（秒）
SEARCH_WINDOW = 20   # 搜索窗口大小
TIMEOUT_CHECK_INTERVAL = 0.5  # 超时检查间隔（秒）
CALIBRATION_THRESHOLD = 1.5  # 强制校准触发阈值（秒）

# 完整语言列表 (Whisper支持的主要语言)
LANGUAGES = {
    "zh": "Chinese (中文)",
    "en": "English (英语)",
    "ja": "Japanese (日语)",
    "ko": "Korean (韩语)",
    "yue": "Cantonese (粤语)",
    "fr": "French (法语)",
    "de": "German (德语)",
    "es": "Spanish (西班牙语)",
    "ru": "Russian (俄语)",
    "it": "Italian (意大利语)",
    "pt": "Portuguese (葡萄牙语)",
    "nl": "Dutch (荷兰语)",
    "tr": "Turkish (土耳其语)",
    "pl": "Polish (波兰语)",
    "sv": "Swedish (瑞典语)",
    "id": "Indonesian (印度尼西亚语)",
    "vi": "Vietnamese (越南语)",
    "th": "Thai (泰语)",
    "ms": "Malay (马来语)",
    "hi": "Hindi (印地语)"
}

# 优化后的默认提示词
PROMPT_DEFAULTS = {
    "zh": "这是一首中文歌曲，歌词包含标点符号。",
    "ja": "这是一首日语歌曲，包含汉字和假名。",
    "en": "This is a pop song with clear lyrics.",
    "yue": "这是一首粤语歌曲。",
    "ko": "This is a Korean song.",
    "default": "Music lyrics."
}

class ConfigManager:
    """线程安全的配置管理器"""
    
    def __init__(self, config_file="settings.json"):
        self.config_file = config_file
        self.config = {}
        self._lock = Lock()
        self.load()

    def load(self):
        """加载配置文件"""
        with self._lock:
            if os.path.exists(self.config_file):
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        self.config = json.load(f)
                except (json.JSONDecodeError, IOError, UnicodeDecodeError) as e:
                    logger.warning("Failed to load config file: %s. Using default config.", e)
                    self.config = self._get_default_config()
            else:
                self.config = self._get_default_config()

    def save(self):
        """保存配置到文件"""
        with self._lock:
            try:
                directory = os.path.dirname(self.config_file) or "."
                os.makedirs(directory, exist_ok=True)
                # 创建临时文件，避免写入失败导致配置丢失
                temp_file = self.config_file + '.tmp'
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
                
                # 原子性替换
                if os.path.exists(self.config_file):
                    os.replace(temp_file, self.config_file)
                else:
                    os.rename(temp_file, self.config_file)
                    
            except Exception as e:
                logger.error("Failed to save config: %s", e)
                # 清理临时文件
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError as cleanup_error:
                        logger.error("Failed to cleanup temp file: %s", cleanup_error)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        with self._lock:
            return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """设置配置项
        
        Args:
            key: 配置键
            value: 配置值
        """
        with self._lock:
            self.config[key] = value
    
    def update(self, updates: dict):
        """批量更新配置
        
        Args:
            updates: 更新字典
        """
        with self._lock:
            self.config.update(updates)
    
    def _get_default_config(self) -> dict:
        """获取默认配置
        
        Returns:
            默认配置字典
        """
        return {
            "MODEL_SIZE": "large-v2",
            "LANGUAGE": "ja",
            "PROMPT": "",
            "OFFSET": 0,
            "CALIBRATION_THRESHOLD": 1.5,
            "RELEASE_VRAM": True,
            "MODEL_DIR": "./models",
            "OUTPUT_DIR": "",
            "THEME": "dark"
        }