# -*- coding: utf-8 -*-
"""
高精度可点击跳转进度条 (ClickableSlider)
支持鼠标点击精准定位与悬浮时间气泡预览。
"""
from PyQt6.QtWidgets import QSlider, QToolTip, QStyle
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent

from utils.time_utils import format_ms

class ClickableSlider(QSlider):
    clicked_position = pyqtSignal(int)

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            val = self._pixel_pos_to_range_value(event.position().x())
            self.setValue(val)
            self.sliderMoved.emit(val)
            self.clicked_position.emit(val)
            event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # 悬浮显示时间 ToolTip
        val = self._pixel_pos_to_range_value(event.position().x())
        time_text = format_ms(val)
        QToolTip.showText(event.globalPosition().toPoint(), time_text, self)
        super().mouseMoveEvent(event)

    def _pixel_pos_to_range_value(self, pos_x: float) -> int:
        opt = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            None,
            QStyle.SubControl.SC_SliderGroove,
            self
        )
        groove_width = opt.width() if opt.width() > 0 else self.width()
        pos_x = max(0, min(pos_x, groove_width))
        ratio = pos_x / groove_width
        val = int(self.minimum() + ratio * (self.maximum() - self.minimum()))
        return max(self.minimum(), min(self.maximum(), val))
