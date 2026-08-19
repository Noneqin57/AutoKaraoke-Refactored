# -*- coding: utf-8 -*-
"""
全局主题管理器 (Theme Manager)
提供主题切换、QSS 生成与广播、颜色获取等能力。
"""
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor, QPalette

from ui.styles.tokens import DARK_THEME_TOKENS, LIGHT_THEME_TOKENS

logger = logging.getLogger(__name__)

class ThemeManager(QObject):
    theme_changed = pyqtSignal(str) # 'dark' or 'light'

    def __init__(self, default_theme: str = "dark"):
        super().__init__()
        self._current_theme = default_theme.lower()
        if self._current_theme not in ("dark", "light"):
            self._current_theme = "dark"

    @property
    def current_theme(self) -> str:
        return self._current_theme

    def is_dark(self) -> bool:
        return self._current_theme == "dark"

    def get_tokens(self) -> dict:
        return DARK_THEME_TOKENS if self.is_dark() else LIGHT_THEME_TOKENS

    def get_color(self, token_name: str, fallback: str = "#ffffff") -> str:
        return self.get_tokens().get(token_name, fallback)

    def get_qcolor(self, token_name: str, fallback: str = "#ffffff") -> QColor:
        color_str = self.get_color(token_name, fallback)
        return QColor(color_str)

    def set_theme(self, theme_name: str):
        theme_name = theme_name.lower()
        if theme_name not in ("dark", "light"):
            theme_name = "dark"
        if self._current_theme != theme_name:
            self._current_theme = theme_name
            logger.info("Theme switched to: %s", theme_name)
            self.apply_to_app()
            self.theme_changed.emit(theme_name)

    def apply_to_app(self):
        app = QApplication.instance()
        if app:
            stylesheet = self.generate_stylesheet()
            app.setStyleSheet(stylesheet)

    def generate_stylesheet(self) -> str:
        t = self.get_tokens()
        
        return f"""
            /* ===== 全局基础设置 ===== */
            QWidget {{
                font-family: 'Microsoft YaHei', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 13px;
                color: {t['text_primary']};
            }}
            
            QMainWindow, QDialog, QWidget#central {{
                background-color: {t['bg_window']};
            }}

            QLabel {{
                color: {t['text_primary']};
                background: transparent;
            }}

            /* ===== 卡片与容器 ===== */
            QFrame#card {{
                background-color: {t['bg_card']};
                border: 1px solid {t['border_light']};
                border-radius: 10px;
            }}

            QWidget#cardHead {{
                background-color: {t['bg_card_head']};
                border-bottom: 1px solid {t['border_light']};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}

            QLabel#cardTitle {{
                font-weight: bold;
                font-size: 13px;
                color: {t['text_primary']};
            }}

            QFrame#header {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1a6be6, stop:1 #409eff);
                border: none;
                border-radius: 10px;
            }}

            QLabel#appTitle {{
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }}

            /* ===== 输入与输出文本框 ===== */
            QTextEdit, QPlainTextEdit {{
                background-color: {t['bg_input']};
                color: {t['text_primary']};
                border: 1px solid {t['border_normal']};
                border-radius: 8px;
                padding: 10px;
                font-family: 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.4;
                selection-background-color: {t['accent_primary']};
                selection-color: #ffffff;
            }}

            QTextEdit:focus, QPlainTextEdit:focus {{
                border: 1px solid {t['border_focus']};
            }}

            QFrame#card QTextEdit {{
                border: none;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
            }}

            QFrame#card QTextEdit#outputBox {{
                background-color: {t['bg_output']};
                color: {t['text_output']};
            }}

            /* ===== 按钮控件 ===== */
            QPushButton {{
                background-color: {t['accent_primary']};
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: bold;
                font-size: 13px;
            }}

            QPushButton:hover {{
                background-color: {t['accent_primary_hover']};
            }}

            QPushButton:pressed {{
                background-color: {t['accent_primary_active']};
            }}

            QPushButton:disabled {{
                background-color: {t['accent_primary_disabled']};
                color: rgba(255, 255, 255, 0.4);
            }}

            QPushButton#secondary {{
                background-color: transparent;
                color: {t['accent_danger']};
                border: 1px solid {t['accent_danger']};
            }}

            QPushButton#secondary:hover {{
                background-color: rgba(245, 108, 108, 0.15);
            }}

            QPushButton#secondary:disabled {{
                border-color: {t['border_normal']};
                color: {t['text_secondary']};
            }}

            QPushButton#warning {{
                background-color: {t['accent_warning']};
                color: #ffffff;
            }}

            QPushButton#warning:hover {{
                background-color: {t['accent_warning_hover']};
            }}

            QPushButton#danger {{
                background-color: {t['accent_danger']};
                color: #ffffff;
            }}

            QPushButton#danger:hover {{
                background-color: {t['accent_danger_hover']};
            }}

            QPushButton#success {{
                background-color: {t['accent_success']};
                color: #ffffff;
            }}

            QPushButton#success:hover {{
                background-color: {t['accent_success_hover']};
            }}

            QPushButton#info {{
                background-color: {t['accent_info']};
                color: #ffffff;
            }}

            QPushButton#info:hover {{
                background-color: {t['accent_info_hover']};
            }}

            /* ===== 表单输入控件 ===== */
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
                background-color: {t['bg_input']};
                color: {t['text_primary']};
                border: 1px solid {t['border_normal']};
                border-radius: 6px;
                padding: 6px 10px;
            }}

            QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
                border-color: {t['border_hover']};
            }}

            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
                border-color: {t['border_focus']};
            }}

            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}

            QComboBox QAbstractItemView {{
                background-color: {t['bg_card']};
                color: {t['text_primary']};
                border: 1px solid {t['border_normal']};
                selection-background-color: {t['accent_primary']};
                selection-color: #ffffff;
                padding: 4px;
                border-radius: 6px;
            }}

            /* ===== 表格控件 ===== */
            QTableWidget {{
                background-color: {t['bg_input']};
                color: {t['text_primary']};
                border: 1px solid {t['border_normal']};
                border-radius: 8px;
                gridline-color: {t['border_light']};
                alternate-background-color: {t['bg_table_alt']};
                selection-background-color: {t['highlight_active_row']};
                selection-color: {t['highlight_active_text']};
            }}

            QHeaderView::section {{
                background-color: {t['bg_card_head']};
                color: {t['text_regular']};
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid {t['border_normal']};
                border-right: 1px solid {t['border_light']};
                font-weight: bold;
            }}

            /* ===== 进度条控件 ===== */
            QProgressBar {{
                border: none;
                border-radius: 4px;
                background-color: {t['border_normal']};
                text-align: center;
                color: {t['text_primary']};
                font-size: 11px;
            }}

            QProgressBar::chunk {{
                background-color: {t['accent_primary']};
                border-radius: 4px;
            }}

            /* ===== 滑块控件 ===== */
            QSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: {t['border_normal']};
                border-radius: 3px;
            }}

            QSlider::sub-page:horizontal {{
                background: {t['accent_primary']};
                border-radius: 3px;
            }}

            QSlider::handle:horizontal {{
                background: #ffffff;
                border: 2px solid {t['accent_primary']};
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}

            QSlider::handle:horizontal:hover {{
                background: {t['accent_primary_hover']};
                border-color: #ffffff;
            }}

            /* ===== 复选框控件 ===== */
            QCheckBox {{
                spacing: 8px;
                color: {t['text_regular']};
            }}

            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {t['border_normal']};
                border-radius: 4px;
                background-color: {t['bg_input']};
            }}

            QCheckBox::indicator:hover {{
                border-color: {t['accent_primary']};
            }}

            QCheckBox::indicator:checked {{
                background-color: {t['accent_primary']};
                border-color: {t['accent_primary']};
            }}

            /* ===== 分组框与Tab控件 ===== */
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {t['border_normal']};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 14px;
            }}

            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
                color: {t['text_primary']};
            }}

            QTabWidget::pane {{
                border: 1px solid {t['border_normal']};
                border-radius: 8px;
                background-color: {t['bg_card']};
                top: -1px;
            }}

            QTabBar::tab {{
                background: {t['bg_input']};
                color: {t['text_secondary']};
                border: 1px solid {t['border_normal']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 8px 16px;
                margin-right: 4px;
            }}

            QTabBar::tab:selected {{
                background: {t['bg_card']};
                color: {t['accent_primary']};
                font-weight: bold;
            }}

            QSplitter::handle {{
                background-color: {t['bg_window']};
                width: 8px;
            }}

            QScrollBar:vertical {{
                background: {t['bg_window']};
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }}

            QScrollBar::handle:vertical {{
                background: {t['border_normal']};
                min-height: 24px;
                border-radius: 4px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: {t['border_hover']};
            }}

            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """

# 全局单例
theme_manager = ThemeManager()
