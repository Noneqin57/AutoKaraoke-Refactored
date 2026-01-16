# -*- coding: utf-8 -*-
import os
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QSlider, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStyle, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from utils.time_utils import format_ms, parse_time_tag
from ui.word_editor import WordLevelEditor

class LrcEditorDialog(QDialog):
    def __init__(self, audio_path, lrc_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle("歌词精细校准 - AutoKaraoke Editor")
        self.resize(1000, 750) 
        self.audio_path = audio_path
        self.lrc_content = lrc_content
        self.result_lrc = None
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        self.setup_ui()
        self.load_lrc_data()
        self.load_audio()
        
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_progress)
        self.timer.start()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        help_lbl = QLabel(
            "💡 <b>操作：</b>单击暂停选中 | 双击跳转 | Enter键同步当前行 | 空格播放/暂停"
        )
        help_lbl.setStyleSheet("background: #e6f7ff; padding: 10px; border: 1px solid #91d5ff;")
        layout.addWidget(help_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["时间戳", "歌词内容"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        
        self.table.cellDoubleClicked.connect(self.seek_to_row)
        self.table.cellPressed.connect(self.pause_on_click)
        layout.addWidget(self.table)
        
        ctrl_box = QHBoxLayout()
        self.btn_play = QPushButton()
        self.update_play_icon()
        self.btn_play.clicked.connect(self.toggle_play)
        
        self.lbl_curr = QLabel("00:00.000")
        self.lbl_curr.setMinimumWidth(80)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(self.set_position)
        self.slider.sliderPressed.connect(self.pause_for_seek)
        self.slider.sliderReleased.connect(self.resume_after_seek)
        self.lbl_total = QLabel("00:00.000")
        
        ctrl_box.addWidget(self.btn_play)
        ctrl_box.addWidget(self.lbl_curr)
        ctrl_box.addWidget(self.slider)
        ctrl_box.addWidget(self.lbl_total)
        layout.addLayout(ctrl_box)
        
        btn_box = QHBoxLayout()
        btn_stamp = QPushButton("⏱️ 智能同步写入 (Enter)")
        btn_stamp.setStyleSheet("background: #e6a23c; color: white; font-weight: bold;")
        btn_stamp.clicked.connect(self.stamp_current_time)
        
        btn_save = QPushButton("💾 保存并关闭")
        btn_save.setStyleSheet("background: #67c23a; color: white; font-weight: bold;")
        btn_save.clicked.connect(self.save_lrc) 
        
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject) 
        
        btn_box.addWidget(btn_stamp)
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        
        self.table.keyPressEvent = self.table_key_event

    def load_audio(self):
        if self.audio_path and os.path.exists(self.audio_path):
            self.player.setSource(QUrl.fromLocalFile(self.audio_path))
            self.player.mediaStatusChanged.connect(self.on_media_status)
    
    def on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            duration = self.player.duration()
            self.slider.setRange(0, duration)
            self.lbl_total.setText(format_ms(duration))

    def load_lrc_data(self):
        lines = self.lrc_content.splitlines()
        self.table.setRowCount(0)
        pattern = re.compile(r'^(\[\d{2}:\d{2}\.\d{2,3}\])(.*)')
        row = 0
        for line in lines:
            line = line.strip()
            if not line: continue
            match = pattern.match(line)
            if match:
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(match.group(1)))
                self.table.setItem(row, 1, QTableWidgetItem(match.group(2)))
                row += 1
            else:
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(""))
                self.table.setItem(row, 1, QTableWidgetItem(line))
                row += 1

    def table_key_event(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.stamp_current_time()
        else:
            QTableWidget.keyPressEvent(self.table, event)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        self.update_play_icon()

    def update_play_icon(self):
        style = self.style()
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPause)
        else:
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.btn_play.setIcon(icon)

    def update_progress(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            pos = self.player.position()
            self.slider.setValue(pos)
            self.lbl_curr.setText(format_ms(pos))

    def set_position(self, pos):
        self.player.setPosition(pos)
        self.lbl_curr.setText(format_ms(pos))

    def pause_for_seek(self):
        self.was_playing = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.player.pause()

    def resume_after_seek(self):
        if hasattr(self, 'was_playing') and self.was_playing:
            self.player.play()
            self.update_play_icon()
    
    def seek_to_row(self, row, col):
        """
        双击进入逐字编辑模式
        """
        # 获取当前行的时间和文本
        time_item = self.table.item(row, 0)
        text_item = self.table.item(row, 1)
        
        if not time_item or not text_item: return
        
        time_str = time_item.text()
        text_content = text_item.text()
        start_ms = parse_time_tag(time_str)
        
        # === 关键：计算本句的结束时间 (下一句的开始时间) ===
        end_ms = self.player.duration() # 默认为歌曲总时长
        next_row = row + 1
        
        # 寻找下一个有效的时间戳作为结束时间
        while next_row < self.table.rowCount():
            next_time_item = self.table.item(next_row, 0)
            if next_time_item:
                next_start_ms = parse_time_tag(next_time_item.text())
                if next_start_ms > start_ms: # 确保下一句时间确实比这句晚
                    end_ms = next_start_ms
                    break
            next_row += 1
        # =================================================
        
        # 暂停主播放器
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.update_play_icon()
            
        # 打开逐字编辑器，传入结束时间
        editor = WordLevelEditor(self.audio_path, text_content, start_ms, end_ms, self)
        
        if editor.exec():
            # 保存逻辑
            if editor.result_start_time:
                self.table.setItem(row, 0, QTableWidgetItem(editor.result_start_time))
            if editor.result_lrc_content:
                self.table.setItem(row, 1, QTableWidgetItem(editor.result_lrc_content))
    
    def pause_on_click(self, row, col):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.update_play_icon()

    def stamp_current_time(self):
        current_rows = self.table.selectedItems()
        if not current_rows: return
        
        row = current_rows[0].row()
        current_pos_ms = self.player.position()
        new_time_str = f"[{format_ms(current_pos_ms)}]"
        
        old_time_item = self.table.item(row, 0)
        old_time_str = old_time_item.text()
        old_start_ms = parse_time_tag(old_time_str)
        
        lyric_item = self.table.item(row, 1)
        original_text = lyric_item.text()
        
        delta_ms = 0
        if old_start_ms >= 0:
            delta_ms = current_pos_ms - old_start_ms

        # 修复首字异常空隙
        extra_fix_ms = 0
        first_inner_match = re.search(r'\[(\d{2}:\d{2}\.\d{2,3})\]', original_text)
        if first_inner_match and old_start_ms >= 0:
            old_first_inner_ms = parse_time_tag(f"[{first_inner_match.group(1)}]")
            original_gap = old_first_inner_ms - old_start_ms
            if original_gap > 1200:
                target_gap = 300 
                extra_fix_ms = -(original_gap - target_gap)

        self.table.setItem(row, 0, QTableWidgetItem(new_time_str))
        
        total_shift_ms = delta_ms + extra_fix_ms
        shifted_text = self.shift_timestamps_in_string(original_text, total_shift_ms)
        self.table.setItem(row, 1, QTableWidgetItem(shifted_text))
        
        # 同步更新后续翻译行
        next_row = row + 1
        while next_row < self.table.rowCount():
            next_time_item = self.table.item(next_row, 0)
            if not next_time_item: break
            if next_time_item.text() == old_time_str:
                self.table.setItem(next_row, 0, QTableWidgetItem(new_time_str))
                next_row += 1
            else:
                break
        
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

    def save_lrc(self):
        lines = []
        for r in range(self.table.rowCount()):
            t = self.table.item(r, 0).text()
            c = self.table.item(r, 1).text()
            lines.append(f"{t}{c}")
        self.result_lrc = "\n".join(lines)
        self.accept()
    
    def stop_and_release(self):
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
        event.accept()
