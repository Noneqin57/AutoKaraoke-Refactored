# -*- coding: utf-8 -*-
"""
AutoKaraoke Refactored 主窗口 (LyricsGenApp)
基于 QFluentWidgets FluentWindow 构建，集成常驻后台 Daemon 任务、
双向语法高亮、Mica/Acrylic 材质、珊瑚粉 (#F25378) 主题与全流程音频打轴工作流。
"""
import os
import sys
import time
import logging
from multiprocessing import Process, Queue, Event
from queue import Empty

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from qfluentwidgets import (FluentWindow, NavigationItemPosition, FluentIcon as FIF, 
                            InfoBar, InfoBarPosition, setTheme, Theme)

from config import TIMEOUT_CHECK_INTERVAL, ConfigManager
from core.lrc_parser import LrcParser
from core.worker_types import WorkerArgs
from core.worker_launcher import daemon_worker_entry
from core.worker_policy import decide_worker_recovery
from ui.pages.generate_page import GeneratePage
from ui.pages.model_page import ModelPage
from ui.pages.settings_page import SettingsPage
from ui.editor_dialog import LrcEditorDialog
from ui.styles.theme_manager import theme_manager

logger = logging.getLogger(__name__)

class LyricsGenApp(FluentWindow):
    """
    主应用窗口：基于 FluentWindow 架构
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoKaraoke Refactored")
        self.resize(1180, 880)
        
        self.config_manager = ConfigManager()
        self.lrc_parser = LrcParser()
        
        # 1. 应用主题
        saved_theme = (self.config_manager.get("THEME") or "dark").lower()
        theme_manager.set_theme(saved_theme)
        
        # 2. 多进程常驻 Daemon 队列与状态
        self.worker_process = None
        self.task_queue = Queue()
        self.result_queue = Queue()
        self.progress_queue = Queue()
        self.stop_event = Event()
        
        self.check_timer = None
        self.is_running_task = False
        self.pending_retry_args = None
        self.retry_attempted = False
        
        # 3. 初始化子页面
        self.generate_page = GeneratePage(self.config_manager, self)
        self.model_page = ModelPage(self)
        self.settings_page = SettingsPage(self.config_manager, self)
        
        # 4. 组装导航
        self.init_navigation()
        self.connect_signals()
        
        # 5. 启动后台子进程
        self.init_worker()
        
        # 居中显示
        self._center_window()

    def _center_window(self):
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - self.width()) // 2
            y = (screen_geo.height() - self.height()) // 2
            self.move(max(0, x), max(0, y))

    def init_navigation(self):
        # 顶部导航
        self.addSubInterface(
            self.generate_page, 
            FIF.MUSIC, 
            "开始生成", 
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.model_page, 
            FIF.APPLICATION, 
            "模型管理", 
            NavigationItemPosition.TOP
        )
        
        # 底部设置
        self.addSubInterface(
            self.settings_page, 
            FIF.SETTING, 
            "系统设置", 
            NavigationItemPosition.BOTTOM
        )

    def connect_signals(self):
        self.generate_page.start_requested.connect(self.start_task)
        self.generate_page.stop_requested.connect(self.stop_task)
        self.generate_page.open_editor_requested.connect(self.open_editor)
        self.generate_page.save_requested.connect(self.save_lrc)
        self.settings_page.theme_applied.connect(self.on_theme_applied)

    def init_worker(self):
        """启动常驻后台推理守护进程（经 torch-free 跳板，主进程不加载 torch）"""
        if self.worker_process is None or not self.worker_process.is_alive():
            self.worker_process = Process(
                target=daemon_worker_entry,
                args=(self.task_queue, self.result_queue, self.progress_queue, self.stop_event)
            )
            self.worker_process.daemon = True
            self.worker_process.start()
            logger.info("Daemon worker process started with PID: %s", self.worker_process.pid)

    def on_theme_applied(self, theme_name: str):
        # 重新应用主题
        theme_manager.set_theme(theme_name)

    def start_task(self, task_data: dict):
        audio_path = task_data["audio_path"]
        model_size = task_data["model_size"]
        lang_code = task_data["language"]
        offset = task_data["offset"]
        force_cali = task_data["force_cali"]
        avg_dist = task_data["avg_dist"]
        ref_text = task_data["ref_text"]
        raw_lrc = task_data["raw_lrc_content"]

        aligner_engine = task_data.get("aligner_engine", "whisper")
        enable_vocal_sep = task_data.get("enable_vocal_separation", False)
        vocal_model = task_data.get("vocal_model", "mel_band_roformer_vocals.ckpt")
        prompt = self.config_manager.get("PROMPT") or ""
        release_vram = self.config_manager.get("RELEASE_VRAM", True) is not False
        calibration_threshold = float(self.config_manager.get("CALIBRATION_THRESHOLD") or 1.5)

        self.is_running_task = True
        
        # 解析参考歌词时间轴
        current_timestamps = []
        used_raw = False
        if raw_lrc:
            temp_parser = LrcParser()
            temp_clean = temp_parser.parse(raw_lrc, ".lrc")
            def norm(s): return "".join(s.split())
            if ref_text and norm(temp_clean) == norm(ref_text):
                self.lrc_parser = temp_parser
                current_timestamps = temp_parser.lines_timestamps
                used_raw = True
                
        if not used_raw and ref_text:
            self.lrc_parser = LrcParser()
            self.lrc_parser.parse(ref_text, ".lrc")
            current_timestamps = self.lrc_parser.lines_timestamps
        elif not ref_text:
            self.lrc_parser = LrcParser()

        lrc_parser_data = {
            'headers': self.lrc_parser.headers,
            'lines_text': self.lrc_parser.lines_text,
            'translations': self.lrc_parser.translations
        }

        # 清空残留消息
        self.stop_event.clear()
        while not self.result_queue.empty():
            try: self.result_queue.get_nowait()
            except Empty: pass
        while not self.progress_queue.empty():
            try: self.progress_queue.get_nowait()
            except Empty: pass

        args = WorkerArgs(
            audio_path=audio_path,
            aligner_engine=aligner_engine,
            enable_vocal_separation=enable_vocal_sep,
            vocal_separation_model=vocal_model,
            model_size=model_size,
            language=lang_code,
            ref_text=ref_text,
            lrc_parser_data=lrc_parser_data,
            time_offset=offset,
            initial_prompt_input=prompt,
            model_dir=self.config_manager.get("MODEL_DIR"),
            release_vram=release_vram,
            lrc_timestamps=current_timestamps,
            enable_force_calibration=force_cali,
            enable_avg_distribution=avg_dist,
            calibration_threshold=calibration_threshold
        )

        self.pending_retry_args = args
        self.retry_attempted = False

        self.init_worker()
        self.task_queue.put(args)

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_queue)
        self.check_timer.start(int(TIMEOUT_CHECK_INTERVAL * 1000))

        InfoBar.info(
            title="任务已提交",
            content=f"已开始处理【{os.path.basename(audio_path)}】...",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500
        )

    def stop_task(self):
        if self.stop_event:
            self.generate_page.status_lbl.setText("正在请求停止推理...")
            self.stop_event.set()

    def check_queue(self):
        # 1. 检查子进程健康度与自动恢复
        if self.worker_process is not None and not self.worker_process.is_alive():
            action = decide_worker_recovery(
                self.is_running_task,
                self.pending_retry_args is not None,
                self.retry_attempted,
            )
            if action == "retry":
                self.retry_attempted = True
                self.generate_page.status_lbl.setText("后台推理进程已重启，正在自动重试任务...")
                self.init_worker()
                self.task_queue.put(self.pending_retry_args)
                return
            if action == "error":
                self.on_error("后台推理进程意外退出，请检查显存并重试！")
            self.cleanup_worker()
            self.init_worker()
            return

        # 2. 读取进度队列
        while True:
            try:
                msg = self.progress_queue.get_nowait()
                if isinstance(msg, str):
                    if msg.startswith("PROGRESS:"):
                        try:
                            val = int(msg.split(":")[1])
                            self.generate_page.update_progress(val)
                        except (ValueError, IndexError):
                            pass
                    else:
                        self.generate_page.status_lbl.setText(msg)
            except Empty:
                break

        # 3. 读取结果队列
        try:
            result_type, result_data = self.result_queue.get_nowait()
            if result_type == "success":
                self.on_done(result_data)
            elif result_type == "error":
                self.on_error(result_data)
            elif result_type == "aborted":
                self.on_aborted()
            self.cleanup_worker()
        except Empty:
            pass

    def cleanup_worker(self):
        if self.check_timer:
            self.check_timer.stop()
            self.check_timer = None

    def on_done(self, lrc_text: str):
        self.is_running_task = False
        self.pending_retry_args = None
        self.generate_page.set_running_state(False)
        self.generate_page.set_result_text(lrc_text)
        self.generate_page.status_lbl.setText("生成完成！")
        
        InfoBar.success(
            title="生成成功",
            content="逐字歌词生成完毕，可点击「进入精细打轴」进行校准！",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=3500
        )

    def on_aborted(self):
        self.is_running_task = False
        self.pending_retry_args = None
        self.generate_page.set_running_state(False)
        self.generate_page.status_lbl.setText("任务已停止")
        InfoBar.warning(
            title="已停止",
            content="生成任务已由用户主动终止。",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500
        )

    def on_error(self, error_msg: str):
        self.is_running_task = False
        self.pending_retry_args = None
        self.generate_page.set_running_state(False)
        self.generate_page.status_lbl.setText("任务失败")
        InfoBar.error(
            title="生成失败",
            content=str(error_msg),
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=4500
        )

    def open_editor(self, audio_path: str, lrc_text: str):
        if not audio_path or not lrc_text.strip():
            return

        dialog = LrcEditorDialog(audio_path, lrc_text, self)
        if dialog.exec():
            if dialog.result_lrc:
                self.generate_page.set_result_text(dialog.result_lrc)
                InfoBar.success(
                    title="校准已应用",
                    content="逐字校对结果已同步至结果框！",
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2500
                )
        # 编辑器自带 50ms 刷新 timer 与 QMediaPlayer，用完立即销毁避免累积泄漏
        dialog.deleteLater()

    def save_lrc(self, content: str, encoding: str):
        audio_path = self.generate_page.audio_path
        default_dir = self.config_manager.get("OUTPUT_DIR") or "output"
        default_name = os.path.splitext(os.path.basename(audio_path))[0] + ".lrc" if audio_path else "lyrics.lrc"
        
        if default_dir and os.path.exists(default_dir):
            default_path = os.path.join(default_dir, default_name)
        else:
            default_path = default_name

        f, _ = QFileDialog.getSaveFileName(self, "保存歌词文件", default_path, "LRC (*.lrc);;All Files (*)")
        if f:
            try:
                with open(f, 'w', encoding=encoding) as file:
                    file.write(content)
                InfoBar.success(
                    title="保存成功",
                    content=f"已成功保存至: {os.path.basename(f)}",
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3000
                )
            except Exception as e:
                InfoBar.error(
                    title="保存失败",
                    content=str(e),
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=3500
                )

    def _shutdown_worker(self, timeout: float = 3.0):
        if not self.worker_process or not self.worker_process.is_alive():
            return
        try:
            self.task_queue.put("EXIT")
        except Exception:
            logger.exception("Failed to send EXIT to worker queue")

        self.worker_process.join(timeout=timeout)
        if self.worker_process.is_alive():
            logger.warning("Worker process did not exit gracefully; terminating.")
            self.worker_process.terminate()
            self.worker_process.join(timeout=1)
            if self.worker_process.is_alive():
                self.worker_process.kill()
                self.worker_process.join(timeout=1)

    def closeEvent(self, event):
        if self.is_running_task:
            reply = QMessageBox.question(
                self, '确认退出', '后台推理任务正在运行，确定要退出吗？', 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_task()
            else: 
                event.ignore()
                return

        if self.worker_process and self.worker_process.is_alive():
            self._shutdown_worker()
            
        event.accept()
