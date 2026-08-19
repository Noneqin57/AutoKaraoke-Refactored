# -*- coding: utf-8 -*-
"""
AutoKaraoke Refactored
功能：Whisper 自动歌词生成、双语对齐、自定义 Prompt、歌词打轴
"""
import multiprocessing
import sys
from PyQt6.QtWidgets import QApplication

from ui.main_window import LyricsGenApp


def main():
    """应用程序主入口"""
    # 支持 PyInstaller 等打包后运行 multiprocessing（Windows spawn）
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    
    # 创建并显示主窗口
    window = LyricsGenApp()
    window.show()
    
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())