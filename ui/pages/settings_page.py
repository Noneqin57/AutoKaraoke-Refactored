# -*- coding: utf-8 -*-
"""
设置页面 (SettingsPage)
基于 QFluentWidgets Fluent Design 风格构建，提供核心识别参数、提示词、目录路径与主题外观管理。
"""
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QFileDialog, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal

from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton, 
                            ComboBox, LineEdit, SpinBox, DoubleSpinBox, 
                            SwitchButton, FluentIcon as FIF, TitleLabel, 
                            CaptionLabel, StrongBodyLabel, InfoBar, 
                            InfoBarPosition, SmoothScrollArea)

from config import (LANGUAGES, ALIGNER_ENGINES, VOCAL_MODELS, 
                    DEFAULT_VOCAL_MODEL, PROMPT_DEFAULTS, ConfigManager)
from ui.styles.theme_manager import theme_manager

class SettingsPage(QWidget):
    theme_applied = pyqtSignal(str)

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsPage")
        self.config_manager = config_manager
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(0, 0, 0, 0)

        scroll = SmoothScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(SmoothScrollArea.Shape.NoFrame)

        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setContentsMargins(28, 20, 28, 24)
        lay.setSpacing(16)

        # 1. 顶部 Header
        t_box = QVBoxLayout()
        t_box.setSpacing(2)
        t_box.addWidget(TitleLabel("系统设置"))
        sub_lbl = CaptionLabel("配置 Whisper 识别引擎、提示词策略、存储路径与 Fluent 主题")
        sub_lbl.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")
        t_box.addWidget(sub_lbl)
        lay.addLayout(t_box)

        # 2. 核心参数卡片
        core_card = CardWidget(container)
        c_lay = QVBoxLayout(core_card)
        c_lay.setContentsMargins(18, 14, 18, 14)
        c_lay.setSpacing(12)

        c_lay.addWidget(StrongBodyLabel("默认识别与对齐参数"))

        # 引擎 & 模型 & 语言
        row1 = QHBoxLayout()
        e_box = QVBoxLayout()
        e_box.addWidget(CaptionLabel("默认对齐引擎"))
        self.engine_combo = ComboBox(core_card)
        for code, name in ALIGNER_ENGINES.items():
            self.engine_combo.addItem(name, userData=code)
        e_box.addWidget(self.engine_combo)
        row1.addLayout(e_box, 1)

        m_box = QVBoxLayout()
        m_box.addWidget(CaptionLabel("默认模型"))
        self.model_combo = ComboBox(core_card)
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v2", "large-v3"])
        m_box.addWidget(self.model_combo)
        row1.addLayout(m_box, 1)

        l_box = QVBoxLayout()
        l_box.addWidget(CaptionLabel("默认语言"))
        self.lang_combo = ComboBox(core_card)
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, userData=code)
        self.lang_combo.currentTextChanged.connect(self._on_lang_changed)
        l_box.addWidget(self.lang_combo)
        row1.addLayout(l_box, 1)
        c_lay.addLayout(row1)

        # 提示词
        p_box = QVBoxLayout()
        p_box.addWidget(CaptionLabel("提示词引导 (Initial Prompt)"))
        self.prompt_edit = LineEdit(core_card)
        self.prompt_edit.setPlaceholderText("例如: 这是一首中文歌曲，歌词包含标点符号。")
        p_box.addWidget(self.prompt_edit)
        c_lay.addLayout(p_box)

        # 偏移 & 校准阈值
        row2 = QHBoxLayout()
        o_box = QVBoxLayout()
        o_box.addWidget(CaptionLabel("全局时间偏移 (ms)"))
        self.offset_spin = SpinBox(core_card)
        self.offset_spin.setRange(-10000, 10000)
        self.offset_spin.setSingleStep(50)
        o_box.addWidget(self.offset_spin)
        row2.addLayout(o_box, 1)

        t_box = QVBoxLayout()
        t_box.addWidget(CaptionLabel("强制校准偏差阈值 (秒)"))
        self.calibration_spin = DoubleSpinBox(core_card)
        self.calibration_spin.setRange(0.1, 10.0)
        self.calibration_spin.setSingleStep(0.1)
        self.calibration_spin.setDecimals(1)
        t_box.addWidget(self.calibration_spin)
        row2.addLayout(t_box, 1)
        c_lay.addLayout(row2)

        # 人声提取配置
        row_vocal = QHBoxLayout()
        v_sw_box = QVBoxLayout()
        v_sw_box.addWidget(CaptionLabel("默认开启人声提取 (MSST)"))
        self.sw_vocal_sep = SwitchButton("人声分离", core_card)
        self.sw_vocal_sep.setChecked(False)
        v_sw_box.addWidget(self.sw_vocal_sep)
        row_vocal.addLayout(v_sw_box, 1)

        v_m_box = QVBoxLayout()
        v_m_box.addWidget(CaptionLabel("默认人声提取模型"))
        self.vocal_model_combo = ComboBox(core_card)
        for code, name in VOCAL_MODELS.items():
            self.vocal_model_combo.addItem(name, userData=code)
        self.vocal_model_combo.setEnabled(False)
        self.sw_vocal_sep.checkedChanged.connect(self.vocal_model_combo.setEnabled)
        v_m_box.addWidget(self.vocal_model_combo)
        row_vocal.addLayout(v_m_box, 2)
        c_lay.addLayout(row_vocal)

        lay.addWidget(core_card)

        # 3. 存储路径卡片
        path_card = CardWidget(container)
        p_lay = QVBoxLayout(path_card)
        p_lay.setContentsMargins(18, 14, 18, 14)
        p_lay.setSpacing(12)

        p_lay.addWidget(StrongBodyLabel("存储与目录"))

        # 模型目录
        m_path_box = QVBoxLayout()
        m_path_box.addWidget(CaptionLabel("Whisper 模型存放目录"))
        m_path_row = QHBoxLayout()
        self.model_dir_edit = LineEdit(path_card)
        self.btn_browse_model = PushButton("浏览...", path_card, FIF.FOLDER)
        self.btn_browse_model.clicked.connect(self._browse_model_dir)
        m_path_row.addWidget(self.model_dir_edit, 1)
        m_path_row.addWidget(self.btn_browse_model)
        m_path_box.addLayout(m_path_row)
        p_lay.addLayout(m_path_box)

        # 输出目录
        o_path_box = QVBoxLayout()
        o_path_box.addWidget(CaptionLabel("默认输出保存目录"))
        o_path_row = QHBoxLayout()
        self.output_dir_edit = LineEdit(path_card)
        self.btn_browse_output = PushButton("浏览...", path_card, FIF.FOLDER)
        self.btn_browse_output.clicked.connect(self._browse_output_dir)
        o_path_row.addWidget(self.output_dir_edit, 1)
        o_path_row.addWidget(self.btn_browse_output)
        o_path_box.addLayout(o_path_row)
        p_lay.addLayout(o_path_box)

        lay.addWidget(path_card)

        # 4. 外观与性能卡片
        app_card = CardWidget(container)
        a_lay = QVBoxLayout(app_card)
        a_lay.setContentsMargins(18, 14, 18, 14)
        a_lay.setSpacing(12)

        a_lay.addWidget(StrongBodyLabel("界面外观与硬件策略"))

        app_row = QHBoxLayout()
        th_box = QVBoxLayout()
        th_box.addWidget(CaptionLabel("应用主题模式"))
        self.theme_combo = ComboBox(app_card)
        self.theme_combo.addItem("深色模式 (Dark)", userData="dark")
        self.theme_combo.addItem("浅色模式 (Light)", userData="light")
        self.theme_combo.addItem("跟随系统 (Auto)", userData="auto")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        th_box.addWidget(self.theme_combo)
        app_row.addLayout(th_box, 1)

        vram_box = QVBoxLayout()
        vram_box.addWidget(CaptionLabel("任务完成后释放显存"))
        self.sw_release_vram = SwitchButton("释放显存", app_card)
        self.sw_release_vram.setChecked(True)
        vram_box.addWidget(self.sw_release_vram)
        app_row.addLayout(vram_box, 1)

        a_lay.addLayout(app_row)
        lay.addWidget(app_card)

        # 5. 底部保存与重置按钮
        btn_bar = QHBoxLayout()
        self.btn_reset = PushButton("恢复默认", container, FIF.CANCEL)
        self.btn_reset.clicked.connect(self.reset_defaults)
        self.btn_save = PrimaryPushButton("保存全部设置", container, FIF.SAVE)
        self.btn_save.clicked.connect(self.save_settings)
        btn_bar.addStretch()
        btn_bar.addWidget(self.btn_reset)
        btn_bar.addWidget(self.btn_save)
        lay.addLayout(btn_bar)

        scroll.setWidget(container)
        main_lay.addWidget(scroll)

    def load_settings(self):
        # 引擎
        engine = self.config_manager.get("ALIGNER_ENGINE") or "whisper"
        for i in range(self.engine_combo.count()):
            if self.engine_combo.itemData(i) == engine:
                self.engine_combo.setCurrentIndex(i)
                break

        # 人声提取
        vocal_sep = bool(self.config_manager.get("ENABLE_VOCAL_SEPARATION", False))
        self.sw_vocal_sep.setChecked(vocal_sep)
        self.vocal_model_combo.setEnabled(vocal_sep)

        vocal_model = self.config_manager.get("VOCAL_MODEL") or DEFAULT_VOCAL_MODEL
        for i in range(self.vocal_model_combo.count()):
            if self.vocal_model_combo.itemData(i) == vocal_model:
                self.vocal_model_combo.setCurrentIndex(i)
                break

        # 模型
        model = self.config_manager.get("MODEL_SIZE") or "large-v2"
        idx = self.model_combo.findText(model)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)
            
        # 语言
        lang = self.config_manager.get("LANGUAGE") or "ja"
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == lang:
                self.lang_combo.setCurrentIndex(i)
                break
                
        # 提示词
        prompt = self.config_manager.get("PROMPT") or ""
        self.prompt_edit.setText(prompt)
        
        # 偏移与阈值
        offset_ms = int(float(self.config_manager.get("OFFSET") or 0.0) * 1000)
        self.offset_spin.setValue(offset_ms)
        
        cali = float(self.config_manager.get("CALIBRATION_THRESHOLD") or 1.5)
        self.calibration_spin.setValue(cali)
        
        # 路径
        self.model_dir_edit.setText(self.config_manager.get("MODEL_DIR") or "models")
        self.output_dir_edit.setText(self.config_manager.get("OUTPUT_DIR") or "output")
        
        # 显存
        self.sw_release_vram.setChecked(bool(self.config_manager.get("RELEASE_VRAM", True)))
        
        # 主题
        theme = (self.config_manager.get("THEME") or "dark").lower()
        for i in range(self.theme_combo.count()):
            if self.theme_combo.itemData(i) == theme:
                self.theme_combo.setCurrentIndex(i)
                break

    def _on_lang_changed(self):
        lang_code = self.lang_combo.currentData()
        if not self.prompt_edit.text().strip():
            default_prompt = PROMPT_DEFAULTS.get(lang_code, PROMPT_DEFAULTS["default"])
            self.prompt_edit.setPlaceholderText(f"推荐: {default_prompt}")

    def _on_theme_changed(self):
        theme_code = self.theme_combo.currentData() or "dark"
        theme_manager.set_theme(theme_code)
        self.theme_applied.emit(theme_code)

    def _browse_model_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择模型存放目录", self.model_dir_edit.text())
        if d:
            self.model_dir_edit.setText(d)

    def _browse_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出保存目录", self.output_dir_edit.text())
        if d:
            self.output_dir_edit.setText(d)

    def save_settings(self):
        self.config_manager.set("ALIGNER_ENGINE", self.engine_combo.currentData())
        self.config_manager.set("ENABLE_VOCAL_SEPARATION", self.sw_vocal_sep.isChecked())
        self.config_manager.set("VOCAL_MODEL", self.vocal_model_combo.currentData() or DEFAULT_VOCAL_MODEL)
        self.config_manager.set("MODEL_SIZE", self.model_combo.currentText())
        self.config_manager.set("LANGUAGE", self.lang_combo.currentData())
        self.config_manager.set("PROMPT", self.prompt_edit.text().strip())
        self.config_manager.set("OFFSET", self.offset_spin.value() / 1000.0)
        self.config_manager.set("CALIBRATION_THRESHOLD", self.calibration_spin.value())
        self.config_manager.set("MODEL_DIR", self.model_dir_edit.text().strip())
        self.config_manager.set("OUTPUT_DIR", self.output_dir_edit.text().strip())
        self.config_manager.set("RELEASE_VRAM", self.sw_release_vram.isChecked())
        self.config_manager.set("THEME", self.theme_combo.currentData())
        self.config_manager.save()

        InfoBar.success(
            title="设置已保存",
            content="系统配置已成功保存并立即生效！",
            parent=self,
            position=InfoBarPosition.TOP_RIGHT,
            duration=2500
        )

    def reset_defaults(self):
        for i in range(self.engine_combo.count()):
            if self.engine_combo.itemData(i) == "whisper":
                self.engine_combo.setCurrentIndex(i)
                break
        self.sw_vocal_sep.setChecked(False)
        self.vocal_model_combo.setEnabled(False)
        for i in range(self.vocal_model_combo.count()):
            if self.vocal_model_combo.itemData(i) == DEFAULT_VOCAL_MODEL:
                self.vocal_model_combo.setCurrentIndex(i)
                break
        self.model_combo.setCurrentText("large-v2")
        for i in range(self.lang_combo.count()):
            if self.lang_combo.itemData(i) == "ja":
                self.lang_combo.setCurrentIndex(i)
                break
        self.prompt_edit.clear()
        self.offset_spin.setValue(0)
        self.calibration_spin.setValue(1.5)
        self.model_dir_edit.setText("models")
        self.output_dir_edit.setText("output")
        self.sw_release_vram.setChecked(True)
        self.theme_combo.setCurrentIndex(0)
        self.save_settings()
