# -*- coding: utf-8 -*-
"""
应用设置对话框 (SettingsDialog)
包装 SettingsPage 视图，支持独立弹窗调起与管理。
"""
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
from qfluentwidgets import PrimaryPushButton, FluentIcon as FIF
from ui.pages.settings_page import SettingsPage

class SettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("系统设置 - AutoKaraoke")
        self.resize(680, 560)
        
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        
        self.settings_page = SettingsPage(config_manager, self)
        lay.addWidget(self.settings_page, 1)
        
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        close_btn = PrimaryPushButton("完成", self, FIF.ACCEPT)
        close_btn.clicked.connect(self.accept)
        btn_bar.addWidget(close_btn)
        lay.addLayout(btn_bar)
