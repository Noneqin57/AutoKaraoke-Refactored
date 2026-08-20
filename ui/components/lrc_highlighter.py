# -*- coding: utf-8 -*-
"""
增强型 LRC 语法高亮器 (EnhancedLrcHighlighter)
支持行级时间戳、逐字内嵌时间戳、元数据标签与动态主题适配。
"""
import re
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from ui.styles.theme_manager import theme_manager

class EnhancedLrcHighlighter(QSyntaxHighlighter):
    def __init__(self, document, parent=None):
        super().__init__(document)
        self._parent = parent
        self.update_formats()
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _theme_name):
        self.update_formats()
        self.rehighlight()

    def update_formats(self):
        is_dark = theme_manager.is_dark()
        accent = theme_manager.accent_color
        
        # 行级时间戳 [00:12.345] -> 主色珊瑚粉
        self.line_time_format = QTextCharFormat()
        self.line_time_format.setForeground(QColor(accent))
        self.line_time_format.setFontWeight(QFont.Weight.Bold)

        # 逐字内嵌时间戳 <00:12.345> 或内部的 [00:12.345] -> 柔和薄荷绿
        self.word_time_format = QTextCharFormat()
        self.word_time_format.setForeground(QColor("#67c23a" if is_dark else "#389e0d"))
        self.word_time_format.setFontWeight(QFont.Weight.Medium)

        # 元数据标签 [ti:Song Title] -> 琥珀金
        self.tag_format = QTextCharFormat()
        self.tag_format.setForeground(QColor("#e6a23c" if is_dark else "#d46b08"))
        self.tag_format.setFontItalic(True)

    def highlightBlock(self, text: str):
        if not text:
            return

        # 1. 匹配元数据标签 [ti:...], [ar:...], [al:...], [by:...], [offset:...]
        meta_pattern = re.compile(r'\[(ti|ar|al|by|offset|length|re|ve):[^\]]*\]', re.IGNORECASE)
        for match in meta_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.tag_format)

        # 2. 匹配尖括号逐字时间戳 <00:00.000>
        angle_pattern = re.compile(r'<\d{2}:\d{2}\.\d{2,3}>')
        for match in angle_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), self.word_time_format)

        # 3. 匹配方括号时间戳 [00:00.000]
        square_pattern = re.compile(r'\[\d{2}:\d{2}\.\d{2,3}\]')
        matches = list(square_pattern.finditer(text))
        for i, match in enumerate(matches):
            if i == 0 and match.start() == 0:
                # 行首时间戳 -> 行级时间戳
                self.setFormat(match.start(), match.end() - match.start(), self.line_time_format)
            else:
                # 行内的逐字时间戳
                self.setFormat(match.start(), match.end() - match.start(), self.word_time_format)
