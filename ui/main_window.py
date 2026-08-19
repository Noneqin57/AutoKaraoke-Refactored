# -*- coding: utf-8 -*-
"""
AutoKaraoke Refactored 主窗口 (LyricsGenApp)
集成常驻后台 Daemon 任务、双向增强语法高亮、主题系统与音频/歌词全流程工作流。
"""
import os
import sys
import time
import logging
from multiprocessing import Process, Queue, Event
from queue import Empty
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QFileDialog, QTextEdit, QProgressBar, QMessageBox, QComboBox, 
                             QSplitter, QCheckBox, QFrame, QGraphicsDropShadowEffect)
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QColor, QIcon, QKeySequence
from PyQt6.QtCore import Qt, QTimer
try:
    import qtawesome as qta
    HAS_QTAWESOME = True
except ImportError:
    qta = None
    HAS_QTAWESOME = False

from config import TIMEOUT_CHECK_INTERVAL, ConfigManager
from core.lrc_parser import LrcParser
from core.whisper_worker import daemon_worker, WorkerArgs
from core.worker_policy import decide_worker_recovery
from ui.editor_dialog import LrcEditorDialog
from ui.settings_dialog import SettingsDialog
from ui.model_manager_dialog import ModelManagerDialog
from ui.components.lrc_highlighter import EnhancedLrcHighlighter
from ui.styles.theme_manager import theme_manager

logger = logging.getLogger(__name__)

class LyricsGenApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoKaraoke Refactored")
        self.resize(1150, 900)
        self.setAcceptDrops(True)
        
        self.config_manager = ConfigManager()
        self.lrc_parser = LrcParser()
        self.audio_path = None
        
        # 初始化并应用主题
        saved_theme = self.config_manager.get("THEME") or "dark"
        theme_manager.set_theme(saved_theme)
        
        # Daemon Worker Management
        self.worker_process = None
        self.task_queue = Queue()
        self.result_queue = Queue()
        self.progress_queue = Queue()
        self.stop_event = Event()
        
        self.check_timer = None
        self.raw_lrc_content = None 
        
        self.chk_force_cali = None
        self.chk_avg_dist = None
        
        self.is_running_task = False
        self.pending_retry_args = None
        self.retry_attempted = False
        
        self.setup_menu()
        self.setup_ui()
        self.init_worker()

    def init_worker(self):
        """启动后台常驻推理守护进程"""
        if self.worker_process is None or not self.worker_process.is_alive():
            self.worker_process = Process(
                target=daemon_worker, 
                args=(self.task_queue, self.result_queue, self.progress_queue, self.stop_event)
            )
            self.worker_process.daemon = True
            self.worker_process.start()
            logger.info("Daemon worker started with PID: %s", self.worker_process.pid)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ['.mp3', '.wav', '.flac', '.m4a', '.ogg']:
                self.audio_path = f
                self.path_lbl.setText(f"已载入音频: {os.path.basename(f)}")
                self.path_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_primary')}; font-weight: bold;")
                self.status.setText("音频已加载 (通过拖拽)")
                if self.out_txt.toPlainText().strip():
                    self.btn_cali.setEnabled(True)
            elif ext in ['.lrc', '.txt', '.srt']:
                self.import_lrc_file(f)

    def import_lrc_file(self, f):
        try:
            raw = ""
            for enc in ['utf-8', 'gbk', 'utf-8-sig', 'big5']:
                try:
                    with open(f, 'r', encoding=enc) as file:
                        raw = file.read()
                        break
                except (UnicodeDecodeError, IOError):
                    continue
            
            self.raw_lrc_content = raw 
            ext = os.path.splitext(f)[1].lower()
            clean_text = self.lrc_parser.parse(raw, ext)
            self.input_txt.setText(clean_text)
            self.status.setText(f"导入成功: {os.path.basename(f)}")
        except Exception as e:
            QMessageBox.warning(self, "导入错误", str(e))
    
    def setup_menu(self):
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("文件 (&F)")
        
        imp_audio = QAction("导入音频 (&O)...", self)
        imp_audio.setShortcut(QKeySequence("Ctrl+O"))
        imp_audio.triggered.connect(self.select_audio)
        file_menu.addAction(imp_audio)
        
        imp_lrc = QAction("导入歌词 (&I)...", self)
        imp_lrc.setShortcut(QKeySequence("Ctrl+I"))
        imp_lrc.triggered.connect(self.import_lrc)
        file_menu.addAction(imp_lrc)
        
        file_menu.addSeparator()
        
        save_action = QAction("保存结果 (&S)...", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.save)
        file_menu.addAction(save_action)
        
        exit_action = QAction("退出 (&Q)", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 设置菜单
        settings_menu = menu_bar.addMenu("设置 (&S)")
        
        adv_settings = QAction("系统设置 (&P)...", self)
        adv_settings.setShortcut(QKeySequence("Ctrl+,"))
        adv_settings.triggered.connect(self.open_settings_dialog)
        settings_menu.addAction(adv_settings)

        model_mgr = QAction("模型管理 (&M)...", self)
        model_mgr.setShortcut(QKeySequence("Ctrl+M"))
        model_mgr.triggered.connect(self.open_model_manager)
        settings_menu.addAction(model_mgr)

    def setup_ui(self):
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_file_card())
        layout.addWidget(self._build_splitter(), 1)
        layout.addWidget(self._build_options_card())
        layout.addWidget(self._build_actions_card())
        layout.addLayout(self._build_status_bar())

    def _make_card(self, shadow: bool = True) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setFrameShape(QFrame.Shape.NoFrame)
        if shadow:
            effect = QGraphicsDropShadowEffect(card)
            effect.setBlurRadius(14)
            effect.setOffset(0, 2)
            effect.setColor(QColor(0, 0, 0, 45) if theme_manager.is_dark() else QColor(31, 35, 41, 14))
            card.setGraphicsEffect(effect)
        return card

    @staticmethod
    def _icon(name: str, color: str = "#ffffff"):
        if not HAS_QTAWESOME:
            return QIcon()
        return qta.icon(name, color=color)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(54)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(20, 0, 20, 0)

        title = QLabel("AutoKaraoke Refactored - Whisper 逐字歌词生成与校对")
        title.setObjectName("appTitle")
        lay.addWidget(title)
        lay.addStretch()

        btn_set = QPushButton("系统设置")
        btn_set.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_set.setIcon(self._icon("fa5s.cog"))
        btn_set.setStyleSheet("background-color: rgba(255, 255, 255, 0.2); border: none; border-radius: 6px; padding: 6px 12px;")
        btn_set.clicked.connect(self.open_settings_dialog)
        lay.addWidget(btn_set)

        return header

    def _build_file_card(self) -> QFrame:
        card = self._make_card()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)

        self.path_lbl = QLabel("尚未选择音频文件 (可直接将 MP3/WAV/FLAC 文件拖拽至此)")
        self.path_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")
        btn_aud = QPushButton("选择歌曲")
        btn_aud.setIcon(self._icon("fa5s.folder-open"))
        btn_aud.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_aud.clicked.connect(self.select_audio)

        lay.addWidget(self.path_lbl, 1)
        lay.addWidget(btn_aud)
        return card

    def _build_splitter(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        # 左侧：歌词底稿
        left = self._make_card(shadow=False)
        l_lay = QVBoxLayout(left)
        l_lay.setContentsMargins(0, 0, 0, 0)
        l_lay.setSpacing(0)

        l_head = QWidget()
        l_head.setObjectName("cardHead")
        lh = QHBoxLayout(l_head)
        lh.setContentsMargins(16, 8, 12, 8)
        lt = QLabel("歌词底稿")
        lt.setObjectName("cardTitle")
        lh.addWidget(lt)
        lh.addStretch()
        
        btn_imp = QPushButton("导入")
        btn_imp.setObjectName("warning")
        btn_imp.setIcon(self._icon("fa5s.file-import"))
        btn_imp.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_imp.clicked.connect(self.import_lrc)
        
        btn_clr = QPushButton("清空")
        btn_clr.setObjectName("danger")
        btn_clr.setIcon(self._icon("fa5s.trash-alt"))
        btn_clr.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_clr.clicked.connect(self.clear_input)
        
        lh.addWidget(btn_imp)
        lh.addWidget(btn_clr)
        l_lay.addWidget(l_head)

        self.input_txt = QTextEdit()
        self.input_txt.setPlaceholderText("在此粘贴包含时间戳的 LRC 底稿，或直接拖拽文件导入...\n第一行为原文，后续相同时间戳的行为翻译。")
        self.input_highlighter = EnhancedLrcHighlighter(self.input_txt.document(), self)
        l_lay.addWidget(self.input_txt)
        splitter.addWidget(left)

        # 右侧：生成结果
        right = self._make_card(shadow=False)
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(0)

        r_head = QWidget()
        r_head.setObjectName("cardHead")
        rh = QHBoxLayout(r_head)
        rh.setContentsMargins(16, 8, 12, 8)
        rt = QLabel("生成结果 (逐字 LRC)")
        rt.setObjectName("cardTitle")
        rh.addWidget(rt)
        rh.addStretch()
        
        self.btn_cali = QPushButton("手动校准 / 打轴")
        self.btn_cali.setObjectName("info")
        self.btn_cali.setIcon(self._icon("fa5s.edit"))
        self.btn_cali.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cali.clicked.connect(self.open_calibration)
        self.btn_cali.setEnabled(False)
        rh.addWidget(self.btn_cali)
        r_lay.addWidget(r_head)

        self.out_txt = QTextEdit()
        self.out_txt.setObjectName("outputBox")
        self.out_txt.setReadOnly(True)
        self.out_highlighter = EnhancedLrcHighlighter(self.out_txt.document(), self)
        r_lay.addWidget(self.out_txt)
        splitter.addWidget(right)

        splitter.setSizes([540, 540])
        return splitter

    def _build_options_card(self) -> QFrame:
        card = self._make_card()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 10)

        self.chk_force_cali = QCheckBox("启用强制纠偏 (Force Calibration)")
        self.chk_force_cali.setChecked(True)
        self.chk_force_cali.setToolTip("当生成的时间戳与原始底稿时间戳偏差过大时，强制对齐到原始时间戳")

        self.chk_avg_dist = QCheckBox("校准行平均分配时间")
        self.chk_avg_dist.setChecked(False)
        self.chk_avg_dist.setToolTip("仅在触发强制校准时生效：将该行的时间平均分配给每个字，便于后续手动微调")

        lay.addWidget(self.chk_force_cali)
        lay.addWidget(self.chk_avg_dist)
        lay.addStretch()
        return card

    def _build_actions_card(self) -> QFrame:
        card = self._make_card()
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)

        self.btn_run = QPushButton("开始生成 (Start)")
        self.btn_run.setIcon(self._icon("fa5s.play"))
        self.btn_run.setMinimumHeight(42)
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.clicked.connect(self.start)

        self.btn_stop = QPushButton("停止 (Stop)")
        self.btn_stop.setObjectName("secondary")
        self.btn_stop.setIcon(self._icon("fa5s.stop", "#f56c6c"))
        self.btn_stop.setMinimumHeight(42)
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False)

        lay.addWidget(self.btn_run, 3)
        lay.addWidget(self.btn_stop, 1)
        return card

    def _build_status_bar(self) -> QHBoxLayout:
        stat = QHBoxLayout()
        stat.setContentsMargins(4, 2, 4, 2)

        self.status = QLabel("就绪")
        self.status.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")
        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setFixedSize(240, 8)
        self.pbar.hide()

        stat.addWidget(self.status)
        stat.addWidget(self.pbar)
        stat.addStretch()
        
        stat.addWidget(QLabel("保存编码:"))
        self.enc_combo = QComboBox()
        self.enc_combo.addItems(["utf-8", "gbk", "utf-8-sig"])
        stat.addWidget(self.enc_combo)
        
        btn_save = QPushButton("保存结果")
        btn_save.setObjectName("success")
        btn_save.setIcon(self._icon("fa5s.save"))
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self.save)
        stat.addWidget(btn_save)
        
        return stat

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config_manager, self)
        dialog.exec()

    def open_model_manager(self):
        dialog = ModelManagerDialog(self)
        dialog.exec()

    def check_queue(self):
        if self.worker_process is not None and not self.worker_process.is_alive():
            action = decide_worker_recovery(
                self.is_running_task,
                self.pending_retry_args is not None,
                self.retry_attempted,
            )
            if action == "retry":
                self.retry_attempted = True
                self.status.setText("后台进程已重启，正在自动重试当前任务...")
                self.init_worker()
                self.task_queue.put(self.pending_retry_args)
                return
            if action == "error":
                self.on_error("后台处理进程意外退出，请重试")
            self.cleanup_worker()
            self.init_worker()
            return
        
        while True:
            try:
                msg = self.progress_queue.get_nowait()
                if isinstance(msg, str):
                    if msg.startswith("PROGRESS:"):
                        try:
                            val = int(msg.split(":")[1])
                            self.pbar.setRange(0, 100)
                            self.pbar.setValue(val)
                        except (ValueError, IndexError):
                            pass
                    else:
                        self.status.setText(msg)
            except Empty:
                break
                
        try:
            result_type, result_data = self.result_queue.get_nowait()
            if result_type == "success": self.on_done(result_data)
            elif result_type == "error": self.on_error(result_data)
            elif result_type == "aborted": self.on_aborted()
            self.cleanup_worker()
        except Empty:
            pass

    def select_audio(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "Audio Files (*.mp3 *.wav *.flac *.m4a *.ogg)")
        if f:
            self.audio_path = f
            self.path_lbl.setText(f"已载入音频: {os.path.basename(f)}")
            self.path_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_primary')}; font-weight: bold;")
            self.status.setText("音频已加载")
            if self.out_txt.toPlainText().strip():
                self.btn_cali.setEnabled(True)

    def clear_input(self):
        self.input_txt.clear()
        self.raw_lrc_content = None
        self.status.setText("已清空输入")

    def import_lrc(self):
        f, _ = QFileDialog.getOpenFileName(self, "导入歌词", "", "Lrc/Txt/Srt (*.lrc *.txt *.srt)")
        if not f: return
        self.import_lrc_file(f)

    def start(self):
        if not self.audio_path:
            return QMessageBox.warning(self, "提示", "请先选择音频文件")
        
        model_size = self.config_manager.get("MODEL_SIZE") or "large-v2"
        lang_code = self.config_manager.get("LANGUAGE") or "ja"
        prompt = self.config_manager.get("PROMPT") or ""
        offset_ms = self.config_manager.get("OFFSET") or 0
        release_vram = self.config_manager.get("RELEASE_VRAM", True) is not False
        calibration_threshold = self.config_manager.get("CALIBRATION_THRESHOLD") or 1.5
        
        self.is_running_task = True
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_cali.setEnabled(False)
        self.pbar.show()
        self.pbar.setRange(0, 0)
        
        txt = self.input_txt.toPlainText()
        current_timestamps = []
        used_raw_content = False
        
        if self.raw_lrc_content:
            temp_parser = LrcParser()
            temp_clean = temp_parser.parse(self.raw_lrc_content, ".lrc")
            
            def normalize(s): return "".join(s.split())
            
            if normalize(temp_clean) == normalize(txt):
                current_timestamps = temp_parser.lines_timestamps
                used_raw_content = True
                logger.info("Using cached raw LRC content for timestamps.")
            else:
                self.lrc_parser = temp_parser
        
        if not used_raw_content:
            self.lrc_parser.parse(txt, ".lrc")
            current_timestamps = self.lrc_parser.lines_timestamps
            logger.info("Parsed content from input text box.")
        
        lrc_parser_data = {
            'headers': self.lrc_parser.headers, 
            'lines_text': self.lrc_parser.lines_text, 
            'translations': self.lrc_parser.translations
        }
        
        if used_raw_content:
            msg = "检测到原始时间轴"
            if self.chk_force_cali.isChecked():
                msg += "，已启用强制纠偏"
            else:
                msg += "，但未启用强制纠偏"
            self.status.setText(msg)
        
        self.stop_event.clear()
        
        while not self.result_queue.empty():
            try: self.result_queue.get_nowait()
            except Empty: pass
        while not self.progress_queue.empty():
            try: self.progress_queue.get_nowait()
            except Empty: pass
        
        args = WorkerArgs(
            audio_path=self.audio_path,
            model_size=model_size,
            language=lang_code,
            ref_text=txt,
            lrc_parser_data=lrc_parser_data,
            time_offset=offset_ms/1000.0,
            initial_prompt_input=prompt,
            model_dir=self.config_manager.get("MODEL_DIR"),
            release_vram=release_vram,
            lrc_timestamps=current_timestamps,
            enable_force_calibration=self.chk_force_cali.isChecked(),
            enable_avg_distribution=self.chk_avg_dist.isChecked(),
            calibration_threshold=calibration_threshold
        )

        self.pending_retry_args = args
        self.retry_attempted = False

        self.init_worker()
        self.task_queue.put(args)
        
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_queue)
        self.check_timer.start(int(TIMEOUT_CHECK_INTERVAL * 1000))

    def stop(self):
        if self.stop_event:
            self.status.setText("正在请求停止...")
            self.stop_event.set()

    def cleanup_worker(self):
        if self.check_timer:
            self.check_timer.stop()
            self.check_timer = None

    def on_done(self, lrc: str):
        self.is_running_task = False
        self.pending_retry_args = None
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_cali.setEnabled(True)
        self.pbar.hide()
        self.out_txt.setText(lrc)
        self.status.setText("任务完成")

    def on_aborted(self):
        self.is_running_task = False
        self.pending_retry_args = None
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.pbar.hide()
        self.status.setText("任务已停止")

    def on_error(self, error_msg: str):
        self.is_running_task = False
        self.pending_retry_args = None
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.pbar.hide()
        self.status.setText("任务失败")
        QMessageBox.critical(self, "错误", error_msg)

    def open_calibration(self):
        if not self.audio_path: return QMessageBox.warning(self, "提示", "没有加载音频文件")
        content = self.out_txt.toPlainText()
        if not content: return QMessageBox.warning(self, "提示", "没有歌词内容")
        
        dialog = LrcEditorDialog(self.audio_path, content, self)
        if dialog.exec():
            if dialog.result_lrc:
                self.out_txt.setText(dialog.result_lrc)
                self.status.setText("校准已应用")

    def save(self):
        txt = self.out_txt.toPlainText()
        if not txt: return
        
        default_dir = self.config_manager.get("OUTPUT_DIR")
        default_filename = os.path.splitext(os.path.basename(self.audio_path))[0] + ".lrc" if self.audio_path else "out.lrc"
        
        if default_dir and os.path.exists(default_dir):
            default_path = os.path.join(default_dir, default_filename)
        else:
            default_path = default_filename

        f, _ = QFileDialog.getSaveFileName(self, "保存歌词", default_path, "LRC (*.lrc)")
        if f:
            try:
                with open(f, 'w', encoding=self.enc_combo.currentText()) as file:
                    file.write(txt)
                self.status.setText(f"已保存: {os.path.basename(f)}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))

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
                self, '确认退出', '后台任务正在运行，确定要退出吗？', 
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.stop()
            else: 
                event.ignore()
                return

        if self.worker_process and self.worker_process.is_alive():
            self._shutdown_worker()
            
        event.accept()
