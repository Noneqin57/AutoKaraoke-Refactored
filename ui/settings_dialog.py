# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QFileDialog, QTabWidget, QWidget,
                             QComboBox, QSpinBox, QCheckBox, QGroupBox, QFormLayout)
from PyQt6.QtCore import Qt
from config import LANGUAGES, PROMPT_DEFAULTS

class SettingsDialog(QDialog):
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("高级设置")
        self.resize(600, 450)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # === 核心设置 Tab ===
        core_tab = QWidget()
        core_layout = QVBoxLayout(core_tab)
        
        # 模型与语言
        model_group = QGroupBox("模型与语言")
        model_form = QFormLayout()
        
        self.model_combo = QComboBox()
        self.model_combo.addItems(["tiny", "base", "small", "medium", "large-v2", "large-v3"])
        self.model_combo.setToolTip("模型越大精度越高，但速度越慢且占用更多显存。\n推荐: medium 或 large-v2")
        model_form.addRow("Whisper 模型:", self.model_combo)
        
        self.lang_combo = QComboBox()
        # 添加语言列表
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setToolTip("请务必选择歌曲的主要语言。\nWhisper 对多语言混合的支持有限，请以主歌词语言为准。")
        self.lang_combo.currentTextChanged.connect(self.on_lang_changed)
        model_form.addRow("主要语言:", self.lang_combo)
        
        model_group.setLayout(model_form)
        core_layout.addWidget(model_group)
        
        # 提示词
        prompt_group = QGroupBox("提示词 (Prompt)")
        prompt_lay = QVBoxLayout()
        self.prompt_edit = QLineEdit()
        self.prompt_edit.setPlaceholderText("例如: 这是一首中文歌曲。")
        self.prompt_edit.setToolTip("提示词可以引导模型更好地识别风格或标点。\n留空则使用默认推荐提示词。")
        prompt_lay.addWidget(self.prompt_edit)
        prompt_group.setLayout(prompt_lay)
        core_layout.addWidget(prompt_group)
        
        # 偏移
        offset_group = QGroupBox("时间偏移")
        offset_lay = QHBoxLayout()
        self.offset_spin = QSpinBox()
        self.offset_spin.setRange(-10000, 10000)
        self.offset_spin.setSuffix(" ms")
        self.offset_spin.setToolTip("整体调整时间戳。\n正数: 时间延后; 负数: 时间提前。")
        offset_lay.addWidget(QLabel("全局偏移:"))
        offset_lay.addWidget(self.offset_spin)
        offset_lay.addStretch()
        offset_group.setLayout(offset_lay)
        core_layout.addWidget(offset_group)
        
        core_layout.addStretch()
        self.tabs.addTab(core_tab, "核心参数")
        
        # === 路径与高级 Tab ===
        path_tab = QWidget()
        path_layout = QVBoxLayout(path_tab)
        
        # 路径设置
        path_group = QGroupBox("文件路径")
        path_form = QFormLayout()
        
        path_lay1 = QHBoxLayout()
        self.model_path_edit = QLineEdit()
        self.model_path_edit.setReadOnly(True)
        btn_model = QPushButton("📂")
        btn_model.clicked.connect(self.browse_model_path)
        path_lay1.addWidget(self.model_path_edit)
        path_lay1.addWidget(btn_model)
        path_form.addRow("模型存放:", path_lay1)
        
        path_lay2 = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        btn_output = QPushButton("📂")
        btn_output.clicked.connect(self.browse_output_path)
        path_lay2.addWidget(self.output_path_edit)
        path_lay2.addWidget(btn_output)
        path_form.addRow("默认保存:", path_lay2)
        
        path_group.setLayout(path_form)
        path_layout.addWidget(path_group)
        
        # 高级选项
        adv_group = QGroupBox("高级选项")
        adv_lay = QVBoxLayout()
        self.check_release_vram = QCheckBox("任务结束后释放显存")
        self.check_release_vram.setChecked(True)
        self.check_release_vram.setToolTip("取消勾选可加快连续任务的处理速度，但会长期占用显存。")
        adv_lay.addWidget(self.check_release_vram)
        adv_group.setLayout(adv_lay)
        path_layout.addWidget(adv_group)
        
        path_layout.addStretch()
        self.tabs.addTab(path_tab, "路径与高级")

        # 底部按钮
        btn_box = QHBoxLayout()
        btn_save = QPushButton("保存设置")
        btn_save.clicked.connect(self.save_settings)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        main_layout.addLayout(btn_box)

    def load_settings(self):
        # Core
        self.model_combo.setCurrentText(self.config_manager.get("MODEL_SIZE", "large-v2"))
        
        saved_lang = self.config_manager.get("LANGUAGE", "ja")
        index = self.lang_combo.findData(saved_lang)
        if index >= 0: self.lang_combo.setCurrentIndex(index)
        
        self.prompt_edit.setText(self.config_manager.get("PROMPT", ""))
        self.offset_spin.setValue(self.config_manager.get("OFFSET", 0))
        
        # Path & Adv
        self.model_path_edit.setText(self.config_manager.get("MODEL_DIR", "models"))
        self.output_path_edit.setText(self.config_manager.get("OUTPUT_DIR", ""))
        self.check_release_vram.setChecked(self.config_manager.get("RELEASE_VRAM", True))

    def on_lang_changed(self, text):
        lang_code = self.lang_combo.currentData()
        # 如果当前prompt为空或者就是默认的，则自动更新
        current_prompt = self.prompt_edit.text().strip()
        is_default = False
        for p in PROMPT_DEFAULTS.values():
            if current_prompt == p:
                is_default = True
                break
        
        if not current_prompt or is_default:
            new_default = PROMPT_DEFAULTS.get(lang_code, PROMPT_DEFAULTS["default"])
            self.prompt_edit.setText(new_default)

    def browse_model_path(self):
        d = QFileDialog.getExistingDirectory(self, "选择模型存放路径", self.model_path_edit.text())
        if d: self.model_path_edit.setText(d)

    def browse_output_path(self):
        d = QFileDialog.getExistingDirectory(self, "选择歌词保存路径", self.output_path_edit.text())
        if d: self.output_path_edit.setText(d)

    def save_settings(self):
        self.config_manager.set("MODEL_SIZE", self.model_combo.currentText())
        self.config_manager.set("LANGUAGE", self.lang_combo.currentData())
        self.config_manager.set("PROMPT", self.prompt_edit.text())
        self.config_manager.set("OFFSET", self.offset_spin.value())
        
        self.config_manager.set("MODEL_DIR", self.model_path_edit.text())
        self.config_manager.set("OUTPUT_DIR", self.output_path_edit.text())
        self.config_manager.set("RELEASE_VRAM", self.check_release_vram.isChecked())
        
        self.config_manager.save()
        self.accept()
