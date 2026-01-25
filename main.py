# -*- coding: utf-8 -*-
"""
AutoKaraoke Refactored
功能：Whisper 自动歌词生成、双语对齐、自定义 Prompt、歌词打轴
"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import LyricsGenApp


def main():
    """应用程序主入口"""
    app = QApplication(sys.argv)
    
    # 高DPI支持
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
        app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    except AttributeError:
        pass
    
    # 创建并显示主窗口
    window = LyricsGenApp()
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())