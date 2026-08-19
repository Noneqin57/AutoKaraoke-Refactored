# -*- coding: utf-8 -*-
"""
高性能音频波形可视化组件 (WaveformWidget)
基于 QPainter 绘制现代 DAW 风格对称声波，支持即点即定位、选区高亮、局部缩放与字级标记。
"""
from typing import Optional, List, Tuple
import numpy as np
from PyQt6.QtWidgets import QWidget, QToolTip
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QMouseEvent, QLinearGradient, QPolygonF

from utils.time_utils import format_ms
from utils.waveform_extractor import extract_waveform_peaks
from ui.styles.theme_manager import theme_manager

class WaveformWidget(QWidget):
    seek_requested = pyqtSignal(int) # 发送点击或拖拽定位时间 (ms)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(56)
        self.setMaximumHeight(100)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.audio_path: str = ""
        self.duration_ms: int = 0
        self.current_position_ms: int = 0
        self.peaks: np.ndarray = np.zeros(0, dtype=np.float32)
        
        # 选区高亮区间 [start_ms, end_ms]
        self.highlight_start_ms: int = -1
        self.highlight_end_ms: int = -1
        
        # 局部放大视野 [zoom_start_ms, zoom_end_ms]，若为 None 则显示全曲
        self.zoom_start_ms: Optional[int] = None
        self.zoom_end_ms: Optional[int] = None
        
        # 字级时间标记 [t1_ms, t2_ms, ...]
        self.word_markers: List[int] = []
        
        self.is_dragging = False

    def load_audio(self, audio_path: str, duration_ms: int = 0):
        self.audio_path = audio_path
        peaks, dur_sec = extract_waveform_peaks(audio_path)
        self.peaks = peaks
        if duration_ms > 0:
            self.duration_ms = duration_ms
        elif dur_sec > 0:
            self.duration_ms = int(dur_sec * 1000)
        self.update()

    def set_duration(self, duration_ms: int):
        self.duration_ms = duration_ms
        self.update()

    def set_position(self, position_ms: int):
        self.current_position_ms = max(0, position_ms)
        self.update()

    def set_highlight_region(self, start_ms: int, end_ms: int):
        self.highlight_start_ms = start_ms
        self.highlight_end_ms = end_ms
        self.update()

    def set_zoom_range(self, start_ms: Optional[int], end_ms: Optional[int]):
        """设置局部放大区间（用于字级精细打轴模式）"""
        self.zoom_start_ms = start_ms
        self.zoom_end_ms = end_ms
        self.update()

    def set_word_markers(self, markers: List[int]):
        self.word_markers = markers
        self.update()

    def _get_visible_range(self) -> Tuple[int, int]:
        if self.zoom_start_ms is not None and self.zoom_end_ms is not None and self.zoom_end_ms > self.zoom_start_ms:
            return self.zoom_start_ms, self.zoom_end_ms
        total = self.duration_ms if self.duration_ms > 0 else (len(self.peaks) * 10 if len(self.peaks) > 0 else 1000)
        return 0, max(1, total)

    def _x_to_time_ms(self, x: float) -> int:
        w = max(1, self.width())
        start_ms, end_ms = self._get_visible_range()
        ratio = max(0.0, min(1.0, x / float(w)))
        return int(start_ms + ratio * (end_ms - start_ms))

    def _time_ms_to_x(self, time_ms: int) -> float:
        w = max(1, self.width())
        start_ms, end_ms = self._get_visible_range()
        if end_ms <= start_ms:
            return 0.0
        ratio = (time_ms - start_ms) / float(end_ms - start_ms)
        return ratio * w

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            seek_ms = self._x_to_time_ms(event.position().x())
            self.current_position_ms = seek_ms
            self.seek_requested.emit(seek_ms)
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos_x = event.position().x()
        hover_ms = self._x_to_time_ms(pos_x)
        QToolTip.showText(event.globalPosition().toPoint(), format_ms(hover_ms), self)
        
        if self.is_dragging:
            self.current_position_ms = hover_ms
            self.seek_requested.emit(hover_ms)
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False) # 条形波形禁用抗锯齿更清脆
        
        w = self.width()
        h = self.height()
        mid_y = h / 2.0

        is_dark = theme_manager.is_dark()
        bg_color = QColor(theme_manager.get_color("bg_preview", "#121316"))
        
        # 1. 绘制背景底板
        painter.fillRect(0, 0, w, h, bg_color)
        
        # 中轴参考线
        painter.setPen(QPen(QColor(theme_manager.get_color("border_light", "#2e323b")), 1, Qt.PenStyle.DashLine))
        painter.drawLine(0, int(mid_y), w, int(mid_y))

        start_ms, end_ms = self._get_visible_range()
        span_ms = max(1, end_ms - start_ms)

        # 2. 绘制当前句子选区高亮 (Region Highlight)
        if self.highlight_start_ms >= 0 and self.highlight_end_ms > self.highlight_start_ms:
            hx1 = self._time_ms_to_x(self.highlight_start_ms)
            hx2 = self._time_ms_to_x(self.highlight_end_ms)
            
            # 限制在屏幕可见区域
            hx1_clamp = max(0.0, min(float(w), hx1))
            hx2_clamp = max(0.0, min(float(w), hx2))
            
            if hx2_clamp > hx1_clamp:
                region_rect = QRectF(hx1_clamp, 0, hx2_clamp - hx1_clamp, h)
                region_color = QColor(64, 158, 255, 40 if is_dark else 30)
                painter.fillRect(region_rect, region_color)
                
                # 选区左右边界高亮线
                painter.setPen(QPen(QColor(64, 158, 255, 180), 1, Qt.PenStyle.SolidLine))
                if 0 <= hx1 <= w:
                    painter.drawLine(int(hx1), 0, int(hx1), h)
                if 0 <= hx2 <= w:
                    painter.drawLine(int(hx2), 0, int(hx2), h)

        # 3. 绘制声波条 (Waveform Bars)
        if len(self.peaks) > 0:
            playhead_x = self._time_ms_to_x(self.current_position_ms)
            
            unplayed_color = QColor(theme_manager.get_color("text_secondary", "#5d6373"))
            unplayed_color.setAlpha(120 if is_dark else 150)
            
            played_color = QColor(theme_manager.get_color("accent_primary", "#409eff"))
            
            # 将屏幕宽度分为条形（例如每条宽 2px，间隔 1px -> step 3px）
            step = 3
            total_bars = max(1, w // step)
            
            # 将 peaks 映射到 visible 区域
            total_samples = len(self.peaks)
            total_audio_ms = self.duration_ms if self.duration_ms > 0 else total_samples * 10
            
            for bar_idx in range(total_bars):
                bx = bar_idx * step
                bar_time_ms = start_ms + (bar_idx / float(total_bars)) * span_ms
                
                # 找到在 peaks 数组中的对应索引
                sample_idx = int((bar_time_ms / float(max(1, total_audio_ms))) * total_samples)
                sample_idx = max(0, min(total_samples - 1, sample_idx))
                
                val = float(self.peaks[sample_idx])
                # 计算条形高度（对称上下分布）
                bar_h = max(2.0, val * (mid_y - 4))
                
                # 区分已播放和未播放颜色
                if bx <= playhead_x:
                    painter.setPen(played_color)
                else:
                    painter.setPen(unplayed_color)

                painter.drawLine(int(bx), int(mid_y - bar_h), int(bx), int(mid_y + bar_h))

        # 4. 绘制字级时间标记线 (Word Markers)
        if self.word_markers:
            painter.setPen(QPen(QColor(103, 194, 58, 200), 1, Qt.PenStyle.DashDotLine))
            for wm in self.word_markers:
                wx = self._time_ms_to_x(wm)
                if 0 <= wx <= w:
                    painter.drawLine(int(wx), 0, int(wx), h)

        # 5. 绘制动态播放头游标 (Playhead Cursor)
        playhead_x = self._time_ms_to_x(self.current_position_ms)
        if 0 <= playhead_x <= w:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            
            # 游标垂直线
            painter.setPen(QPen(QColor("#ffffff"), 2))
            painter.drawLine(int(playhead_x), 0, int(playhead_x), h)
            
            # 顶部三角游标把手
            head_brush = QBrush(QColor("#ffffff"))
            painter.setBrush(head_brush)
            painter.setPen(Qt.PenStyle.NoPen)
            triangle = QPolygonF([
                QPointF(playhead_x - 5, 0),
                QPointF(playhead_x + 5, 0),
                QPointF(playhead_x, 7)
            ])
            painter.drawPolygon(triangle)
            
            # 底部三角游标把手
            triangle_bottom = QPolygonF([
                QPointF(playhead_x - 5, h),
                QPointF(playhead_x + 5, h),
                QPointF(playhead_x, h - 7)
            ])
            painter.drawPolygon(triangle_bottom)
