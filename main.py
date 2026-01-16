# -*- coding: utf-8 -*-
"""
AutoKaraoke Refactored
功能：Whisper 自动歌词生成、双语对齐、自定义 Prompt、歌词打轴
"""
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import LyricsGenApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try: app.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    except: pass
    window = LyricsGenApp()
    window.show()
    sys.exit(app.exec())