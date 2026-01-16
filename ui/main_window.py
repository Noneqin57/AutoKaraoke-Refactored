# -*- coding: utf-8 -*-
import os
import sys
import time
from multiprocessing import Process, Queue, Event
from queue import Empty
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QFileDialog, QTextEdit, QProgressBar, QMessageBox, QComboBox, 
                             QSplitter, QSpinBox, QCheckBox)
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QSyntaxHighlighter, QTextCharFormat, QColor
from PyQt6.QtCore import Qt, QTimer

from config import TIMEOUT_CHECK_INTERVAL, PROMPT_DEFAULTS, ConfigManager, LANGUAGES
from core.lrc_parser import LrcParser
from core.whisper_worker import daemon_worker, WorkerArgs
from ui.editor_dialog import LrcEditorDialog
from ui.settings_dialog import SettingsDialog

try:
    import faster_whisper
    HAS_FASTER_WHISPER = True
except ImportError:
    HAS_FASTER_WHISPER = False

class LrcHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.format = QTextCharFormat()
        self.format.setForeground(QColor("#409eff"))
        self.format.setFontWeight(700) # Bold

    def highlightBlock(self, text):
        import re
        # Highlight [mm:ss.xx]
        for match in re.finditer(r'\[\d{2}:\d{2}\.\d{2,3}\]', text):
            self.setFormat(match.start(), match.end() - match.start(), self.format)

class LyricsGenApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AutoKaraoke Refactored")
        self.resize(1100, 900)
        self.setAcceptDrops(True) # Enable Drag & Drop
        
        self.config_manager = ConfigManager()
        self.lrc_parser = LrcParser()
        self.audio_path = None
        
        # Daemon Worker Management
        self.worker_process = None
        self.task_queue = Queue()
        
        # 初始化通信队列和事件
        self.result_queue = Queue()
        self.progress_queue = Queue()
        self.stop_event = Event()
        
        self.check_timer = None
        self.raw_lrc_content = None 
        
        self.chk_force_cali = None
        self.chk_avg_dist = None
        
        self.is_running_task = False # Track actual task status
        
        self.setup_menu()
        self.setup_ui()
        self.init_worker() # Start daemon
        
    def init_worker(self):
        """Start the persistent worker process"""
        if self.worker_process is None or not self.worker_process.is_alive():
            # 将结果队列、进度队列和停止事件直接传递给子进程
            self.worker_process = Process(target=daemon_worker, 
                                          args=(self.task_queue, self.result_queue, self.progress_queue, self.stop_event))
            self.worker_process.daemon = True
            self.worker_process.start()
            print(f"Daemon worker started with PID: {self.worker_process.pid}")

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
                self.path_lbl.setText(f"🎵 {os.path.basename(f)}")
                self.status.setText("音频已加载 (通过拖拽)")
                if self.out_txt.toPlainText().strip(): self.btn_cali.setEnabled(True)
            elif ext in ['.lrc', '.txt', '.srt']:
                self.import_lrc_file(f)

    def import_lrc_file(self, f):
        """Helper for import logic"""
        try:
            raw = ""
            for enc in ['utf-8', 'gbk', 'utf-8-sig', 'big5']:
                try:
                    with open(f, 'r', encoding=enc) as file: raw = file.read(); break
                except: continue
            
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
        file_menu = menu_bar.addMenu("文件")
        
        imp_audio = QAction("导入音频", self)
        imp_audio.triggered.connect(self.select_audio)
        file_menu.addAction(imp_audio)
        
        imp_lrc = QAction("导入歌词", self)
        imp_lrc.triggered.connect(self.import_lrc)
        file_menu.addAction(imp_lrc)
        
        file_menu.addSeparator()
        
        save_action = QAction("保存结果", self)
        save_action.triggered.connect(self.save)
        file_menu.addAction(save_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 设置菜单
        settings_menu = menu_bar.addMenu("设置")
        
        adv_settings = QAction("高级设置...", self)
        adv_settings.triggered.connect(self.open_settings_dialog)
        settings_menu.addAction(adv_settings)

    def setup_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f7fa; }
            QLabel { font-family: 'Microsoft YaHei'; color: #333; font-size: 13px; }
            QTextEdit { background: white; border: 1px solid #dcdfe6; border-radius: 6px; padding: 10px; font-family: Consolas; font-size: 14px; }
            QLineEdit { background: white; border: 1px solid #dcdfe6; border-radius: 4px; padding: 5px; }
            QPushButton { background-color: #409eff; color: white; border-radius: 6px; padding: 8px 15px; font-weight: bold; }
            QPushButton:hover { background-color: #66b1ff; }
            QPushButton:disabled { background-color: #c0c4cc; color: #909399; }
            QComboBox, QSpinBox { padding: 5px; border: 1px solid #dcdfe6; background: white; border-radius: 4px; }
            QProgressBar { border: 1px solid #dcdfe6; border-radius: 4px; text-align: center; }
            QProgressBar::chunk { background-color: #409eff; width: 20px; }
        """)
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        
        status_text = "<span style='color:green'>⚡ 加速模式</span>" if HAS_FASTER_WHISPER else "<span>标准模式</span>"
        layout.addWidget(QLabel(f"<h2>AutoKaraoke Refactored {status_text}</h2>"), alignment=Qt.AlignmentFlag.AlignCenter)
        
        # 文件选择
        file_box = QHBoxLayout()
        self.path_lbl = QLabel("🚫 尚未选择音频文件")
        self.path_lbl.setStyleSheet("background: white; padding: 8px; border: 1px dashed #ccc; border-radius: 4px;")
        btn_aud = QPushButton("📂 选择歌曲")
        btn_aud.clicked.connect(self.select_audio)
        file_box.addWidget(self.path_lbl, 4)
        file_box.addWidget(btn_aud, 1)
        layout.addLayout(file_box)
        
        # 分割区域
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧输入
        left = QWidget()
        l_lay = QVBoxLayout(left)
        h_lay = QHBoxLayout()
        h_lay.addWidget(QLabel("<b>📝 歌词底稿</b>"))
        btn_imp = QPushButton("📂 导入 LRC/TXT")
        btn_imp.setStyleSheet("background:#e6a23c; color: white;")
        btn_imp.clicked.connect(self.import_lrc)
        btn_clr = QPushButton("🗑️ 清空")
        btn_clr.setStyleSheet("background:#f56c6c; color: white;")
        btn_clr.clicked.connect(self.clear_input)
        h_lay.addWidget(btn_imp)
        h_lay.addWidget(btn_clr)
        h_lay.addStretch()
        l_lay.addLayout(h_lay)
        self.input_txt = QTextEdit()
        self.input_txt.setPlaceholderText("在此粘贴包含时间戳的LRC...\n第一行为原文，后续相同时间戳的行为翻译。")
        self.highlighter = LrcHighlighter(self.input_txt.document())
        l_lay.addWidget(self.input_txt)
        splitter.addWidget(left)
        
        # 右侧输出
        right = QWidget()
        r_lay = QVBoxLayout(right)
        r_head_lay = QHBoxLayout()
        r_head_lay.addWidget(QLabel("<b>✅ 生成结果</b>"))
        self.btn_cali = QPushButton("🛠️ 手动校准/编辑")
        self.btn_cali.setStyleSheet("background: #909399; color: white;")
        self.btn_cali.clicked.connect(self.open_calibration)
        self.btn_cali.setEnabled(False)
        r_head_lay.addStretch()
        r_head_lay.addWidget(self.btn_cali)
        r_lay.addLayout(r_head_lay)
        self.out_txt = QTextEdit()
        self.out_txt.setStyleSheet("background:#f0f9eb; color: #333;")
        self.out_txt.setReadOnly(True)
        r_lay.addWidget(self.out_txt)
        splitter.addWidget(right)
        layout.addWidget(splitter, 1)
        
        # 选项控制
        opt_lay = QHBoxLayout()
        self.chk_force_cali = QCheckBox("启用强制校准")
        self.chk_force_cali.setChecked(True)
        self.chk_force_cali.setToolTip("当生成的时间戳与原始时间戳偏差过大时，强制对齐到原始时间戳")
        
        self.chk_avg_dist = QCheckBox("校准行平均分配时间")
        self.chk_avg_dist.setChecked(False)
        self.chk_avg_dist.setToolTip("仅在触发强制校准时生效：将该行的时间平均分配给每个字，便于后续手动微调")
        
        opt_lay.addWidget(self.chk_force_cali)
        opt_lay.addWidget(self.chk_avg_dist)
        opt_lay.addStretch()
        layout.addLayout(opt_lay)
        
        # 底部控制
        btm = QHBoxLayout()
        self.btn_run = QPushButton("🚀 开始生成")
        self.btn_run.clicked.connect(self.start)
        self.btn_run.setMinimumHeight(40)
        self.btn_stop = QPushButton("⏹️ 停止")
        self.btn_stop.setStyleSheet("background:#f56c6c; color: white;")
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setMinimumHeight(40)
        btm.addWidget(self.btn_run, 2)
        btm.addWidget(self.btn_stop, 1)
        layout.addLayout(btm)
        
        # 状态栏
        stat = QHBoxLayout()
        self.status = QLabel("就绪")
        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setMaximumHeight(10)
        self.pbar.hide()
        stat.addWidget(self.status)
        stat.addWidget(self.pbar)
        stat.addStretch()
        stat.addWidget(QLabel("保存编码:"))
        self.enc_combo = QComboBox()
        self.enc_combo.addItems(["utf-8", "gbk", "utf-8-sig"])
        stat.addWidget(self.enc_combo)
        btn_save = QPushButton("💾 保存结果")
        btn_save.clicked.connect(self.save)
        stat.addWidget(btn_save)
        layout.addLayout(stat)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config_manager, self)
        dialog.exec()

    def check_queue(self):
        # 移除进程存活检查，因为是常驻进程
        # if self.worker_process and not self.worker_process.is_alive(): ... 
        
        while True:
            try:
                msg = self.progress_queue.get_nowait()
                if isinstance(msg, str):
                    if msg.startswith("PROGRESS:"):
                        try:
                            val = int(msg.split(":")[1])
                            self.pbar.setRange(0, 100)
                            self.pbar.setValue(val)
                        except: pass
                    else:
                        self.status.setText(msg)
            except Empty: break
        try:
            result_type, result_data = self.result_queue.get_nowait()
            if result_type == "success": self.on_done(result_data)
            elif result_type == "error": self.on_error(result_data)
            elif result_type == "aborted": self.on_aborted()
            self.cleanup_worker()
        except Empty: pass

    def select_audio(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择音频", "", "Audio Files (*.mp3 *.wav *.flac *.m4a *.ogg)")
        if f:
            self.audio_path = f
            self.path_lbl.setText(f"🎵 {os.path.basename(f)}")
            self.status.setText("音频已加载")
            if self.out_txt.toPlainText().strip(): self.btn_cali.setEnabled(True)

    def clear_input(self):
        self.input_txt.clear()
        self.raw_lrc_content = None
        self.status.setText("已清空输入")

    def import_lrc(self):
        f, _ = QFileDialog.getOpenFileName(self, "导入歌词", "", "Lrc/Txt/Srt (*.lrc *.txt *.srt)")
        if not f: return
        self.import_lrc_file(f)

    def start(self):
        if not self.audio_path: return QMessageBox.warning(self, "提示", "请先选择音频文件")
        
        # 从配置中读取参数
        model_size = self.config_manager.get("MODEL_SIZE", "large-v2")
        lang_code = self.config_manager.get("LANGUAGE", "ja")
        prompt = self.config_manager.get("PROMPT", "")
        offset_ms = self.config_manager.get("OFFSET", 0)
        release_vram = self.config_manager.get("RELEASE_VRAM", True)
        
        # 验证语言设置 (如果prompt是默认值，则根据语言自动更新)
        # 这里实际上我们在SettingsDialog里已经处理了Prompt的联动，所以直接用即可。
        
        self.is_running_task = True
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_cali.setEnabled(False)
        self.pbar.show()
        self.pbar.setRange(0, 0)
        
        txt = self.input_txt.toPlainText()
        
        # 尝试使用缓存的原始LRC内容来恢复时间戳
        # 只有当缓存内容存在，且其解析出的纯文本与当前输入框内容一致时才使用
        current_timestamps = []
        used_raw_content = False
        
        if self.raw_lrc_content:
            # 临时解析一下raw内容，看看纯文本是否匹配
            temp_parser = LrcParser()
            temp_clean = temp_parser.parse(self.raw_lrc_content, ".lrc")
            
            # 宽松比较：去除所有空白字符
            def normalize(s): return "".join(s.split())
            
            if normalize(temp_clean) == normalize(txt):
                # 内容匹配，说明用户没有修改歌词文本，可以使用原始时间戳
                current_timestamps = temp_parser.lines_timestamps
                used_raw_content = True
                print("Using cached raw LRC content for timestamps.")
            else:
                print("Cached content mismatch. Fallback to input text.")
                # Debug info
                # print(f"Cached len: {len(normalize(temp_clean))}, Input len: {len(normalize(txt))}")
                
                # 更新主 parser 的状态
                self.lrc_parser = temp_parser
        
        if not used_raw_content:
            # 如果不能使用缓存（内容已修改或无缓存），则解析输入框内容
            # 注意：如果输入框里没有时间戳，这里解析出的 timestamps 全是 -1
            self.lrc_parser.parse(txt, ".lrc")
            current_timestamps = self.lrc_parser.lines_timestamps
            print("Parsed content from input text box.")
        
        lrc_parser_data = {
            'headers': self.lrc_parser.headers, 
            'lines_text': self.lrc_parser.lines_text, 
            'translations': self.lrc_parser.translations
        }
        
        # 提取 timestamps
        # current_timestamps 已经在上面准备好了
        
        if used_raw_content:
             msg = "检测到原始时间轴"
             if self.chk_force_cali.isChecked():
                 msg += "，已启用强制纠偏"
             else:
                 msg += "，但未启用强制纠偏 (可手动开启)"
             self.status.setText(msg)
        
        # 复用已有的队列和事件
        # 重置 stop_event
        self.stop_event.clear()
        
        # 清空队列中可能残留的旧消息
        while not self.result_queue.empty():
            try: self.result_queue.get_nowait()
            except: pass
        while not self.progress_queue.empty():
            try: self.progress_queue.get_nowait()
            except: pass
        
        args = WorkerArgs(
            audio_path=self.audio_path,
            model_size=model_size,
            language=lang_code,
            ref_text=txt, # 这里传进去的是 input_txt 的内容
            lrc_parser_data=lrc_parser_data,
            time_offset=offset_ms/1000.0,
            initial_prompt_input=prompt,
            # result_queue, progress_queue, stop_event 已经在 daemon 进程中持有
            model_dir=self.config_manager.get("MODEL_DIR"),
            release_vram=release_vram,
            lrc_timestamps=current_timestamps, # 传递时间戳
            enable_force_calibration=self.chk_force_cali.isChecked(),
            enable_avg_distribution=self.chk_avg_dist.isChecked()
        )

        # 确保后台进程已启动
        self.init_worker()
        # 发送任务
        self.task_queue.put(args)
        
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_queue)
        self.check_timer.start(int(TIMEOUT_CHECK_INTERVAL * 1000))

    def stop(self):
        if self.stop_event:
            self.status.setText("正在请求停止...")
            self.stop_event.set()
            # 此时不需要 terminate 进程，daemon 会检测 stop_event 并优雅退出当前任务

    def cleanup_worker(self):
        if self.check_timer: self.check_timer.stop(); self.check_timer = None
        # 不再销毁 worker_process，保持后台常驻
        # 也不要重置队列，因为它们是复用的
        pass

    def on_done(self, lrc: str):
        self.is_running_task = False
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_cali.setEnabled(True)
        self.pbar.hide()
        self.out_txt.setText(lrc)
        self.status.setText("✅ 任务完成")

    def on_aborted(self):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.pbar.hide()
        self.status.setText("🛑 任务已停止")

    def on_error(self, error_msg: str):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.pbar.hide()
        self.status.setText("❌ 任务失败")
        QMessageBox.critical(self, "错误", error_msg)

    def open_calibration(self):
        if not self.audio_path: return QMessageBox.warning(self, "提示", "没有加载音频文件")
        content = self.out_txt.toPlainText()
        if not content: return QMessageBox.warning(self, "提示", "没有歌词内容")
        
        dialog = LrcEditorDialog(self.audio_path, content, self)
        if dialog.exec():
            if dialog.result_lrc:
                self.out_txt.setText(dialog.result_lrc)
                self.status.setText("✅ 校准已应用")

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
                with open(f, 'w', encoding=self.enc_combo.currentText()) as file: file.write(txt)
                self.status.setText(f"💾 已保存: {os.path.basename(f)}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))

    def closeEvent(self, event):
        if self.is_running_task: # 仅当任务实际运行时提示
            reply = QMessageBox.question(self, '确认退出', '后台任务正在运行，确定要退出吗？', 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                                         QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.stop()
            else: 
                event.ignore()
                return

        # 关闭常驻进程
        if self.worker_process and self.worker_process.is_alive():
            self.task_queue.put("EXIT")
            # 给他一点时间退出
            time.sleep(0.1)
            
        event.accept()
