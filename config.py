# -*- coding: utf-8 -*-
"""
REATK - AutoKaraoke Refactored
Copyright (C) 2024 

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import os
import json

# 镜像源配置
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 常量配置
MIN_DURATION = 0.06
SEARCH_WINDOW = 20
TIMEOUT_CHECK_INTERVAL = 0.5

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
    def __init__(self, config_file="settings.json"):
        self.config_file = config_file
        self.config = {}
        self.load()

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except (json.JSONDecodeError, IOError, UnicodeDecodeError) as e:
                print(f"Warning: Failed to load config file: {e}. Using default config.")
                self.config = {}
        else:
            self.config = {}

    def save(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value