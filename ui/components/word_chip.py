# -*- coding: utf-8 -*-
"""
字卡与逐字时间轴控件 (WordChip & WordChipRow)
用于打轴编辑器中展示逐字卡片（字符 + 时间戳），支持播放时实时平滑点亮与点击微调。
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QScrollArea, QFrame, QInputDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QCursor

from utils.time_utils import format_ms
from ui.styles.theme_manager import theme_manager

class WordChip(QFrame):
    """
    单个字卡控件：上部为字符 (加大字号)，下部为微型时间戳
    """
    clicked = pyqtSignal(int) # token_index
    double_clicked = pyqtSignal(int)

    def __init__(self, token_index: int, char: str, time_ms: int, parent=None):
        super().__init__(parent)
        self.token_index = token_index
        self.char = char
        self.time_ms = time_ms
        self.is_active = False
        self.is_edited = False
        
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedWidth(64)
        self.setFixedHeight(64)
        self.setup_ui()
        self.update_style()

    def setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.char_lbl = QLabel(self.char)
        self.char_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_char = QFont("Sarasa Gothic SC", 15, QFont.Weight.Bold)
        font_char.setStyleHint(QFont.StyleHint.SansSerif)
        self.char_lbl.setFont(font_char)

        # 格式化时间戳 (显示完整的 mm:ss.xx，避免跨分钟时丢失分导致秒数回零感)
        compact_time = self._format_chip_time(self.time_ms)
            
        self.time_lbl = QLabel(compact_time)
        self.time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_time = QFont("Geist Mono", 8)
        font_time.setStyleHint(QFont.StyleHint.Monospace)
        self.time_lbl.setFont(font_time)

        lay.addWidget(self.char_lbl)
        lay.addWidget(self.time_lbl)

    @staticmethod
    def _format_chip_time(time_ms: int) -> str:
        time_str = format_ms(time_ms)
        if len(time_str) >= 8:
            return time_str[:8] # 01:23.45 (完整 mm:ss.xx)
        return time_str

    def set_time_ms(self, new_time_ms: int, edited: bool = True):
        self.time_ms = new_time_ms
        self.is_edited = edited
        compact_time = self._format_chip_time(self.time_ms)
        self.time_lbl.setText(compact_time)
        self.update_style()

    def set_active(self, active: bool):
        if self.is_active != active:
            self.is_active = active
            self.update_style()

    def update_style(self):
        t = theme_manager.get_tokens()
        accent = theme_manager.accent_color
        
        if self.is_active:
            # 激活/当前播放态：主色珊瑚粉填充，文字纯白
            self.setStyleSheet(f"""
                WordChip {{
                    background-color: {accent};
                    border: 1px solid {accent};
                    border-radius: 10px;
                }}
                QLabel {{
                    color: #FFFFFF;
                    background: transparent;
                }}
            """)
        else:
            # 常规态：卡片底色，细描边
            border_color = t['border_normal'] if not self.is_edited else accent
            bg_color = t['bg_card']
            text_char = t['text_primary']
            text_time = t['text_secondary']
            
            self.setStyleSheet(f"""
                WordChip {{
                    background-color: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 10px;
                }}
                WordChip:hover {{
                    border: 1.5px solid {accent};
                    background-color: {t['bg_hover']};
                }}
            """)
            self.char_lbl.setStyleSheet(f"color: {text_char}; background: transparent;")
            self.time_lbl.setStyleSheet(f"color: {text_time}; background: transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.token_index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.token_index)
        super().mouseDoubleClickEvent(event)


class WordChipRow(QScrollArea):
    """
    字卡水平滚动容器，支持随播放进度平滑滚动居中当前字
    """
    chip_clicked = pyqtSignal(int)
    chip_double_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFixedHeight(96)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.lay = QHBoxLayout(self.container)
        self.lay.setContentsMargins(12, 8, 12, 8)
        self.lay.setSpacing(8)
        self.lay.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setWidget(self.container)

        self.chips = []
        self.active_index = -1

    def set_tokens(self, tokens: list):
        """
        加载 token 列表：[{'char': '夜', 'time': 12300, 'edited': False}, ...]
        """
        # 清空现有字卡
        for chip in self.chips:
            self.lay.removeWidget(chip)
            chip.deleteLater()
        self.chips.clear()
        self.active_index = -1

        for i, tok in enumerate(tokens):
            chip = WordChip(i, tok['char'], tok['time'], self.container)
            if tok.get('edited', False):
                chip.is_edited = True
                chip.update_style()
            chip.clicked.connect(self.chip_clicked.emit)
            chip.double_clicked.connect(self.chip_double_clicked.emit)
            self.lay.addWidget(chip)
            self.chips.append(chip)

        self.lay.addStretch()

    def update_token_time(self, index: int, new_time_ms: int, edited: bool = True):
        if 0 <= index < len(self.chips):
            self.chips[index].set_time_ms(new_time_ms, edited)

    def highlight_index(self, index: int):
        if index == self.active_index:
            return
        
        # 取消上一个
        if 0 <= self.active_index < len(self.chips):
            self.chips[self.active_index].set_active(False)
            
        self.active_index = index
        
        # 激活当前
        if 0 <= self.active_index < len(self.chips):
            active_chip = self.chips[self.active_index]
            active_chip.set_active(True)
            self.ensureWidgetVisible(active_chip, 100, 0)
