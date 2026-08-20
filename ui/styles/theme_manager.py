# -*- coding: utf-8 -*-
"""
全局主题管理器 (Theme Manager)
提供与 QFluentWidgets 深度联动的主题切换、QSS 生成、珊瑚粉 (#F25378) 品牌色注入与广播能力。
"""
import logging
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QColor

try:
    from qfluentwidgets import setTheme, Theme, setCustomThemeColor, ThemeColor
    HAS_FLUENT = True
except ImportError:
    HAS_FLUENT = False

from ui.styles.tokens import DARK_THEME_TOKENS, LIGHT_THEME_TOKENS

logger = logging.getLogger(__name__)

class ThemeManager(QObject):
    theme_changed = pyqtSignal(str) # 'dark', 'light', 'auto'

    def __init__(self, default_theme: str = "dark"):
        super().__init__()
        self._current_theme = default_theme.lower()
        if self._current_theme not in ("dark", "light", "auto"):
            self._current_theme = "dark"
        self._accent_color = "#F25378" # 珊瑚粉主色

    @property
    def current_theme(self) -> str:
        return self._current_theme

    @property
    def accent_color(self) -> str:
        return self._accent_color

    def is_dark(self) -> bool:
        if self._current_theme == "light":
            return False
        return True # dark or auto fallback

    def get_tokens(self) -> dict:
        return DARK_THEME_TOKENS if self.is_dark() else LIGHT_THEME_TOKENS

    def get_color(self, token_name: str, fallback: str = "#F25378") -> str:
        return self.get_tokens().get(token_name, fallback)

    def get_qcolor(self, token_name: str, fallback: str = "#F25378") -> QColor:
        color_str = self.get_color(token_name, fallback)
        return QColor(color_str)

    def set_theme(self, theme_name: str):
        theme_name = theme_name.lower()
        if theme_name not in ("dark", "light", "auto"):
            theme_name = "dark"
            
        self._current_theme = theme_name
        logger.info("Theme switched to: %s", theme_name)
        self.apply_to_app()
        self.theme_changed.emit(theme_name)

    def apply_to_app(self):
        # 1. 注入 QFluentWidgets 主题引擎
        if HAS_FLUENT:
            try:
                setCustomThemeColor(self._accent_color, self._accent_color)
                if self._current_theme == "dark":
                    setTheme(Theme.DARK)
                elif self._current_theme == "light":
                    setTheme(Theme.LIGHT)
                elif self._current_theme == "auto":
                    setTheme(Theme.AUTO)
            except Exception as e:
                logger.warning("Failed to apply fluent theme: %s", e)

        # 2. 注入全局补偿样式表
        app = QApplication.instance()
        if app:
            stylesheet = self.generate_stylesheet()
            app.setStyleSheet(stylesheet)

    def generate_stylesheet(self) -> str:
        t = self.get_tokens()
        
        return f"""
            /* ===== 全局基础设置 ===== */
            QWidget {{
                font-family: 'Sarasa Gothic SC', 'Microsoft YaHei UI', 'PingFang SC', 'Segoe UI', sans-serif;
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
                border-radius: 12px;
            }}

            QWidget#cardHead {{
                background-color: {t['bg_card_head']};
                border-bottom: 1px solid {t['border_light']};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}

            QLabel#cardTitle {{
                font-weight: 600;
                font-size: 13px;
                color: {t['text_primary']};
            }}

            QFrame#header {{
                background-color: {t['bg_card']};
                border: 1px solid {t['border_light']};
                border-radius: 12px;
            }}

            QLabel#appTitle {{
                color: {t['text_primary']};
                font-size: 18px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }}

            QLabel#appSubtitle {{
                color: {t['text_secondary']};
                font-size: 12px;
            }}

            /* ===== 输入与输出文本框 ===== */
            QTextEdit, QPlainTextEdit {{
                background-color: {t['bg_input']};
                color: {t['text_primary']};
                border: 1px solid {t['border_normal']};
                border-radius: 10px;
                padding: 10px;
                font-family: 'Geist Mono', Consolas, 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.4;
                selection-background-color: {t['accent_primary']};
                selection-color: #ffffff;
            }}
            
            QTextEdit:focus, QPlainTextEdit:focus {{
                border: 1.5px solid {t['accent_primary']};
            }}

            /* ===== 按钮控件 ===== */
            QPushButton {{
                background-color: {t['bg_card']};
                color: {t['text_primary']};
                border: 1px solid {t['border_normal']};
                border-radius: 8px;
                padding: 6px 14px;
                font-weight: 500;
                font-size: 13px;
            }}

            QPushButton:hover {{
                background-color: {t['bg_hover']};
                border-color: {t['border_hover']};
            }}

            QPushButton:pressed {{
                background-color: {t['border_light']};
            }}

            QPushButton#primary {{
                background-color: {t['accent_primary']};
                color: #ffffff;
                border: none;
                font-weight: 600;
            }}

            QPushButton#primary:hover {{
                background-color: {t['accent_primary_hover']};
            }}

            QPushButton#primary:pressed {{
                background-color: {t['accent_primary_active']};
            }}

            /* ===== 分割条 ===== */
            QSplitter::handle {{
                background-color: {t['border_light']};
                border-radius: 2px;
            }}
            QSplitter::handle:hover {{
                background-color: {t['accent_primary']};
            }}

            /* ===== 滚动条 ===== */
            QScrollBar:vertical {{
                background: transparent;
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['border_hover']};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['accent_primary']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            QScrollBar:horizontal {{
                background: transparent;
                height: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: {t['border_hover']};
                min-width: 24px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {t['accent_primary']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
        """

theme_manager = ThemeManager()
