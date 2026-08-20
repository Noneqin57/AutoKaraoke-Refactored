# -*- coding: utf-8 -*-
"""
字级精细打轴编辑器 (WordLevelEditor)
基于 QFluentWidgets Fluent Design 风格构建，支持波形定位、WordChip 逐字时间轴、
单句循环播放、Undo/Redo 历史记录与全键盘快捷打轴。
"""
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QTableWidget, QTableWidgetItem, QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QUndoStack, QColor, QFont, QKeyEvent

from qfluentwidgets import (CardWidget, PrimaryPushButton, PushButton, 
                            SwitchButton, ComboBox, FluentIcon as FIF, 
                            TitleLabel, CaptionLabel, StrongBodyLabel, InfoBar, InfoBarPosition)

from utils.time_utils import format_ms, parse_time_tag
from ui.components.clickable_slider import ClickableSlider
from ui.components.waveform_widget import WaveformWidget
from ui.components.word_chip import WordChipRow
from ui.commands.lrc_commands import WordTimestampCommand
from ui.styles.theme_manager import theme_manager

class WordLevelEditor(QDialog):
    """
    字级精细校对窗口 (Fluent 风格)
    """
    def __init__(self, audio_path, line_text, start_time_ms, end_time_ms, parent=None):
        super().__init__(parent)
        self.setWindowTitle("逐字精细打轴 - AutoKaraoke Editor")
        self.resize(1120, 640)
        self.audio_path = audio_path
        self.line_text = line_text
        self.base_time = start_time_ms
        self.end_time_ms = end_time_ms
        self.result_text = None
        self.result_lrc_content = None
        self.result_start_time = None
        
        self.undo_stack = QUndoStack(self)
        self.tokens = self.parse_line(line_text, start_time_ms)
        self.last_active_idx = -1
        self.loop_playback = False
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        
        # 初始定位到该句开始前 1秒 (预卷)
        self.start_pos = max(0, self.tokens[0]['time'] - 1000 if self.tokens else start_time_ms - 1000)
        
        self.setup_ui()
        
        self.timer = QTimer(self)
        self.timer.setInterval(40) # 25fps 刷新
        self.timer.timeout.connect(self.sync_highlight)
        self.timer.start()

    def on_media_status_changed(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            duration = self.player.duration()
            self.slider.setRange(0, duration)
            self.player.setPosition(self.start_pos)

    def parse_line(self, text, default_start):
        clean_text = re.sub(r'^\[\d{2}:\d{2}\.\d{2,3}\]', '', text)
        parts = re.split(r'(\[\d{2}:\d{2}\.\d{2,3}\])', clean_text)
        tokens = []
        current_time = default_start
        for part in parts:
            if not part:
                continue
            if re.match(r'^\[\d{2}:\d{2}\.\d{2,3}\]$', part):
                current_time = parse_time_tag(part)
            else:
                chars = list(part)
                for char in chars:
                    tokens.append({'char': char, 'time': current_time, 'edited': False})
        return tokens

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 20)
        layout.setSpacing(12)
        
        # === 1. 顶部卡拉OK预览与波形卡片 ===
        preview_card = CardWidget(self)
        p_lay = QVBoxLayout(preview_card)
        p_lay.setContentsMargins(16, 12, 16, 12)
        p_lay.setSpacing(8)
        
        top_info = QHBoxLayout()
        lbl_hint = StrongBodyLabel("实时逐字卡拉OK与波形")
        range_str = f"当前区间: {format_ms(self.base_time)} ➔ {format_ms(self.end_time_ms)}"
        lbl_range = CaptionLabel(range_str)
        lbl_range.setStyleSheet(f"color: {theme_manager.get_color('accent_primary')}; font-weight: bold;")
        top_info.addWidget(lbl_hint)
        top_info.addStretch()
        top_info.addWidget(lbl_range)
        p_lay.addLayout(top_info)
        
        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("""
            font-family: 'Sarasa Gothic SC', 'Microsoft YaHei', sans-serif;
            font-size: 24px;
            font-weight: bold;
            min-height: 40px;
        """)
        self.lbl_preview.setTextFormat(Qt.TextFormat.RichText)
        self.update_preview_display(0)
        p_lay.addWidget(self.lbl_preview)
        
        # 波形轨
        self.waveform = WaveformWidget(self)
        self.waveform.load_audio(self.audio_path)
        zoom_start = max(0, self.base_time - 1000)
        zoom_end = self.end_time_ms + 1000
        self.waveform.set_zoom_range(zoom_start, zoom_end)
        self.waveform.set_highlight_region(self.base_time, self.end_time_ms)
        self.waveform.set_word_markers([t['time'] for t in self.tokens])
        self.waveform.seek_requested.connect(self.set_position)
        p_lay.addWidget(self.waveform)
        
        layout.addWidget(preview_card)

        # === 2. 逐字时间轴 WordChip 行 ===
        chip_card = CardWidget(self)
        chip_lay = QVBoxLayout(chip_card)
        chip_lay.setContentsMargins(14, 10, 14, 10)
        chip_lay.setSpacing(6)

        chip_head = QHBoxLayout()
        chip_head.addWidget(StrongBodyLabel("逐字时间轴 (WordChip)"))
        chip_head.addStretch()
        chip_hint = CaptionLabel("点击字卡即可微调时间戳 · 支持 Ctrl+Z 撤销")
        chip_hint.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")
        chip_head.addWidget(chip_hint)
        chip_lay.addLayout(chip_head)

        self.word_chip_row = WordChipRow(self)
        self.word_chip_row.set_tokens(self.tokens)
        self.word_chip_row.chip_clicked.connect(self.on_chip_clicked)
        self.word_chip_row.chip_double_clicked.connect(self.on_chip_double_clicked)
        chip_lay.addWidget(self.word_chip_row)
        layout.addWidget(chip_card)

        # === 3. 播放控制与操作卡片 ===
        ctrl_card = CardWidget(self)
        c_lay = QVBoxLayout(ctrl_card)
        c_lay.setContentsMargins(16, 12, 16, 12)
        c_lay.setSpacing(10)

        # 进度滑块
        slider_box = QHBoxLayout()
        self.lbl_time = StrongBodyLabel("00:00.000")
        self.lbl_time.setStyleSheet(f"color: {theme_manager.get_color('accent_primary')};")
        self.slider = ClickableSlider(Qt.Orientation.Horizontal, self)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.clicked_position.connect(self.set_position)
        
        slider_box.addWidget(self.lbl_time)
        slider_box.addWidget(self.slider)
        c_lay.addLayout(slider_box)

        # 控制按钮行
        btn_ctrl_row = QHBoxLayout()
        self.btn_play = PrimaryPushButton("播放 (Space)", self, FIF.PLAY)
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.clicked.connect(self.toggle_play)
        
        self.btn_replay = PushButton("重播本句 (R)", self, FIF.SYNC)
        self.btn_replay.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_replay.clicked.connect(self.replay_line)
        
        self.sw_loop = SwitchButton("单句循环", self)
        self.sw_loop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sw_loop.setChecked(False)
        self.sw_loop.checkedChanged.connect(self.on_loop_changed)
        
        lbl_speed = CaptionLabel("倍速:")
        self.combo_speed = ComboBox(self)
        self.combo_speed.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_speed.currentTextChanged.connect(self.change_speed)

        self.btn_undo = PushButton("撤销 (Ctrl+Z)", self, FIF.HISTORY)
        self.btn_undo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_undo.clicked.connect(self.undo)

        self.btn_redo = PushButton("重做 (Ctrl+Y)", self, FIF.RIGHT_ARROW)
        self.btn_redo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_redo.clicked.connect(self.redo)

        btn_ctrl_row.addWidget(self.btn_play)
        btn_ctrl_row.addWidget(self.btn_replay)
        btn_ctrl_row.addWidget(self.sw_loop)
        btn_ctrl_row.addSpacing(10)
        btn_ctrl_row.addWidget(lbl_speed)
        btn_ctrl_row.addWidget(self.combo_speed)
        btn_ctrl_row.addStretch()
        btn_ctrl_row.addWidget(self.btn_undo)
        btn_ctrl_row.addWidget(self.btn_redo)
        c_lay.addLayout(btn_ctrl_row)

        layout.addWidget(ctrl_card)
        
        # === 4. 底部保存与提示 ===
        bottom_bar = QHBoxLayout()
        tips = CaptionLabel("快捷键: [Space]播放/暂停 | [Enter]打点跳下字 | [←/→]选字 | [↑/↓]微调±50ms | [J/L]步进±500ms | [Ctrl+Z]撤销")
        tips.setStyleSheet(f"color: {theme_manager.get_color('text_secondary')};")
        bottom_bar.addWidget(tips)
        bottom_bar.addStretch()

        self.btn_cancel = PushButton("取消", self, FIF.CANCEL)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = PrimaryPushButton("确认并保存 (Ctrl+S)", self, FIF.SAVE)
        self.btn_save.clicked.connect(self.save_and_close)

        bottom_bar.addWidget(self.btn_cancel)
        bottom_bar.addWidget(self.btn_save)
        layout.addLayout(bottom_bar)

    def on_loop_changed(self, is_checked: bool):
        self.loop_playback = is_checked

    def replay_line(self):
        self.player.setPosition(self.start_pos)
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.player.play()
            self.btn_play.setText("暂停 (Space)")

    def change_speed(self, speed_str):
        try:
            speed = float(speed_str.replace("x", ""))
            self.player.setPlaybackRate(speed)
        except ValueError:
            pass

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn_play.setText("播放 (Space)")
        else:
            self.player.play()
            self.btn_play.setText("暂停 (Space)")

    def set_position(self, pos):
        self.player.setPosition(pos)
        self.sync_highlight()

    def sync_highlight(self):
        pos = self.player.position()
        self.slider.blockSignals(True)
        self.slider.setValue(pos)
        self.slider.blockSignals(False)
        self.lbl_time.setText(format_ms(pos))
        
        # 同步波形游标
        self.waveform.set_position(pos)
        
        # 单句循环 (A-B Loop)
        if self.loop_playback and self.end_time_ms > 0:
            if pos >= self.end_time_ms + 200: # 稍微留一点尾音
                self.player.setPosition(self.start_pos)
                return
        
        active_idx = -1
        for i, t in enumerate(self.tokens):
            if pos >= t['time']:
                active_idx = i
            else:
                break
                
        if active_idx != self.last_active_idx:
            self.last_active_idx = active_idx
            self.update_preview_display(active_idx)
            self.word_chip_row.highlight_index(active_idx)

    def update_preview_display(self, active_idx):
        accent_color = theme_manager.accent_color
        played_color = accent_color
        unplayed_color = theme_manager.get_color("text_secondary")
        
        html = ""
        for i, t in enumerate(self.tokens):
            if i <= active_idx:
                html += f"<span style='color: {played_color}; font-weight: bold;'>{t['char']}</span>"
            else:
                html += f"<span style='color: {unplayed_color}; font-weight: normal;'>{t['char']}</span>"
        self.lbl_preview.setText(html)

    def on_chip_clicked(self, token_idx: int):
        if 0 <= token_idx < len(self.tokens):
            self.set_position(self.tokens[token_idx]['time'])

    def on_chip_double_clicked(self, token_idx: int):
        # 实时根据当前播放时间打点
        self.stamp_current_word(token_idx)

    def stamp_current_word(self, token_idx: int = -1):
        if token_idx < 0:
            token_idx = self.word_chip_row.active_index
        if 0 <= token_idx < len(self.tokens):
            pos = self.player.position()
            old_time = self.tokens[token_idx]['time']
            
            cmd = WordTimestampCommand(
                token_index=token_idx,
                old_time_ms=old_time,
                new_time_ms=pos,
                update_callback=self._apply_token_time_update,
                description=f"打点: '{self.tokens[token_idx]['char']}'"
            )
            self.undo_stack.push(cmd)

    def _apply_token_time_update(self, token_idx: int, new_time_ms: int):
        self.tokens[token_idx]['time'] = new_time_ms
        self.tokens[token_idx]['edited'] = True
        self.word_chip_row.update_token_time(token_idx, new_time_ms, edited=True)
        self.waveform.set_word_markers([t['time'] for t in self.tokens])
        self.sync_highlight()

    def undo(self):
        if self.undo_stack.canUndo():
            self.undo_stack.undo()

    def redo(self):
        if self.undo_stack.canRedo():
            self.undo_stack.redo()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()
        
        # 撤销重做
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Z:
                if modifiers & Qt.KeyboardModifier.ShiftModifier:
                    self.redo()
                else:
                    self.undo()
                event.accept()
                return
            elif key == Qt.Key.Key_Y:
                self.redo()
                event.accept()
                return
            elif key == Qt.Key.Key_S:
                self.save_and_close()
                event.accept()
                return
                
        if key == Qt.Key.Key_Space:
            self.toggle_play()
            event.accept()
        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            # 打点并定位到下一个字
            curr_idx = self.word_chip_row.active_index
            self.stamp_current_word(curr_idx)
            next_idx = min(len(self.tokens) - 1, curr_idx + 1)
            self.word_chip_row.highlight_index(next_idx)
            event.accept()
        elif key == Qt.Key.Key_R:
            self.replay_line()
            event.accept()
        elif key == Qt.Key.Key_J:
            self.set_position(max(0, self.player.position() - 500))
            event.accept()
        elif key == Qt.Key.Key_L:
            self.set_position(self.player.position() + 500)
            event.accept()
        elif key == Qt.Key.Key_Left:
            prev_idx = max(0, self.word_chip_row.active_index - 1)
            self.word_chip_row.highlight_index(prev_idx)
            if 0 <= prev_idx < len(self.tokens):
                self.set_position(self.tokens[prev_idx]['time'])
            event.accept()
        elif key == Qt.Key.Key_Right:
            next_idx = min(len(self.tokens) - 1, self.word_chip_row.active_index + 1)
            self.word_chip_row.highlight_index(next_idx)
            if 0 <= next_idx < len(self.tokens):
                self.set_position(self.tokens[next_idx]['time'])
            event.accept()
        elif key == Qt.Key.Key_Up:
            # 微调当前字 +50ms
            curr_idx = self.word_chip_row.active_index
            if 0 <= curr_idx < len(self.tokens):
                old_t = self.tokens[curr_idx]['time']
                cmd = WordTimestampCommand(curr_idx, old_t, old_t + 50, self._apply_token_time_update, "微调 +50ms")
                self.undo_stack.push(cmd)
            event.accept()
        elif key == Qt.Key.Key_Down:
            # 微调当前字 -50ms
            curr_idx = self.word_chip_row.active_index
            if 0 <= curr_idx < len(self.tokens):
                old_t = self.tokens[curr_idx]['time']
                cmd = WordTimestampCommand(curr_idx, old_t, max(0, old_t - 50), self._apply_token_time_update, "微调 -50ms")
                self.undo_stack.push(cmd)
            event.accept()
        else:
            super().keyPressEvent(event)

    def save_and_close(self):
        # 组装逐字歌词文本
        res = ""
        for t in self.tokens:
            res += f"{t['char']}[{format_ms(t['time'])}]"
            
        line_start_ms = self.tokens[0]['time'] if self.tokens else self.base_time
        full_line = f"[{format_ms(line_start_ms)}]{res}"
        
        self.result_text = full_line
        self.result_lrc_content = full_line
        self.result_start_time = line_start_ms
        self.player.stop()
        self.accept()

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)
