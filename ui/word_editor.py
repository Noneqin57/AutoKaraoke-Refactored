# -*- coding: utf-8 -*-
"""
字级精细打轴编辑器 (WordLevelEditor)
支持精准波形级定位、单句循环播放、Undo/Redo 历史记录与全键盘快捷工作流。
"""
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
                             QCheckBox, QFrame)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QUndoStack, QColor, QFont

from utils.time_utils import format_ms, parse_time_tag
from ui.components.clickable_slider import ClickableSlider
from ui.components.waveform_widget import WaveformWidget
from ui.commands.lrc_commands import WordTimestampCommand
from ui.styles.theme_manager import theme_manager

class WordLevelEditor(QDialog):
    """
    字级精细校对窗口 (支持区间播放、单句循环与完整撤销重做)
    """
    def __init__(self, audio_path, line_text, start_time_ms, end_time_ms, parent=None):
        super().__init__(parent)
        self.setWindowTitle("逐字精细打轴 - AutoKaraoke Editor")
        self.resize(1080, 560)
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
        
        # 初始定位到该句开始前 1秒 (留出预卷时间)
        self.start_pos = max(0, self.tokens[0]['time'] - 1000 if self.tokens else start_time_ms - 1000)
        
        self.setup_ui()
        
        self.timer = QTimer(self)
        self.timer.setInterval(40) # 25fps 丝滑刷新
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
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        
        # === 顶部卡拉OK预览卡片 ===
        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_card.setStyleSheet(f"""
            QFrame#card {{
                background-color: {theme_manager.get_color('bg_preview', '#121316')};
                border-radius: 10px;
                padding: 12px;
            }}
        """)
        p_lay = QVBoxLayout(preview_card)
        p_lay.setContentsMargins(12, 8, 12, 8)
        p_lay.setSpacing(4)
        
        top_info = QHBoxLayout()
        lbl_hint = QLabel("实时逐字卡拉OK预览")
        lbl_hint.setStyleSheet(f"color: {theme_manager.get_color('text_secondary', '#8c92a4')}; font-size: 11px; font-weight: bold;")
        range_str = f"当前区间: {format_ms(self.base_time)} -> {format_ms(self.end_time_ms)}"
        lbl_range = QLabel(range_str)
        lbl_range.setStyleSheet(f"color: {theme_manager.get_color('accent_primary', '#409eff')}; font-size: 11px; font-weight: bold;")
        top_info.addWidget(lbl_hint)
        top_info.addStretch()
        top_info.addWidget(lbl_range)
        p_lay.addLayout(top_info)
        
        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("""
            font-family: 'Microsoft YaHei', sans-serif;
            font-size: 26px;
            font-weight: bold;
            min-height: 44px;
        """)
        self.lbl_preview.setTextFormat(Qt.TextFormat.RichText)
        self.update_preview_display(0)
        p_lay.addWidget(self.lbl_preview)
        
        # 单句局部放大波形轨
        self.waveform = WaveformWidget()
        self.waveform.load_audio(self.audio_path)
        zoom_start = max(0, self.base_time - 1000)
        zoom_end = self.end_time_ms + 1000
        self.waveform.set_zoom_range(zoom_start, zoom_end)
        self.waveform.set_highlight_region(self.base_time, self.end_time_ms)
        self.waveform.set_word_markers([t['time'] for t in self.tokens])
        self.waveform.seek_requested.connect(self.set_position)
        p_lay.addWidget(self.waveform)
        
        layout.addWidget(preview_card)

        # === 播放控制与进度条栏 ===
        ctrl_card = QFrame()
        ctrl_card.setObjectName("card")
        c_lay = QVBoxLayout(ctrl_card)
        c_lay.setContentsMargins(14, 10, 14, 10)
        c_lay.setSpacing(8)

        # 进度滑块
        slider_box = QHBoxLayout()
        self.lbl_time = QLabel("00:00.000")
        self.lbl_time.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {theme_manager.get_color('accent_primary', '#409eff')};")
        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.clicked_position.connect(self.set_position)
        
        slider_box.addWidget(self.lbl_time)
        slider_box.addWidget(self.slider)
        c_lay.addLayout(slider_box)

        # 控制按钮行
        btn_ctrl_row = QHBoxLayout()
        self.btn_play = QPushButton("播放 (Space)")
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.clicked.connect(self.toggle_play)
        
        self.btn_replay = QPushButton("重播本句 (R)")
        self.btn_replay.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_replay.setObjectName("info")
        self.btn_replay.clicked.connect(self.replay_line)
        
        self.chk_loop = QCheckBox("单句循环 (Loop)")
        self.chk_loop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chk_loop.setChecked(False)
        self.chk_loop.stateChanged.connect(self.on_loop_changed)
        
        lbl_speed = QLabel("倍速:")
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_speed.currentTextChanged.connect(self.change_speed)

        self.btn_undo = QPushButton("撤销 (Ctrl+Z)")
        self.btn_undo.setObjectName("info")
        self.btn_undo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_undo.clicked.connect(self.undo)

        self.btn_redo = QPushButton("重做 (Ctrl+Y)")
        self.btn_redo.setObjectName("info")
        self.btn_redo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_redo.clicked.connect(self.redo)

        btn_ctrl_row.addWidget(self.btn_play)
        btn_ctrl_row.addWidget(self.btn_replay)
        btn_ctrl_row.addWidget(self.chk_loop)
        btn_ctrl_row.addSpacing(12)
        btn_ctrl_row.addWidget(lbl_speed)
        btn_ctrl_row.addWidget(self.combo_speed)
        btn_ctrl_row.addStretch()
        btn_ctrl_row.addWidget(self.btn_undo)
        btn_ctrl_row.addWidget(self.btn_redo)
        c_lay.addLayout(btn_ctrl_row)

        layout.addWidget(ctrl_card)

        # === 表格展示区 ===
        self.table = QTableWidget()
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setRowCount(2)
        self.table.setVerticalHeaderLabels(["歌词", "时间"])
        self.table.setColumnCount(len(self.tokens))
        self.table.horizontalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectColumns)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        
        for col, token in enumerate(self.tokens):
            item_char = QTableWidgetItem(token['char'])
            item_char.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_char.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
            self.table.setItem(0, col, item_char)
            
            time_str = format_ms(token['time'])
            item_time = QTableWidgetItem(time_str)
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(1, col, item_time)
            
        self.table.resizeRowsToContents()
        for i in range(self.table.columnCount()):
            self.table.setColumnWidth(i, 65)
            
        self.table.cellClicked.connect(self.on_cell_clicked)
        layout.addWidget(self.table, 1)
        
        # === 快捷键提示条 ===
        tips = QLabel("快捷键: [Space]播放/暂停 | [Enter]打点并跳下一字 | [←/→]选字 | [↑/↓]微调±50ms | [J/L]步进±500ms | [Ctrl+Z]撤销")
        tips.setStyleSheet(f"color: {theme_manager.get_color('text_secondary', '#8c92a4')}; font-size: 11px;")
        layout.addWidget(tips)
        
        # === 底部操作栏 ===
        btn_box = QHBoxLayout()
        btn_save = QPushButton("确认并保存 (Ctrl+S)")
        btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_save.setObjectName("success")
        btn_save.setMinimumHeight(36)
        btn_save.clicked.connect(self.save_and_close)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.setObjectName("secondary")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        
        if self.table.columnCount() > 0:
            self.table.selectColumn(0)

    def on_loop_changed(self, state):
        self.loop_playback = (state == Qt.CheckState.Checked.value or state == 2)

    def replay_line(self):
        self.player.setPosition(self.start_pos)
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.player.play()
            self.update_play_button_text()

    def set_position(self, pos):
        self.player.setPosition(pos)
        self.slider.setValue(pos)
        self.waveform.set_position(pos)
        self.lbl_time.setText(format_ms(pos))
        self.update_preview_display(pos)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            if self.player.position() >= self.end_time_ms:
                self.player.setPosition(self.start_pos)
            self.player.play()
        self.update_play_button_text()

    def update_play_button_text(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("暂停 (Space)")
        else:
            self.btn_play.setText("播放 (Space)")

    def change_speed(self, text):
        try:
            val = float(text.replace('x', ''))
            self.player.setPlaybackRate(val)
        except (ValueError, AttributeError):
            pass

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()

        # 撤销 Ctrl+Z
        if key == Qt.Key.Key_Z and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self.undo()
            return
        # 重做 Ctrl+Y 或 Ctrl+Shift+Z
        if (key == Qt.Key.Key_Y and (modifiers & Qt.KeyboardModifier.ControlModifier)) or \
           (key == Qt.Key.Key_Z and (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))):
            self.redo()
            return
        # 保存 Ctrl+S
        if key == Qt.Key.Key_S and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self.save_and_close()
            return

        if key == Qt.Key.Key_Space:
            self.toggle_play()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.stamp_current_char()
        elif key == Qt.Key.Key_Left:
            curr = self.table.currentColumn()
            if curr > 0: self.table.selectColumn(curr - 1)
        elif key == Qt.Key.Key_Right:
            curr = self.table.currentColumn()
            if curr < self.table.columnCount() - 1: self.table.selectColumn(curr + 1)
        elif key == Qt.Key.Key_Up:
            self.adjust_timestamp(50)
        elif key == Qt.Key.Key_Down:
            self.adjust_timestamp(-50)
        elif key == Qt.Key.Key_J:
            # 快退 500ms
            self.player.setPosition(max(0, self.player.position() - 500))
        elif key == Qt.Key.Key_L:
            # 快进 500ms
            self.player.setPosition(self.player.position() + 500)
        elif key == Qt.Key.Key_R:
            self.replay_line()
        else:
            super().keyPressEvent(event)

    def undo(self):
        if self.undo_stack.canUndo():
            self.undo_stack.undo()

    def redo(self):
        if self.undo_stack.canRedo():
            self.undo_stack.redo()

    def _apply_token_time(self, col: int, new_time_ms: int):
        self.tokens[col]['time'] = new_time_ms
        self.tokens[col]['edited'] = True
        self.table.item(1, col).setText(format_ms(new_time_ms))
        self.update_cell_color(col, is_active=True)
        self.waveform.set_word_markers([t['time'] for t in self.tokens])
        self.update_preview_display(self.player.position())

    def adjust_timestamp(self, delta_ms):
        curr = self.table.currentColumn()
        if curr < 0: return
        
        old_time = self.tokens[curr]['time']
        new_time = max(0, old_time + delta_ms)
        cmd = WordTimestampCommand(
            token_index=curr,
            old_time_ms=old_time,
            new_time_ms=new_time,
            update_callback=self._apply_token_time,
            description=f"微调时间 {delta_ms}ms"
        )
        self.undo_stack.push(cmd)

    def stamp_current_char(self):
        curr_col = self.table.currentColumn()
        if curr_col < 0: return
        
        current_pos = self.player.position()
        old_time = self.tokens[curr_col]['time']
        
        cmd = WordTimestampCommand(
            token_index=curr_col,
            old_time_ms=old_time,
            new_time_ms=current_pos,
            update_callback=self._apply_token_time,
            description="打点当前字"
        )
        self.undo_stack.push(cmd)
        
        # 自动移动到下一个字
        if curr_col < self.table.columnCount() - 1:
            self.table.selectColumn(curr_col + 1)

    def update_preview_display(self, current_pos):
        html = ""
        played_color = theme_manager.get_color("highlight_karaoke_played", "#67c23a")
        active_color = theme_manager.get_color("highlight_karaoke_active", "#409eff")
        unplayed_color = theme_manager.get_color("highlight_karaoke_unplayed", "#8c92a4")

        for i, token in enumerate(self.tokens):
            t = token['time']
            char = token['char']
            next_t = self.tokens[i+1]['time'] if i < len(self.tokens)-1 else self.end_time_ms
            
            if current_pos >= next_t:
                color = played_color
            elif current_pos >= t:
                color = active_color
            else:
                color = unplayed_color
            
            html += f"<span style='color:{color};'>{char}</span>"
            
        self.lbl_preview.setText(html)

    def sync_highlight(self):
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return
            
        pos = self.player.position()
        self.lbl_time.setText(format_ms(pos))
        self.slider.setValue(pos)
        self.waveform.set_position(pos)
        self.update_preview_display(pos)
        
        # 单句结束判断与单句循环
        if pos >= self.end_time_ms + 200:
            if self.loop_playback:
                self.player.setPosition(self.start_pos)
            else:
                self.player.pause()
                self.update_play_button_text()
            return
        
        active_idx = -1
        for i, token in enumerate(self.tokens):
            if pos >= token['time']:
                active_idx = i
            else:
                break
        
        if active_idx != self.last_active_idx:
            if 0 <= self.last_active_idx < self.table.columnCount():
                self.update_cell_color(self.last_active_idx, is_active=False)
            
            if 0 <= active_idx < self.table.columnCount():
                self.update_cell_color(active_idx, is_active=True)
                self.table.scrollToItem(self.table.item(0, active_idx))
            
            self.last_active_idx = active_idx

    def update_cell_color(self, col, is_active):
        token = self.tokens[col]
        item = self.table.item(0, col)
        if not item: return

        is_dark = theme_manager.is_dark()
        if is_active:
            bg = QColor("#1b3859" if is_dark else "#d9ecff")
        elif token['edited']:
            bg = QColor("#594214" if is_dark else "#fdf6ec")
        else:
            bg = QColor(theme_manager.get_color("bg_input", "#1d1f24"))
            
        item.setBackground(bg)

    def on_cell_clicked(self, row, col):
        time_ms = self.tokens[col]['time']
        self.player.setPosition(time_ms)
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.player.play()
            self.update_play_button_text()

    def reject(self):
        self.player.stop()
        super().reject()

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)

    def save_and_close(self):
        content_str = ""
        first_time_str = f"[{format_ms(self.tokens[0]['time'])}]"
        for i, token in enumerate(self.tokens):
            t_str = f"[{format_ms(token['time'])}]"
            if i == 0: content_str += token['char']
            else: content_str += f"{t_str}{token['char']}"
        
        self.result_lrc_content = content_str
        self.result_start_time = first_time_str
        self.player.stop()
        self.accept()
