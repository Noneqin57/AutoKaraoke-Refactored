# -*- coding: utf-8 -*-
"""
Whisper 模型管理对话框 (ModelManagerDialog)
提供官方模型状态查看、下载与本地删除。
"""
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QProgressBar, QLabel,
                             QHeaderView, QMessageBox, QWidget, QFrame)
from PyQt6.QtCore import QThread, pyqtSignal, QObject

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

class ModelManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("模型管理 - AutoKaraoke")
        self.resize(850, 520)
        
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        
        info_card = QFrame()
        info_card.setObjectName("card")
        info_lay = QVBoxLayout(info_card)
        info_lay.setContentsMargins(14, 10, 14, 10)
        
        info_lbl = QLabel(
            "<b>提示：</b>模型均来自 OpenAI 官方 CDN（Original Whisper）。\n"
            "推荐日常使用 <b>small</b> 或 <b>medium</b> 模型；精细打轴推荐 <b>large-v2</b>。"
        )
        info_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_regular', '#dcdfe6')}; line-height: 1.4;")
        info_lay.addWidget(info_lbl)
        layout.addWidget(info_card)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["模型名称", "类型", "状态", "进度", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        btn_box = QHBoxLayout()
        refresh_btn = QPushButton("刷新列表")
        refresh_btn.setObjectName("info")
        refresh_btn.clicked.connect(self.refresh_list)
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        
        btn_box.addStretch()
        btn_box.addWidget(refresh_btn)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def refresh_list(self):
        self.table.setRowCount(0)
        self.model_list = self.manager.get_model_list()
        
        for i, model in enumerate(self.model_list):
            self.table.insertRow(i)
            
            # Name
            self.table.setItem(i, 0, QTableWidgetItem(model.name))
            
            # Type
            type_item = QTableWidgetItem(model.type)
            self.table.setItem(i, 1, type_item)
            
            # Status
            status_str = "已下载" if model.is_downloaded else "未下载"
            self.table.setItem(i, 2, QTableWidgetItem(status_str))
            
            # Progress Bar Container
            pbar_widget = QWidget()
            pbar_layout = QVBoxLayout(pbar_widget)
            pbar_layout.setContentsMargins(4, 4, 4, 4)
            pbar = QProgressBar()
            pbar.setRange(0, 100)
            pbar.setValue(0)
            pbar.setTextVisible(True)
            pbar.hide()
            pbar_layout.addWidget(pbar)
            self.table.setCellWidget(i, 3, pbar_widget)
            
            # Action Button
            self.update_action_button(i, model)

    def update_action_button(self, row, model):
        btn = QPushButton()
        if model.is_downloaded:
            btn.setText("删除")
            btn.setObjectName("danger")
            btn.clicked.connect(lambda checked, r=row: self.delete_model(r))
        else:
            if row in self.download_threads:
                btn.setText("暂停")
                btn.setObjectName("warning")
                btn.clicked.connect(lambda checked, r=row: self.stop_download(r))
            else:
                btn.setText("下载")
                btn.clicked.connect(lambda checked, r=row: self.start_download(r))
        
        self.table.setCellWidget(row, 4, btn)

    def start_download(self, row):
        model = self.model_list[row]
        self.table.item(row, 2).setText("下载中...")
        
        pbar_widget = self.table.cellWidget(row, 3)
        pbar = pbar_widget.findChild(QProgressBar)
        pbar.show()
        pbar.setValue(0)

        thread = QThread()
        worker = DownloadWorker(model)
        worker.moveToThread(thread)
        
        thread.started.connect(worker.run)
        worker.progress.connect(lambda p, msg: self.update_progress(row, p, msg))
        worker.finished.connect(lambda s, m: self.on_download_finished(row, s, m))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(lambda: self.cleanup_thread(row))
        thread.finished.connect(thread.deleteLater)
        
        self.download_threads[row] = (thread, worker)
        thread.start()
        self.update_action_button(row, model)

    def stop_download(self, row):
        if row in self.download_threads:
            thread, worker = self.download_threads[row]
            worker.stop()
            self.table.item(row, 2).setText("正在停止...")
            btn = self.table.cellWidget(row, 4)
            btn.setEnabled(False)

    def update_progress(self, row, percent, msg):
        pbar_widget = self.table.cellWidget(row, 3)
        if pbar_widget:
            pbar = pbar_widget.findChild(QProgressBar)
            if percent >= 0:
                pbar.setValue(percent)
            pbar.setToolTip(msg)

    def on_download_finished(self, row, success, msg):
        if success:
            self.model_list[row].is_downloaded = True
            self.refresh_row(row)
            QMessageBox.information(self, "成功", f"模型 {self.model_list[row].name} 下载完成")
        else:
            self.refresh_row(row)
            if msg != "Stopped":
                QMessageBox.critical(self, "错误", f"下载失败: {msg}")

    def cleanup_thread(self, row):
        if row in self.download_threads:
            del self.download_threads[row]

    def delete_model(self, row):
        model = self.model_list[row]
        reply = QMessageBox.question(self, '确认删除', f"确定要删除模型 {model.name} 吗？\n文件将被永久移除。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.manager.delete_model(model)
            model.is_downloaded = False
            self.refresh_row(row)

    def refresh_row(self, row):
        model = self.model_list[row]
        self.table.item(row, 2).setText("已下载" if model.is_downloaded else "未下载")
        
        pbar_widget = self.table.cellWidget(row, 3)
        pbar = pbar_widget.findChild(QProgressBar)
        pbar.hide()
        pbar.setValue(0)
        
        self.update_action_button(row, model)
        
    def closeEvent(self, event):
        if self.download_threads:
            reply = QMessageBox.warning(self, "警告", "有正在进行的下载任务，关闭窗口将终止下载。\n确定要关闭吗？",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            
            for row, (thread, worker) in self.download_threads.items():
                worker.stop()
                thread.quit()
                thread.wait()
                
        event.accept()
