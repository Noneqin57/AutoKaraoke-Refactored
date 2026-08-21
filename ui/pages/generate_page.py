# -*- coding: utf-8 -*-
"""
歌词生成工作区页面 (GeneratePage)
基于 QFluentWidgets Fluent Design 风格构建，支持智能感知双模式（对齐/转写）、
音频拖拽、双栏歌词对比、参数快捷配置与进度展示。
"""
import os
import sys
import ctypes
import ctypes.util
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTextEdit, QSplitter, QFileDialog)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton, 
                            TransparentPushButton, ComboBox, DoubleSpinBox, 
                            SwitchButton, ProgressBar, FluentIcon as FIF,
                            TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel, 
                            StrongBodyLabel, InfoBadge, InfoBar, InfoBarPosition, IconWidget)

from config import LANGUAGES, ALIGNER_ENGINES, VOCAL_MODELS, DEFAULT_VOCAL_MODEL, ConfigManager
from core.lrc_parser import LrcParser
from ui.components.lrc_highlighter import EnhancedLrcHighlighter
from ui.styles.theme_manager import theme_manager

class GeneratePage(QWidget):
    # 业务信号
    start_requested = pyqtSignal(dict) # 触发开始生成
    stop_requested = pyqtSignal()      # 触发停止
    open_editor_requested = pyqtSignal(str, str) # 打开打轴编辑器 (audio_path, lrc_text)
    save_requested = pyqtSignal(str, str) # 保存结果 (content, encoding)

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.setObjectName("GeneratePage")
        self.config_manager = config_manager
        self.lrc_parser = LrcParser()
        
        self.audio_path = None
        self.raw_lrc_content = None
        self.is_running = False

        self.setup_ui()
        self.load_config_defaults()
        self.setAcceptDrops(True)

    def setup_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(28, 20, 28, 24)
        main_lay.setSpacing(14)

        # 1. 顶部 Header 区域
        main_lay.addLayout(self._build_header())

        # 2. 音频源卡片
        main_lay.addWidget(self._build_audio_card())

        # 3. 歌词双栏对比 (底稿 / 结果)
        main_lay.addWidget(self._build_lyrics_splitter(), 1)

        # 4. 选项与参数卡片
        main_lay.addWidget(self._build_params_card())

        # 5. 操作与进度卡片
        main_lay.addWidget(self._build_action_card())

    def _build_header(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setContentsMargins(0, 0, 0, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        self.title_lbl = TitleLabel("生成歌词")
        self.subtitle_lbl = CaptionLabel("粘贴歌词底稿即「强制对齐」，留空则「语音识别」· Whisper 逐字打轴")
        self.subtitle_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")

        title_box.addWidget(self.title_lbl)
        title_box.addWidget(self.subtitle_lbl)
        lay.addLayout(title_box)
        lay.addStretch()

        # 设备状态徽章 (动态检测硬件运行环境)
        if self._is_cuda_available():
            self.device_badge = InfoBadge.attension("GPU 加速已就绪")
        else:
            self.device_badge = InfoBadge.info("CPU 模式运行")
        lay.addWidget(self.device_badge)
        return lay

    @staticmethod
    def _is_cuda_available() -> bool:
        """轻量探测 NVIDIA CUDA 运行时（ctypes），避免在 UI 主进程加载 torch。"""
        try:
            if sys.platform == "win32":
                ctypes.CDLL("nvcuda.dll")
                return True
            lib = ctypes.util.find_library("cuda")
            return lib is not None
        except OSError:
            return False

    def _build_audio_card(self) -> CardWidget:
        card = CardWidget(self)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(12)

        icon_w = IconWidget(FIF.MUSIC, self)
        icon_w.setFixedSize(28, 28)
        lay.addWidget(icon_w)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        self.audio_title_lbl = StrongBodyLabel("尚未选择音频文件")
        self.audio_hint_lbl = CaptionLabel("支持 MP3 / WAV / FLAC / M4A / OGG，可直接拖拽音频到窗口")
        self.audio_hint_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")
        info_box.addWidget(self.audio_title_lbl)
        info_box.addWidget(self.audio_hint_lbl)
        lay.addLayout(info_box, 1)

        self.btn_select_audio = PrimaryPushButton("选择歌曲", self, FIF.FOLDER)
        self.btn_select_audio.setFixedWidth(120)
        self.btn_select_audio.clicked.connect(self._on_select_audio)
        lay.addWidget(self.btn_select_audio)

        return card

    def _build_lyrics_splitter(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)

        # 左侧：歌词底稿卡片
        left_card = CardWidget(self)
        l_lay = QVBoxLayout(left_card)
        l_lay.setContentsMargins(14, 12, 14, 12)
        l_lay.setSpacing(8)

        l_head = QHBoxLayout()
        l_title = StrongBodyLabel("歌词底稿 (参考文本)")
        l_head.addWidget(l_title)
        l_head.addStretch()

        self.btn_import_lrc = PushButton("导入底稿", self, FIF.DOCUMENT)
        self.btn_import_lrc.clicked.connect(self._on_import_lrc)
        self.btn_clear_input = TransparentPushButton("清空", self, FIF.DELETE)
        self.btn_clear_input.clicked.connect(self._on_clear_input)
        l_head.addWidget(self.btn_import_lrc)
        l_head.addWidget(self.btn_clear_input)
        l_lay.addLayout(l_head)

        self.input_txt = QTextEdit(self)
        self.input_txt.setPlaceholderText(
            "在此粘贴包含时间戳的 LRC / SRT 底稿，或留空直接进行全曲语音识别...\n"
            "• 若粘贴底稿：启用「强制对齐」模式，对齐精度更高。\n"
            "• 若留空：启用「语音识别」模式，自动听写全曲逐字歌词。"
        )
        self.input_highlighter = EnhancedLrcHighlighter(self.input_txt.document(), self)
        self.input_txt.textChanged.connect(self._on_input_text_changed)
        l_lay.addWidget(self.input_txt)

        splitter.addWidget(left_card)

        # 右侧：逐字 LRC 结果卡片
        right_card = CardWidget(self)
        r_lay = QVBoxLayout(right_card)
        r_lay.setContentsMargins(14, 12, 14, 12)
        r_lay.setSpacing(8)

        r_head = QHBoxLayout()
        r_title = StrongBodyLabel("生成结果 (逐字 LRC)")
        r_head.addWidget(r_title)
        r_head.addStretch()

        self.btn_open_editor = PrimaryPushButton("进入精细打轴", self, FIF.EDIT)
        self.btn_open_editor.setEnabled(False)
        self.btn_open_editor.clicked.connect(self._on_open_editor)
        r_head.addWidget(self.btn_open_editor)
        r_lay.addLayout(r_head)

        self.out_txt = QTextEdit(self)
        self.out_txt.setPlaceholderText("生成的逐字时间戳 LRC 将在此处显示...")
        self.out_highlighter = EnhancedLrcHighlighter(self.out_txt.document(), self)
        r_lay.addWidget(self.out_txt)

        splitter.addWidget(right_card)
        splitter.setSizes([520, 520])
        return splitter

    def _build_params_card(self) -> CardWidget:
        card = CardWidget(self)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(20)

        # 0. 对齐引擎选择
        e_box = QVBoxLayout()
        e_box.setSpacing(4)
        e_box.addWidget(CaptionLabel("对齐引擎"))
        self.engine_combo = ComboBox(self)
        for code, name in ALIGNER_ENGINES.items():
            self.engine_combo.addItem(name, userData=code)
        e_box.addWidget(self.engine_combo)
        lay.addLayout(e_box, 2)

        # 1. 模型选择
        m_box = QVBoxLayout()
        m_box.setSpacing(4)
        m_box.addWidget(CaptionLabel("Whisper 模型"))
        self.model_combo = ComboBox(self)
        self.model_combo.addItems([
            "large-v2 (精细打轴·推荐)",
            "large-v3",
            "medium (日常首选)",
            "small (轻快)",
            "base",
            "tiny"
        ])
        m_box.addWidget(self.model_combo)
        lay.addLayout(m_box, 2)

        # 2. 人声提取预处理 (MSST / RoFormer)
        v_box = QVBoxLayout()
        v_box.setSpacing(4)
        v_box.addWidget(CaptionLabel("人声提取 (MSST)"))
        
        v_sub_lay = QHBoxLayout()
        self.sw_vocal_sep = SwitchButton("启用", self)
        self.sw_vocal_sep.setChecked(False)
        self.vocal_combo = ComboBox(self)
        for code, name in VOCAL_MODELS.items():
            self.vocal_combo.addItem(name, userData=code)
        self.vocal_combo.setEnabled(False)
        self.sw_vocal_sep.checkedChanged.connect(self.vocal_combo.setEnabled)
        
        v_sub_lay.addWidget(self.sw_vocal_sep)
        v_sub_lay.addWidget(self.vocal_combo, 1)
        v_box.addLayout(v_sub_lay)
        lay.addLayout(v_box, 2)

        # 3. 识别语言
        l_box = QVBoxLayout()
        l_box.setSpacing(4)
        l_box.addWidget(CaptionLabel("主要语言"))
        self.lang_combo = ComboBox(self)
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, userData=code)
        l_box.addWidget(self.lang_combo)
        lay.addLayout(l_box, 2)

        # 4. 时间偏移
        o_box = QVBoxLayout()
        o_box.setSpacing(4)
        o_box.addWidget(CaptionLabel("全局偏移 (秒)"))
        self.offset_spin = DoubleSpinBox(self)
        self.offset_spin.setRange(-10.0, 10.0)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.setValue(0.0)
        o_box.addWidget(self.offset_spin)
        lay.addLayout(o_box, 1)

        # 5. 开关组
        t_box = QVBoxLayout()
        t_box.setSpacing(4)
        t_box.addWidget(CaptionLabel("校准策略"))
        
        sw_lay = QHBoxLayout()
        self.sw_force_cali = SwitchButton("强制纠偏", self)
        self.sw_force_cali.setChecked(True)
        self.sw_avg_dist = SwitchButton("平均分配", self)
        self.sw_avg_dist.setChecked(False)
        sw_lay.addWidget(self.sw_force_cali)
        sw_lay.addWidget(self.sw_avg_dist)
        t_box.addLayout(sw_lay)
        lay.addLayout(t_box, 2)

        return card

    def _build_action_card(self) -> CardWidget:
        card = CardWidget(self)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(10)

        # 进度与状态行
        stat_row = QHBoxLayout()
        self.status_lbl = BodyLabel("就绪")
        stat_row.addWidget(self.status_lbl)
        stat_row.addStretch()

        self.encoding_combo = ComboBox(self)
        self.encoding_combo.addItems(["utf-8", "gbk", "utf-8-sig"])
        stat_row.addWidget(CaptionLabel("编码:"))
        stat_row.addWidget(self.encoding_combo)

        self.btn_save = PushButton("保存结果", self, FIF.SAVE)
        self.btn_save.clicked.connect(self._on_save_clicked)
        stat_row.addWidget(self.btn_save)
        lay.addLayout(stat_row)

        # 进度条
        self.progress_bar = ProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        lay.addWidget(self.progress_bar)

        # 操作按钮行
        btn_row = QHBoxLayout()
        self.btn_run = PrimaryPushButton("开始生成 (Start)", self, FIF.PLAY)
        self.btn_run.setFixedHeight(38)
        self.btn_run.clicked.connect(self._on_run_clicked)

        self.btn_stop = PushButton("停止 (Stop)", self, FIF.CANCEL)
        self.btn_stop.setFixedHeight(38)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._on_stop_clicked)

        btn_row.addWidget(self.btn_run, 3)
        btn_row.addWidget(self.btn_stop, 1)
        lay.addLayout(btn_row)

        return card

    def load_config_defaults(self):
        saved_engine = self.config_manager.get("ALIGNER_ENGINE") or "whisper"
        for i in range(self.engine_combo.count()):
            if self.engine_combo.itemData(i) == saved_engine:
                self.engine_combo.setCurrentIndex(i)
                break

        saved_vocal_sep = bool(self.config_manager.get("ENABLE_VOCAL_SEPARATION", False))
        self.sw_vocal_sep.setChecked(saved_vocal_sep)
        self.vocal_combo.setEnabled(saved_vocal_sep)

        saved_vocal_model = self.config_manager.get("VOCAL_MODEL") or DEFAULT_VOCAL_MODEL
        for i in range(self.vocal_combo.count()):
            if self.vocal_combo.itemData(i) == saved_vocal_model:
                self.vocal_combo.setCurrentIndex(i)
                break

        saved_model = self.config_manager.get("MODEL_SIZE") or "large-v2"
        for i in range(self.model_combo.count()):
            if saved_model in self.model_combo.itemText(i):
                self.model_combo.setCurrentIndex(i)
                break
                
        saved_lang = self.config_manager.get("LANGUAGE") or "ja"
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == saved_lang:
                self.lang_combo.setCurrentIndex(i)
                break
                
        saved_offset = self.config_manager.get("OFFSET") or 0.0
        try:
            self.offset_spin.setValue(float(saved_offset))
        except (TypeError, ValueError):
            pass

    def _on_input_text_changed(self):
        text = self.input_txt.toPlainText().strip()
        if text:
            self.subtitle_lbl.setText("当前模式：【强制对齐】· 依据左侧歌词底稿进行 Whisper/CTC 毫秒级打轴")
        else:
            self.subtitle_lbl.setText("当前模式：【语音识别】· 纯音频全曲听写转写，生成逐字歌词")

    def _on_select_audio(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", "",
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.ogg);;All Files (*)"
        )
        if f:
            self.set_audio_file(f)

    def set_audio_file(self, path: str):
        self.audio_path = path
        self.audio_title_lbl.setText(f"已载入音频: {os.path.basename(path)}")
        self.audio_hint_lbl.setText(path)
        self.status_lbl.setText("音频已加载就绪")
        if self.out_txt.toPlainText().strip():
            self.btn_open_editor.setEnabled(True)

    def _on_import_lrc(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "导入歌词底稿", "",
            "Lyric Files (*.lrc *.txt *.srt);;All Files (*)"
        )
        if f:
            self.import_lrc_file(f)

    def import_lrc_file(self, f: str):
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
        self.status_lbl.setText(f"已导入底稿: {os.path.basename(f)}")
        InfoBar.success(
            title="导入成功",
            content=f"已成功载入歌词文件: {os.path.basename(f)}",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500
        )

    def _on_clear_input(self):
        self.input_txt.clear()
        self.raw_lrc_content = None
        self.status_lbl.setText("底稿已清空")

    def _on_run_clicked(self):
        if not self.audio_path:
            InfoBar.warning(
                title="提示",
                content="请先选择或拖拽音频文件！",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=3000
            )
            return

        aligner_engine = self.engine_combo.currentData() or "whisper"
        enable_vocal_sep = self.sw_vocal_sep.isChecked()
        vocal_model = self.vocal_combo.currentData() or DEFAULT_VOCAL_MODEL

        model_text = self.model_combo.currentText()
        model_size = "large-v2"
        for candidate in ["large-v3", "large-v2", "medium", "small", "base", "tiny"]:
            if candidate in model_text:
                model_size = candidate
                break

        lang = self.lang_combo.currentData() or "ja"
        offset = self.offset_spin.value()
        force_cali = self.sw_force_cali.isChecked()
        avg_dist = self.sw_avg_dist.isChecked()
        ref_text = self.input_txt.toPlainText().strip()

        task_data = {
            "audio_path": self.audio_path,
            "aligner_engine": aligner_engine,
            "enable_vocal_separation": enable_vocal_sep,
            "vocal_model": vocal_model,
            "model_size": model_size,
            "language": lang,
            "offset": offset,
            "force_cali": force_cali,
            "avg_dist": avg_dist,
            "ref_text": ref_text,
            "raw_lrc_content": self.raw_lrc_content
        }

        self.set_running_state(True)
        self.start_requested.emit(task_data)

    def _on_stop_clicked(self):
        self.stop_requested.emit()

    def _on_open_editor(self):
        if self.audio_path and self.out_txt.toPlainText().strip():
            self.open_editor_requested.emit(self.audio_path, self.out_txt.toPlainText())

    def _on_save_clicked(self):
        content = self.out_txt.toPlainText().strip()
        if not content:
            InfoBar.warning(
                title="提示",
                content="当前没有可保存的逐字 LRC 结果！",
                parent=self,
                position=InfoBarPosition.TOP_RIGHT,
                duration=2500
            )
            return
        enc = self.encoding_combo.currentText()
        self.save_requested.emit(content, enc)

    def set_running_state(self, is_running: bool):
        self.is_running = is_running
        self.btn_run.setEnabled(not is_running)
        self.btn_stop.setEnabled(is_running)
        self.btn_select_audio.setEnabled(not is_running)
        self.btn_import_lrc.setEnabled(not is_running)
        if is_running:
            self.progress_bar.show()
            self.progress_bar.setValue(0)
            self.status_lbl.setText("正在准备启动后台推理进程...")
        else:
            self.progress_bar.hide()

    def update_progress(self, val: int, msg: str = ""):
        self.progress_bar.setValue(val)
        if msg:
            self.status_lbl.setText(msg)

    def set_result_text(self, text: str):
        self.out_txt.setText(text)
        if text.strip() and self.audio_path:
            self.btn_open_editor.setEnabled(True)

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
                self.set_audio_file(f)
                InfoBar.success(
                    title="音频已载入",
                    content=f"已载入音频: {os.path.basename(f)}",
                    parent=self,
                    position=InfoBarPosition.TOP_RIGHT,
                    duration=2500
                )
            elif ext in ['.lrc', '.txt', '.srt']:
                self.import_lrc_file(f)
