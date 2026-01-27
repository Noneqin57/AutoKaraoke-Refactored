# -*- coding: utf-8 -*-
import os

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
                             QTableWidgetItem, QPushButton, QProgressBar, QLabel,
                             QHeaderView, QMessageBox, QWidget, QLineEdit, QFormLayout)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject

from core.model_manager import ModelManager, ModelInfo, ModelDownloader, ModelType
from config import ConfigManager

class DownloadWorker(QObject):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str) # success, msg

    def __init__(self, model_info: ModelInfo, mirror_url: str = None):
        super().__init__()
        self.model_info = model_info
        self.mirror_url = mirror_url
        self.downloader = None

    def run(self):
        try:
            self.downloader = ModelDownloader(self.model_info, self._callback)
            self.downloader.set_mirror(self.mirror_url)
            self.downloader.start()
            self.finished.emit(True, "Success")
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
        self.setWindowTitle("模型管理")
        self.resize(800, 500)
        
        # Determine model dir from config
        self.config = ConfigManager()
        model_dir = self.config.get("MODEL_DIR")
        if not model_dir:
            model_dir = "models"
            
        # If relative, make absolute
        if not os.path.isabs(model_dir):
            model_dir = os.path.abspath(model_dir)
            
        self.manager = ModelManager(model_dir)
        self.model_list = []
        self.download_threads = {} # row -> (thread, worker)

        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        info_lbl = QLabel("提示: Faster-Whisper 模型通常比标准模型更快且精度接近。\n如果网速较慢，请优先下载 Small 或 Medium 模型。")
        info_lbl.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(info_lbl)

        # Mirror settings
        mirror_layout = QHBoxLayout()
        mirror_layout.addWidget(QLabel("下载镜像源 (Faster-Whisper):"))
        self.mirror_edit = QLineEdit()
        self.mirror_edit.setText(self.config.get("HF_MIRROR", "https://hf-mirror.com"))
        self.mirror_edit.setPlaceholderText("https://hf-mirror.com")
        self.mirror_edit.setToolTip("设置 HuggingFace 镜像源以加速国内下载")
        save_mirror_btn = QPushButton("保存镜像设置")
        save_mirror_btn.clicked.connect(self.save_mirror_config)
        mirror_layout.addWidget(self.mirror_edit)
        mirror_layout.addWidget(save_mirror_btn)
        layout.addLayout(mirror_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["模型名称", "类型", "状态", "进度", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        btn_box = QHBoxLayout()
        refresh_btn = QPushButton("刷新列表")
        refresh_btn.clicked.connect(self.refresh_list)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_box.addStretch()
        btn_box.addWidget(refresh_btn)
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)

    def save_mirror_config(self):
        url = self.mirror_edit.text().strip()
        if not url: return
        self.config.set("HF_MIRROR", url)
        self.config.save()
        QMessageBox.information(self, "成功", "镜像源设置已保存。")

    def refresh_list(self):
        # Keep existing rows if possible to avoid flicker, but full refresh is safer for logic
        self.table.setRowCount(0)
        self.model_list = self.manager.get_model_list()
        
        for i, model in enumerate(self.model_list):
            self.table.insertRow(i)
            
            # Name
            self.table.setItem(i, 0, QTableWidgetItem(model.name))
            
            # Type
            type_item = QTableWidgetItem(model.type)
            if model.type == ModelType.FASTER_WHISPER:
                type_item.setForeground(Qt.GlobalColor.darkGreen)
            self.table.setItem(i, 1, type_item)
            
            # Status
            status_str = "已下载" if model.is_downloaded else "未下载"
            self.table.setItem(i, 2, QTableWidgetItem(status_str))
            
            # Progress Bar Container
            pbar_widget = QWidget()
            pbar_layout = QVBoxLayout(pbar_widget)
            pbar_layout.setContentsMargins(2, 2, 2, 2)
            pbar = QProgressBar()
            pbar.setRange(0, 100)
            pbar.setValue(0)
            pbar.setTextVisible(False) # We will use label for text if needed, or tooltip
            pbar.hide()
            pbar_layout.addWidget(pbar)
            self.table.setCellWidget(i, 3, pbar_widget)
            
            # Action Button
            self.update_action_button(i, model)

    def update_action_button(self, row, model):
        # Helper to create/update the action button
        btn = QPushButton()
        if model.is_downloaded:
            btn.setText("删除")
            btn.setStyleSheet("background-color: #f56c6c; color: white;")
            btn.clicked.connect(lambda checked, r=row: self.delete_model(r))
        else:
            if row in self.download_threads:
                # Active download
                btn.setText("暂停") # Actually stop
                btn.setStyleSheet("background-color: #e6a23c; color: white;")
                btn.clicked.connect(lambda checked, r=row: self.stop_download(r))
            else:
                btn.setText("下载")
                btn.setStyleSheet("background-color: #409eff; color: white;")
                btn.clicked.connect(lambda checked, r=row: self.start_download(r))
        
        self.table.setCellWidget(row, 4, btn)

    def start_download(self, row):
        model = self.model_list[row]
        
        # Update UI
        self.table.item(row, 2).setText("下载中...")
        
        pbar_widget = self.table.cellWidget(row, 3)
        pbar = pbar_widget.findChild(QProgressBar)
        pbar.show()
        pbar.setValue(0)

        # Create Thread
        thread = QThread()
        mirror = self.config.get("HF_MIRROR", "https://hf-mirror.com")
        worker = DownloadWorker(model, mirror)
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
        
        # Update button to "Pause"
        self.update_action_button(row, model)

    def stop_download(self, row):
        if row in self.download_threads:
            thread, worker = self.download_threads[row]
            worker.stop()
            # UI update happens in on_download_finished (triggered by stop usually indirectly or we force it)
            # Actually, stop() just sets a flag. The thread will finish with success=False.
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
            # Optional: Show text in status column? 
            # self.table.item(row, 2).setText(msg)

    def on_download_finished(self, row, success, msg):
        # Note: Do not delete thread ref here to avoid QThread destroyed while running error
        # It will be cleaned up in cleanup_thread when thread actually finishes
            
        if success:
            self.model_list[row].is_downloaded = True
            self.refresh_row(row)
            # Use QTimer.singleShot to show message box after a slight delay to allow event loop to process
            # But direct call is usually fine if we don't delete thread here
            QMessageBox.information(self, "成功", f"模型 {self.model_list[row].name} 下载完成")
        else:
            self.refresh_row(row)
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
        # Helper to just refresh one row's UI based on current model state
        model = self.model_list[row]
        
        self.table.item(row, 2).setText("已下载" if model.is_downloaded else "未下载")
        
        pbar_widget = self.table.cellWidget(row, 3)
        pbar = pbar_widget.findChild(QProgressBar)
        if not self.model_list[row].is_downloaded:
             pbar.hide()
             pbar.setValue(0)
        else:
             pbar.hide()
        
        self.update_action_button(row, model)
        
    def closeEvent(self, event):
        # Warn if downloads are active
        if self.download_threads:
            reply = QMessageBox.warning(self, "警告", "有正在进行的下载任务，关闭窗口将终止下载。\n确定要关闭吗？",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            
            # Stop all threads
            for row, (thread, worker) in self.download_threads.items():
                worker.stop()
                thread.quit()
                thread.wait() # force wait
                
        event.accept()
