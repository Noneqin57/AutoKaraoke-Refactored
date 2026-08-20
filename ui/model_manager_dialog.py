# -*- coding: utf-8 -*-
"""
Whisper 模型管理对话框 (ModelManagerDialog)
包装 ModelPage 视图，支持独立弹窗调起与管理。
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import PrimaryPushButton, FluentIcon as FIF
from ui.pages.model_page import ModelPage

class ModelManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("模型管理 - AutoKaraoke")
        self.resize(900, 580)
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        
        self.model_page = ModelPage(self)
        lay.addWidget(self.model_page, 1)
        
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        close_btn = PrimaryPushButton("完成", self, FIF.ACCEPT)
        close_btn.clicked.connect(self.accept)
        btn_bar.addWidget(close_btn)
        lay.addLayout(btn_bar)
