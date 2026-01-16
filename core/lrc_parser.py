# -*- coding: utf-8 -*-
import re
from typing import List, Dict
from utils.time_utils import parse_time_tag

class LrcParser:
    def __init__(self):
        self.headers: List[str] = []
        self.lines_text: List[str] = []
        self.translations: Dict[int, List[str]] = {}
        self.lines_timestamps: List[float] = [] # 存储每一行的原始时间戳 (秒)
        # 匹配制作人信息等非歌词行
        self.credits_pattern = re.compile(
            r"^(作|编|词|曲|演|唱|混|录|母|制|监|统|出|绘|调|和|吉|贝|鼓|弦|管|Lyr|Com|Arr|Sin|Voc|Mix|Mas|Pro|Art|Cov|Gui|Bas|Dru|Str)"
            r".{0,40}"
            r"([:：]|\s|-)", re.IGNORECASE
        )
        # 支持 [mm:ss], [mm:ss.xx], [mm:ss:xx]
        self.time_tag_pattern = re.compile(r'^\[\d{1,2}:\d{1,2}(?:[\.:]\d{1,3})?\]')
        # 分组1: 时间标签, 分组2: 内容
        self.tag_content_pattern = re.compile(r'^(\[\d{1,2}:\d{1,2}(?:[\.:]\d{1,3})?\])(.*)')
        # 用于移除行内所有时间标签
        self.remove_tags_pattern = re.compile(r'\[\d{1,2}:\d{1,2}(?:[\.:]\d{1,3})?\]')
        self.remove_html_pattern = re.compile(r'<.*?>')

    def parse(self, content: str, ext: str) -> str:
        self.headers = []
        self.lines_text = []
        self.translations = {}
        
        content = content.lstrip('\ufeff')
        lines = content.splitlines()
        
        last_time_tag = None
        current_index = -1
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # 如果是头部标签 [ti:xxx] 等，通常不符合 time_tag_pattern (因为那是 key:value)
            # 但要注意 [00:12] 这种短标签。
            # 标准头部标签: [ti:Title], [ar:Artist]. 
            # 我们的 time_tag_pattern 要求数字开头。
            if line.startswith('[') and not self.time_tag_pattern.match(line):
                self.headers.append(line)
                continue
            
            match = self.tag_content_pattern.match(line)
            text_only = ""
            time_tag = ""
            
            if match:
                time_tag = match.group(1)
                text_content = match.group(2).strip()
                text_only = self.remove_tags_pattern.sub('', text_content)
                text_only = self.remove_html_pattern.sub('', text_only).strip()
            else:
                # 尝试移除行内所有标签
                text_only = self.remove_tags_pattern.sub('', line)
                text_only = self.remove_html_pattern.sub('', text_only).strip()
            
            if not text_only: continue
            
            if self.credits_pattern.match(text_only):
                self.headers.append(line)
                continue
            
            # 翻译行判定：如果时间标签相同，且已经有上一行
            if time_tag and time_tag == last_time_tag and current_index >= 0:
                if current_index not in self.translations:
                    self.translations[current_index] = []
                self.translations[current_index].append(text_only)
            else:
                self.lines_text.append(text_only)
                
                # 解析并存储时间戳
                ts_val = -1.0
                if time_tag:
                    try:
                        ts_val = parse_time_tag(time_tag) / 1000.0 # 转换为秒
                    except:
                        ts_val = -1.0
                self.lines_timestamps.append(ts_val)
                
                current_index += 1
                last_time_tag = time_tag
        
        return "\n".join(self.lines_text)
