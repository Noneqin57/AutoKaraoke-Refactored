# -*- coding: utf-8 -*-
"""
模型管理页面 (ModelPage)
基于 QFluentWidgets Fluent Design 风格构建，提供 OpenAI 官方 Whisper 模型（tiny ~ large-v3）
的状态检测、CDN 直连极速下载、断点续传、进度追踪与本地文件清理。
"""
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QHeaderView, QTableWidgetItem)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject

from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton, 
                            TransparentPushButton, TableWidget, ProgressBar, 
                            FluentIcon as FIF, TitleLabel, CaptionLabel, 
                            StrongBodyLabel, InfoBar, InfoBarPosition, InfoBadge)

from core.model_manager import DownloadStopped, ModelManager, ModelInfo, ModelDownloader
from config import ConfigManager
from ui.styles.theme_manager import theme_manager

class DownloadWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str) # success, msg

    def __init__(self, model_info: ModelInfo):
        super().__init__()
        self.model_info = model_info
        self.downloader = None

    def run(self):
        try:
            self.downloader = ModelDownloader(self.model_info, self._callback)
            self.downloader.start()
            self.finished.emit(True, "Success")
        except DownloadStopped:
            self.finished.emit(False, "Stopped")
        except Exception as e:
            self.finished.emit(False, str(e))

    def _callback(self, percent, msg):
        self.progress.emit(percent, msg)

    def stop(self):
        if self.downloader:
            self.downloader.stop()


class ModelPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelPage")
        self.config = ConfigManager()
        
        model_dir = self.config.get("MODEL_DIR") or "models"
        if not os.path.isabs(model_dir):
            model_dir = os.path.abspath(model_dir)
            
        self.manager = ModelManager(model_dir)
        self.model_list = []
        self.download_threads = {} # row -> (thread, worker)

        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(28, 20, 28, 24)
        main_lay.setSpacing(14)

        # 1. 顶部 Header
        header_lay = QHBoxLayout()
        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        self.title_lbl = TitleLabel("模型管理")
        sub_lbl = CaptionLabel("支持 OpenAI Whisper 语音识别模型与 MSST/RoFormer 人声提取模型管理、断点续传与本地存储。")
        sub_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")
        t_box.addWidget(self.title_lbl)
        t_box.addWidget(sub_lbl)
        header_lay.addLayout(t_box)
        header_lay.addStretch()

        self.btn_refresh = PushButton("刷新列表", self, FIF.SYNC)
        self.btn_refresh.clicked.connect(self.refresh_list)
        header_lay.addWidget(self.btn_refresh)
        main_lay.addLayout(header_lay)

        # 2. 模型列表表格卡片
        card = CardWidget(self)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(12, 12, 12, 12)
        card_lay.setSpacing(8)

        self.table = TableWidget(self)
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["模型名称", "模型类型", "本地状态", "下载进度", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        
        card_lay.addWidget(self.table)
        main_lay.addWidget(card, 1)

    def refresh_list(self):
        self.model_list = self.manager.get_model_list()
        self.table.setRowCount(len(self.model_list))

        for row, info in enumerate(self.model_list):
            self.table.setRowHeight(row, 50)
            
            # 0. 模型名称
            name_item = QTableWidgetItem(f" {info.name}")
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, name_item)

            # 1. 类型
            type_item = QTableWidgetItem(info.type)
            type_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 1, type_item)

            # 2. 状态
            status_str = "已就绪" if info.is_downloaded else "未下载"
            status_item = QTableWidgetItem(status_str)
            status_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            if info.is_downloaded:
                status_item.setForeground(theme_manager.get_qcolor("accent_primary"))
            self.table.setItem(row, 2, status_item)

            # 3. 进度条
            pbar = ProgressBar(self.table)
            pbar.setRange(0, 100)
            pbar.setValue(100 if info.is_downloaded else 0)
            self.table.setCellWidget(row, 3, pbar)

            # 4. 操作按钮容器
            act_widget = QWidget()
            act_lay = QHBoxLayout(act_widget)
            act_lay.setContentsMargins(6, 4, 6, 4)
            act_lay.setSpacing(6)

            if info.is_downloaded:
                del_btn = PushButton("删除", act_widget, FIF.DELETE)
                del_btn.setFixedHeight(30)
                del_btn.clicked.connect(lambda ch, r=row: self.delete_model(r))
                act_lay.addWidget(del_btn)
            else:
                down_btn = PrimaryPushButton("下载", act_widget, FIF.DOWNLOAD)
                down_btn.setFixedHeight(30)
                down_btn.clicked.connect(lambda ch, r=row: self.start_download(r))
                act_lay.addWidget(down_btn)

            self.table.setCellWidget(row, 4, act_widget)

    def start_download(self, row: int):
        if row in self.download_threads:
            return

        info = self.model_list[row]
        worker = DownloadWorker(info)
        thread = QThread()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(lambda pct, msg, r=row: self.update_download_progress(r, pct, msg))
        worker.finished.connect(lambda success, msg, r=row: self.on_download_finished(r, success, msg))

        self.download_threads[row] = (thread, worker)
        thread.start()

        # 更新状态为下载中
        self.table.item(row, 2).setText("下载中...")
        
        act_widget = QWidget()
        act_lay = QHBoxLayout(act_widget)
        act_lay.setContentsMargins(6, 4, 6, 4)
        stop_btn = PushButton("暂停", act_widget, FIF.PAUSE)
        stop_btn.setFixedHeight(30)
        stop_btn.clicked.connect(lambda ch, r=row: self.stop_download(r))
        act_lay.addWidget(stop_btn)
        self.table.setCellWidget(row, 4, act_widget)

        InfoBar.info(
            title="开始下载",
            content=f"正在连接 OpenAI CDN 下载 {info.name} 模型...",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3000
        )

    def stop_download(self, row: int):
        if row in self.download_threads:
            thread, worker = self.download_threads[row]
            worker.stop()

    def update_download_progress(self, row: int, percent: int, msg: str):
        pbar = self.table.cellWidget(row, 3)
        if isinstance(pbar, ProgressBar):
            pbar.setValue(percent)
        if self.table.item(row, 2):
            self.table.item(row, 2).setText(f"{percent}%")

    def on_download_finished(self, row: int, success: bool, msg: str):
        if row in self.download_threads:
            thread, worker = self.download_threads[row]
            thread.quit()
            thread.wait()
            del self.download_threads[row]

        info = self.model_list[row]
        if success:
            InfoBar.success(
                title="下载完成",
                content=f"模型 {info.name} 已成功就绪！",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3500
            )
        elif msg == "Stopped":
            InfoBar.warning(
                title="下载已暂停",
                content=f"模型 {info.name} 下载已暂停，支持断点续传。",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500
            )
        else:
            InfoBar.error(
                title="下载失败",
                content=f"模型 {info.name} 下载异常: {msg}",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=4000
            )

        self.refresh_list()

    def delete_model(self, row: int):
        info = self.model_list[row]
        try:
            self.manager.delete_model(info)
            InfoBar.success(
                title="删除成功",
                content=f"已成功移除本地模型: {info.name}",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500
            )
        except Exception as e:
            InfoBar.error(
                title="删除失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000
            )
        self.refresh_list()
