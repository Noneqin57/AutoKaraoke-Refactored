# -*- coding: utf-8 -*-
"""
歌词精细校准对话框 (LrcEditorDialog)
提供逐行同步打点、时间轴整体/局部实时偏移、双向跳转、字级精细联动与完整撤销重做。
"""
import os
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
                             QFrame, QComboBox, QSpinBox)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QUndoStack, QUndoCommand, QColor

from utils.time_utils import format_ms, parse_time_tag
from ui.word_editor import WordLevelEditor
from ui.components.clickable_slider import ClickableSlider
from ui.components.waveform_widget import WaveformWidget
from ui.commands.lrc_commands import BatchLineShiftCommand
from ui.styles.theme_manager import theme_manager

class LineStampCommand(QUndoCommand):
    """逐行打点/单行时间戳修改指令"""
    def __init__(self, dialog, row: int, old_time_str: str, old_text: str,
                 new_time_str: str, new_text: str, affected_translations: list,
                 description: str = "修改行时间戳"):
        super().__init__(description)
        self.dialog = dialog
        self.row = row
        self.old_time_str = old_time_str
        self.old_text = old_text
        self.new_time_str = new_time_str
        self.new_text = new_text
        self.affected_translations = affected_translations # [(row, old_time, new_time)]

    def redo(self):
        self.dialog.table.setItem(self.row, 0, QTableWidgetItem(self.new_time_str))
        self.dialog.table.setItem(self.row, 1, QTableWidgetItem(self.new_text))
        for r, _, new_t in self.affected_translations:
            self.dialog.table.setItem(r, 0, QTableWidgetItem(new_t))
        self.dialog.cache_timestamps()
        self.dialog.refresh_playback_view()

    def undo(self):
        self.dialog.table.setItem(self.row, 0, QTableWidgetItem(self.old_time_str))
        self.dialog.table.setItem(self.row, 1, QTableWidgetItem(self.old_text))
        for r, old_t, _ in self.affected_translations:
            self.dialog.table.setItem(r, 0, QTableWidgetItem(old_t))
        self.dialog.cache_timestamps()
        self.dialog.refresh_playback_view()


class LrcEditorDialog(QDialog):
    def __init__(self, audio_path, lrc_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle("歌词精细校准与时间轴调整 - AutoKaraoke Editor")
        self.resize(1080, 840)
        self.audio_path = audio_path
        self.lrc_content = lrc_content
        self.result_lrc = None
        
        self.undo_stack = QUndoStack(self)
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        self.cached_timestamps = []  # [(row, time_ms), ...]
        self.last_highlight_row = -1
        self.translation_rows = set()
        
        self.setup_ui()
        self.load_lrc_data()
        self.load_audio()
        
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.update_progress)
        self.timer.start()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        
        # === 顶部卡拉OK预览卡片 ===
        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_card.setStyleSheet(f"""
            QFrame#card {{
                background-color: {theme_manager.get_color('bg_preview', '#121316')};
                border-radius: 10px;
                padding: 10px;
            }}
        """)
        p_lay = QVBoxLayout(preview_card)
        p_lay.setContentsMargins(12, 6, 12, 6)
        p_lay.setSpacing(2)
        
        top_info = QHBoxLayout()
        lbl_hint = QLabel("实时逐行预览 (双击下方行进入逐字打轴 | 调整时间轴可直接试听效果)")
        lbl_hint.setStyleSheet(f"color: {theme_manager.get_color('text_secondary', '#8c92a4')}; font-size: 11px; font-weight: bold;")
        top_info.addWidget(lbl_hint)
        p_lay.addLayout(top_info)
        
        self.lbl_line_preview = QLabel()
        self.lbl_line_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_line_preview.setStyleSheet("""
            font-family: 'Microsoft YaHei', sans-serif;
            font-size: 22px;
            font-weight: bold;
            min-height: 48px;
        """)
        self.lbl_line_preview.setText("<span style='color:#8c92a4;'>等待播放...</span>")
        p_lay.addWidget(self.lbl_line_preview)
        
        # 音频波形可视化组件
        self.waveform = WaveformWidget()
        self.waveform.seek_requested.connect(self.set_position)
        p_lay.addWidget(self.waveform)
        
        layout.addWidget(preview_card)

        # === 歌词表格 ===
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["时间戳", "歌词内容"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        
        self.table.cellDoubleClicked.connect(self.seek_to_row)
        self.table.cellPressed.connect(self.pause_on_click)
        layout.addWidget(self.table, 1)
        
        # === 播放控制与进度条卡片 ===
        ctrl_card = QFrame()
        ctrl_card.setObjectName("card")
        c_lay = QVBoxLayout(ctrl_card)
        c_lay.setContentsMargins(14, 10, 14, 10)
        c_lay.setSpacing(8)

        slider_box = QHBoxLayout()
        self.lbl_curr = QLabel("00:00.000")
        self.lbl_curr.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {theme_manager.get_color('accent_primary', '#409eff')};")
        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.clicked_position.connect(self.set_position)
        self.lbl_total = QLabel("00:00.000")
        self.lbl_total.setStyleSheet(f"color: {theme_manager.get_color('text_secondary', '#8c92a4')};")
        
        slider_box.addWidget(self.lbl_curr)
        slider_box.addWidget(self.slider)
        slider_box.addWidget(self.lbl_total)
        c_lay.addLayout(slider_box)

        btn_ctrl_row = QHBoxLayout()
        self.btn_play = QPushButton("播放/暂停 (Space)")
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.clicked.connect(self.toggle_play)

        btn_stamp = QPushButton("智能同步写入 (Enter)")
        btn_stamp.setObjectName("warning")
        btn_stamp.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_stamp.clicked.connect(self.stamp_current_time)

        self.btn_undo = QPushButton("撤销 (Ctrl+Z)")
        self.btn_undo.setObjectName("info")
        self.btn_undo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_undo.clicked.connect(self.undo)

        self.btn_redo = QPushButton("重做 (Ctrl+Y)")
        self.btn_redo.setObjectName("info")
        self.btn_redo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_redo.clicked.connect(self.redo)

        btn_ctrl_row.addWidget(self.btn_play)
        btn_ctrl_row.addWidget(btn_stamp)
        btn_ctrl_row.addStretch()
        btn_ctrl_row.addWidget(self.btn_undo)
        btn_ctrl_row.addWidget(self.btn_redo)
        c_lay.addLayout(btn_ctrl_row)

        layout.addWidget(ctrl_card)

        # === 【全新】时间轴实时偏移调整卡片 (Offset Toolbar) ===
        offset_card = QFrame()
        offset_card.setObjectName("card")
        o_lay = QHBoxLayout(offset_card)
        o_lay.setContentsMargins(14, 8, 14, 8)
        o_lay.setSpacing(8)

        lbl_offset_title = QLabel("时间轴偏移调整:")
        lbl_offset_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        o_lay.addWidget(lbl_offset_title)

        self.combo_offset_scope = QComboBox()
        self.combo_offset_scope.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_offset_scope.addItem("全部歌词 (All)", "all")
        self.combo_offset_scope.addItem("当前行至末尾 (To End)", "to_end")
        self.combo_offset_scope.addItem("仅选中的行 (Selected)", "selected")
        self.combo_offset_scope.setToolTip("选择时间偏移的影响范围")
        o_lay.addWidget(self.combo_offset_scope)

        # 快捷微调按钮
        btn_m200 = QPushButton("-200ms")
        btn_m200.setObjectName("info")
        btn_m200.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_m200.setToolTip("将目标范围时间戳提前 200ms")
        btn_m200.clicked.connect(lambda: self.apply_quick_offset(-200))
        o_lay.addWidget(btn_m200)

        btn_m50 = QPushButton("-50ms")
        btn_m50.setObjectName("info")
        btn_m50.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_m50.setToolTip("将目标范围时间戳提前 50ms")
        btn_m50.clicked.connect(lambda: self.apply_quick_offset(-50))
        o_lay.addWidget(btn_m50)

        btn_p50 = QPushButton("+50ms")
        btn_p50.setObjectName("info")
        btn_p50.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_p50.setToolTip("将目标范围时间戳延后 50ms")
        btn_p50.clicked.connect(lambda: self.apply_quick_offset(50))
        o_lay.addWidget(btn_p50)

        btn_p200 = QPushButton("+200ms")
        btn_p200.setObjectName("info")
        btn_p200.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_p200.setToolTip("将目标范围时间戳延后 200ms")
        btn_p200.clicked.connect(lambda: self.apply_quick_offset(200))
        o_lay.addWidget(btn_p200)

        o_lay.addSpacing(6)

        self.spin_offset = QSpinBox()
        self.spin_offset.setRange(-30000, 30000)
        self.spin_offset.setSingleStep(50)
        self.spin_offset.setValue(0)
        self.spin_offset.setSuffix(" ms")
        self.spin_offset.setToolTip("自定义偏移量：正数延后，负数提前。回车或点击应用。")
        self.spin_offset.returnPressed.connect(self.apply_spinbox_offset)
        o_lay.addWidget(self.spin_offset)

        btn_apply_spin = QPushButton("应用自定义偏移")
        btn_apply_spin.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_apply_spin.clicked.connect(self.apply_spinbox_offset)
        o_lay.addWidget(btn_apply_spin)

        layout.addWidget(offset_card)
        
        # === 快捷键提示条 ===
        tips = QLabel("快捷键: [Space]播放/暂停 | [Enter]写入当前时间戳并跳下行 | [Ctrl+←/→]微调±100ms | [J/L]步进±1s | [Ctrl+Z]撤销偏移")
        tips.setStyleSheet(f"color: {theme_manager.get_color('text_secondary', '#8c92a4')}; font-size: 11px;")
        layout.addWidget(tips)

        # === 底部保存/取消栏 ===
        btn_box = QHBoxLayout()
        btn_save = QPushButton("保存并应用 (Ctrl+S)")
        btn_save.setObjectName("success")
        btn_save.setMinimumHeight(36)
        btn_save.clicked.connect(self.save_lrc)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("secondary")
        btn_cancel.setMinimumHeight(36)
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        
        self.table.keyPressEvent = self.table_key_event

    def load_audio(self):
        if self.audio_path and os.path.exists(self.audio_path):
            self.player.setSource(QUrl.fromLocalFile(self.audio_path))
            self.player.mediaStatusChanged.connect(self.on_media_status)
            self.waveform.load_audio(self.audio_path)
    
    def on_media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            duration = self.player.duration()
            self.slider.setRange(0, duration)
            self.waveform.set_duration(duration)
            self.lbl_total.setText(format_ms(duration))

    def load_lrc_data(self):
        lines = self.lrc_content.splitlines()
        self.table.setRowCount(0)
        self.translation_rows.clear()
        pattern = re.compile(r'^(\[\d{2}:\d{2}\.\d{2,3}\])(.*)')
        row = 0
        last_timestamp = None
        
        for line in lines:
            line = line.strip()
            if not line: continue
            match = pattern.match(line)
            if match:
                timestamp = match.group(1)
                content = match.group(2)
                
                self.table.insertRow(row)
                if timestamp == last_timestamp and row > 0:
                    self.translation_rows.add(row)
                
                self.table.setItem(row, 0, QTableWidgetItem(timestamp))
                self.table.setItem(row, 1, QTableWidgetItem(content))
                last_timestamp = timestamp
                row += 1
            else:
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(""))
                self.table.setItem(row, 1, QTableWidgetItem(line))
                row += 1
        
        self.cache_timestamps()

    def table_key_event(self, event):
        key = event.key()
        modifiers = event.modifiers()

        if key == Qt.Key.Key_Z and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self.undo()
            return
        if (key == Qt.Key.Key_Y and (modifiers & Qt.KeyboardModifier.ControlModifier)) or \
           (key == Qt.Key.Key_Z and (modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))):
            self.redo()
            return
        if key == Qt.Key.Key_S and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self.save_lrc()
            return

        if key == Qt.Key.Key_Space:
            self.toggle_play()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.stamp_current_time()
        elif key == Qt.Key.Key_Left and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self.adjust_timestamp(-100)
        elif key == Qt.Key.Key_Right and (modifiers & Qt.KeyboardModifier.ControlModifier):
            self.adjust_timestamp(100)
        elif key == Qt.Key.Key_J:
            self.player.setPosition(max(0, self.player.position() - 1000))
        elif key == Qt.Key.Key_L:
            self.player.setPosition(self.player.position() + 1000)
        else:
            QTableWidget.keyPressEvent(self.table, event)

    def undo(self):
        if self.undo_stack.canUndo():
            self.undo_stack.undo()

    def redo(self):
        if self.undo_stack.canRedo():
            self.undo_stack.redo()

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self.update_play_button_text()

    def update_play_button_text(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("暂停 (Space)")
        else:
            self.btn_play.setText("播放 (Space)")

    def update_progress(self):
        pos = self.player.position()
        self.slider.setValue(pos)
        self.waveform.set_position(pos)
        self.lbl_curr.setText(format_ms(pos))
        self.highlight_current_line(pos)
        self.update_line_preview(pos)

    def set_position(self, pos):
        self.player.setPosition(pos)
        self.slider.setValue(pos)
        self.waveform.set_position(pos)
        self.lbl_curr.setText(format_ms(pos))
        self.update_line_preview(pos)
        self.highlight_current_line(pos)

    def pause_on_click(self, row, col):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.update_play_button_text()

    def seek_to_row(self, row, col):
        """双击进入逐字编辑模式"""
        time_item = self.table.item(row, 0)
        text_item = self.table.item(row, 1)
        
        if not time_item or not text_item: return
        
        time_str = time_item.text()
        text_content = text_item.text()
        start_ms = parse_time_tag(time_str)
        
        end_ms = self.player.duration()
        next_row = row + 1
        while next_row < self.table.rowCount():
            next_time_item = self.table.item(next_row, 0)
            if next_time_item:
                next_start_ms = parse_time_tag(next_time_item.text())
                if next_start_ms > start_ms:
                    end_ms = next_start_ms
                    break
            next_row += 1
        
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.update_play_button_text()
            
        editor = WordLevelEditor(self.audio_path, text_content, start_ms, end_ms, self)

        if editor.exec():
            if editor.result_start_time:
                self.table.setItem(row, 0, QTableWidgetItem(editor.result_start_time))
            if editor.result_lrc_content:
                self.table.setItem(row, 1, QTableWidgetItem(editor.result_lrc_content))
            self.cache_timestamps()
            self.refresh_playback_view()
        # 编辑器自带 40ms 刷新 timer 与 QMediaPlayer，用完立即销毁避免累积泄漏
        editor.deleteLater()

    # === 时间轴偏移工具箱逻辑 ===
    def get_target_rows_for_offset(self) -> list:
        scope = self.combo_offset_scope.currentData() or "all"
        total_rows = self.table.rowCount()
        
        if scope == "all":
            return list(range(total_rows))
        
        selected_items = self.table.selectedItems()
        selected_rows = sorted(list(set(it.row() for it in selected_items)))
        
        if scope == "to_end":
            start_row = selected_rows[0] if selected_rows else 0
            return list(range(start_row, total_rows))
        
        if scope == "selected":
            return selected_rows if selected_rows else list(range(total_rows))
            
        return list(range(total_rows))

    def apply_quick_offset(self, delta_ms: int):
        self.apply_batch_offset(delta_ms)

    def apply_spinbox_offset(self):
        val = self.spin_offset.value()
        if val != 0:
            self.apply_batch_offset(val)
            self.spin_offset.setValue(0)

    def apply_batch_offset(self, delta_ms: int):
        if delta_ms == 0:
            return
            
        target_rows = self.get_target_rows_for_offset()
        if not target_rows:
            return

        old_data = []
        new_data = []

        for r in target_rows:
            t_item = self.table.item(r, 0)
            c_item = self.table.item(r, 1)
            
            old_time_str = t_item.text() if t_item else ""
            old_text = c_item.text() if c_item else ""
            
            # 计算新时间戳
            new_time_str = old_time_str
            if old_time_str:
                ms = parse_time_tag(old_time_str)
                if ms >= 0:
                    new_ms = max(0, ms + delta_ms)
                    new_time_str = f"[{format_ms(new_ms)}]"
            
            # 计算新文本（包含逐字内嵌时间戳）
            new_text = self.shift_timestamps_in_string(old_text, delta_ms)
            
            old_data.append((r, old_time_str, old_text))
            new_data.append((r, new_time_str, new_text))

        def _apply(data_list):
            for r, t_str, c_str in data_list:
                self.table.setItem(r, 0, QTableWidgetItem(t_str))
                self.table.setItem(r, 1, QTableWidgetItem(c_str))
            self.cache_timestamps()
            self.refresh_playback_view()

        cmd = BatchLineShiftCommand(
            old_data=old_data,
            new_data=new_data,
            apply_callback=_apply,
            description=f"时间轴偏移 {delta_ms:+d}ms"
        )
        self.undo_stack.push(cmd)

    def refresh_playback_view(self):
        pos = self.player.position()
        self.highlight_current_line(pos)
        self.update_line_preview(pos)

    def stamp_current_time(self):
        current_rows = self.table.selectedItems()
        if not current_rows: return
        
        row = current_rows[0].row()
        current_pos_ms = self.player.position()
        new_time_str = f"[{format_ms(current_pos_ms)}]"
        
        old_time_item = self.table.item(row, 0)
        old_time_str = old_time_item.text() if old_time_item else ""
        old_start_ms = parse_time_tag(old_time_str)
        
        lyric_item = self.table.item(row, 1)
        original_text = lyric_item.text() if lyric_item else ""
        
        delta_ms = current_pos_ms - old_start_ms if old_start_ms >= 0 else 0

        # 修复首字异常空隙
        extra_fix_ms = 0
        first_inner_match = re.search(r'\[(\d{2}:\d{2}\.\d{2,3})\]', original_text)
        if first_inner_match and old_start_ms >= 0:
            old_first_inner_ms = parse_time_tag(f"[{first_inner_match.group(1)}]")
            original_gap = old_first_inner_ms - old_start_ms
            if original_gap > 1200:
                target_gap = 300
                extra_fix_ms = -(original_gap - target_gap)

        total_shift_ms = delta_ms + extra_fix_ms
        shifted_text = self.shift_timestamps_in_string(original_text, total_shift_ms)
        
        affected_trans = []
        next_row = row + 1
        while next_row < self.table.rowCount():
            next_time_item = self.table.item(next_row, 0)
            if not next_time_item: break
            if next_time_item.text() == old_time_str and next_row in self.translation_rows:
                affected_trans.append((next_row, old_time_str, new_time_str))
                next_row += 1
            else:
                break
        
        cmd = LineStampCommand(
            dialog=self,
            row=row,
            old_time_str=old_time_str,
            old_text=original_text,
            new_time_str=new_time_str,
            new_text=shifted_text,
            affected_translations=affected_trans,
            description="写入行时间戳"
        )
        self.undo_stack.push(cmd)
        
        if row < self.table.rowCount() - 1:
            self.table.selectRow(row + 1)
            self.table.scrollToItem(self.table.item(row + 1, 0))

    def shift_timestamps_in_string(self, text, delta_ms):
        def replace_func(match):
            full_tag = match.group(0)
            ms = parse_time_tag(full_tag)
            if ms < 0: return full_tag
            new_ms = max(0, ms + delta_ms)
            return f"[{format_ms(new_ms)}]"
        
        pattern = re.compile(r'\[\d{2}:\d{2}\.\d{2,3}\]')
        return pattern.sub(replace_func, text)

    def cache_timestamps(self):
        self.cached_timestamps = []
        for row in range(self.table.rowCount()):
            time_item = self.table.item(row, 0)
            if time_item and time_item.text():
                ms = parse_time_tag(time_item.text())
                self.cached_timestamps.append((row, ms))
            else:
                self.cached_timestamps.append((row, -1))

    def highlight_current_line(self, current_pos_ms):
        target_row = -1
        for i, (row, start_ms) in enumerate(self.cached_timestamps):
            if start_ms < 0 or row in self.translation_rows:
                continue
            
            end_ms = None
            for j in range(i + 1, len(self.cached_timestamps)):
                if self.cached_timestamps[j][0] not in self.translation_rows and self.cached_timestamps[j][1] > 0:
                    end_ms = self.cached_timestamps[j][1]
                    break
            
            if end_ms is None:
                if current_pos_ms >= start_ms:
                    target_row = row
                    break
            else:
                if start_ms <= current_pos_ms < end_ms:
                    target_row = row
                    break
        
        if target_row != self.last_highlight_row:
            if self.last_highlight_row >= 0:
                self.set_row_highlight(self.last_highlight_row, False)
                self.highlight_translation_rows(self.last_highlight_row, False)
            
            if target_row >= 0:
                self.set_row_highlight(target_row, True)
                self.highlight_translation_rows(target_row, True)
                self.table.scrollToItem(self.table.item(target_row, 0))
                
                # 同步更新波形高亮选区
                h_start = self.cached_timestamps[target_row][1]
                h_end = self.player.duration()
                for j in range(target_row + 1, len(self.cached_timestamps)):
                    if self.cached_timestamps[j][0] not in self.translation_rows and self.cached_timestamps[j][1] > 0:
                        h_end = self.cached_timestamps[j][1]
                        break
                self.waveform.set_highlight_region(h_start, h_end)
            else:
                self.waveform.set_highlight_region(-1, -1)
            
            self.last_highlight_row = target_row

    def highlight_translation_rows(self, original_row, is_playing):
        if original_row < 0: return
        time_item = self.table.item(original_row, 0)
        if not time_item: return
        
        original_timestamp = time_item.text()
        for row in range(original_row + 1, self.table.rowCount()):
            if row not in self.translation_rows: break
            trans_time_item = self.table.item(row, 0)
            if trans_time_item and trans_time_item.text() == original_timestamp:
                self.set_row_highlight(row, is_playing)

    def set_row_highlight(self, row, is_playing):
        is_dark = theme_manager.is_dark()
        if is_playing:
            bg_color = QColor("#1b3859" if is_dark else "#e6f7ff")
            text_color = QColor("#79bbff" if is_dark else "#1890ff")
        else:
            bg_color = QColor(theme_manager.get_color("bg_input", "#1d1f24"))
            text_color = QColor(theme_manager.get_color("text_primary", "#ffffff"))
        
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(bg_color)
                item.setForeground(text_color)

    def adjust_timestamp(self, delta_ms):
        current_rows = self.table.selectedItems()
        if not current_rows: return
        
        row = current_rows[0].row()
        time_item = self.table.item(row, 0)
        if not time_item or not time_item.text(): return
        
        old_time_str = time_item.text()
        old_time_ms = parse_time_tag(old_time_str)
        if old_time_ms < 0: return
        
        new_time_ms = max(0, old_time_ms + delta_ms)
        new_time_str = f"[{format_ms(new_time_ms)}]"
        
        lyric_item = self.table.item(row, 1)
        original_text = lyric_item.text() if lyric_item else ""
        shifted_text = self.shift_timestamps_in_string(original_text, delta_ms)
        
        cmd = LineStampCommand(
            dialog=self,
            row=row,
            old_time_str=old_time_str,
            old_text=original_text,
            new_time_str=new_time_str,
            new_text=shifted_text,
            affected_translations=[],
            description=f"微调单行时间 {delta_ms:+d}ms"
        )
        self.undo_stack.push(cmd)

    def update_line_preview(self, current_pos_ms):
        current_row = -1
        current_line_start_ms = 0
        for i, (row, start_ms) in enumerate(self.cached_timestamps):
            if start_ms < 0 or row in self.translation_rows:
                continue

            end_ms = None
            for j in range(i + 1, len(self.cached_timestamps)):
                if self.cached_timestamps[j][0] not in self.translation_rows and self.cached_timestamps[j][1] > 0:
                    end_ms = self.cached_timestamps[j][1]
                    break

            if end_ms is None:
                if current_pos_ms >= start_ms:
                    current_row = row
                    current_line_start_ms = start_ms
                    break
            else:
                if start_ms <= current_pos_ms < end_ms:
                    current_row = row
                    current_line_start_ms = start_ms
                    break
        
        if current_row < 0:
            self.lbl_line_preview.setText("<span style='color:#8c92a4;'>等待播放...</span>")
            return
        
        text_item = self.table.item(current_row, 1)
        if not text_item: return
        line_text = text_item.text()
        
        translations = []
        time_item = self.table.item(current_row, 0)
        if time_item:
            original_timestamp = time_item.text()
            for row in range(current_row + 1, self.table.rowCount()):
                if row not in self.translation_rows: break
                trans_time_item = self.table.item(row, 0)
                trans_text_item = self.table.item(row, 1)
                if trans_time_item and trans_text_item and trans_time_item.text() == original_timestamp:
                    translations.append(trans_text_item.text())
        
        if '[' in line_text and ']' in line_text and re.search(r'\[\d{2}:\d{2}\.\d{2,3}\]', line_text):
            html = self.render_karaoke_html(line_text, current_pos_ms, current_line_start_ms)
        else:
            active_color = theme_manager.get_color("highlight_karaoke_played", "#67c23a")
            html = f"<span style='color:{active_color};'>{line_text}</span>"
        
        if translations:
            trans_html = f"<br><span style='color:#8c92a4; font-size:15px; font-weight:normal;'>{' / '.join(translations)}</span>"
            html += trans_html
        
        self.lbl_line_preview.setText(html)

    def render_karaoke_html(self, line_text, current_pos_ms, line_start_ms=0):
        # 行首若带时间标签则作为首字的起始时间；否则用行时间戳列的起点，
        # 避免首字因初始 current_time=0 而恒显示为「已唱」
        lead = re.match(r'^\[\d{2}:\d{2}\.\d{2,3}\]', line_text)
        if lead:
            current_time = parse_time_tag(lead.group(0))
            clean_text = line_text[lead.end():]
        else:
            current_time = line_start_ms
            clean_text = line_text
        parts = re.split(r'(\[\d{2}:\d{2}\.\d{2,3}\])', clean_text)

        html = ""
        played_color = theme_manager.get_color("highlight_karaoke_played", "#67c23a")
        unplayed_color = theme_manager.get_color("highlight_karaoke_unplayed", "#8c92a4")

        for part in parts:
            if not part: continue
            if re.match(r'^\[\d{2}:\d{2}\.\d{2,3}\]$', part):
                current_time = parse_time_tag(part)
            else:
                for char in part:
                    color = played_color if current_pos_ms >= current_time else unplayed_color
                    html += f"<span style='color:{color};'>{char}</span>"
        
        return html if html else "<span style='color:#8c92a4;'>无歌词</span>"

    def save_lrc(self):
        lines = []
        for r in range(self.table.rowCount()):
            t = self.table.item(r, 0).text() if self.table.item(r, 0) else ""
            c = self.table.item(r, 1).text() if self.table.item(r, 1) else ""
            lines.append(f"{t}{c}")
        self.result_lrc = "\n".join(lines)
        self.accept()
    
    def stop_and_release(self):
        # 停止刷新定时器，避免对话框关闭后 timer 持续空转
        self.timer.stop()
        if self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.player.stop()

    def accept(self):
        self.stop_and_release()
        super().accept()

    def reject(self):
        self.stop_and_release()
        super().reject()

    def closeEvent(self, event):
        self.stop_and_release()
        super().closeEvent(event)
