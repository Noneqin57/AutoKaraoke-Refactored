# -*- coding: utf-8 -*-
import os
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
                             QSlider, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStyle, QMessageBox)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtGui import QColor

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
        
        # 新增：时间戳缓存和高亮追踪
        self.cached_timestamps = []  # 缓存解析后的时间戳 [(row, time_ms), ...]
        self.last_highlight_row = -1  # 记录上次高亮的行
        self.translation_rows = set()  # 记录翻译行的索引
        
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
            "<b>操作：</b>单击暂停选中 | 双击跳转 | Enter键同步当前行 | 空格播放/暂停"
        )
        help_lbl.setStyleSheet("background: #e6f7ff; padding: 10px; border: 1px solid #91d5ff;")
        layout.addWidget(help_lbl)
        
        # 新增：顶部卡拉OK预览区
        preview_container = QVBoxLayout()
        preview_container.setSpacing(5)
        
        lbl_hint = QLabel("当前播放")
        lbl_hint.setStyleSheet("color: #909399; font-size: 12px;")
        preview_container.addWidget(lbl_hint)
        
        self.lbl_line_preview = QLabel()
        self.lbl_line_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_line_preview.setStyleSheet("""
            background-color: #303133;
            border-radius: 8px;
            padding: 15px;
            font-family: 'Microsoft YaHei';
            font-size: 24px;
            font-weight: bold;
            min-height: 60px;
            color: #909399;
        """)
        self.lbl_line_preview.setText("等待播放...")
        preview_container.addWidget(self.lbl_line_preview)
        
        layout.addLayout(preview_container)

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
        btn_stamp = QPushButton("智能同步写入 (Enter)")
        btn_stamp.setStyleSheet("background: #e6a23c; color: white; font-weight: bold;")
        btn_stamp.clicked.connect(self.stamp_current_time)
        
        btn_save = QPushButton("保存并关闭")
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
                
                # 检测翻译行（时间戳相同且不是第一次出现）
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
        
        # 新增：加载完成后缓存时间戳
        self.cache_timestamps()

    def table_key_event(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.stamp_current_time()
        elif event.key() == Qt.Key.Key_Left and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Ctrl+Left: 时间戳 -100ms
            self.adjust_timestamp(-100)
        elif event.key() == Qt.Key.Key_Right and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Ctrl+Right: 时间戳 +100ms
            self.adjust_timestamp(100)
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
        pos = self.player.position()
        self.slider.setValue(pos)
        self.lbl_curr.setText(format_ms(pos))
        
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            # 新增：高亮当前播放的行
            self.highlight_current_line(pos)
            # 新增：更新预览区
            self.update_line_preview(pos)
        else:
            # 暂停时也更新预览（静态显示）
            self.update_line_preview(pos)

    def set_position(self, pos):
        self.player.setPosition(pos)
        self.lbl_curr.setText(format_ms(pos))
        
        # 新增：拖拽时也更新预览和高亮
        self.update_line_preview(pos)
        self.highlight_current_line(pos)

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
        
        # 新增：修改时间戳后重新缓存
        self.cache_timestamps()
        
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

    def cache_timestamps(self):
        """缓存所有行的时间戳（毫秒），优化查找性能"""
        self.cached_timestamps = []
        for row in range(self.table.rowCount()):
            time_item = self.table.item(row, 0)
            if time_item and time_item.text():
                ms = parse_time_tag(time_item.text())
                self.cached_timestamps.append((row, ms))
            else:
                self.cached_timestamps.append((row, -1))
    
    def highlight_current_line(self, current_pos_ms):
        """根据播放位置高亮当前行"""
        target_row = -1
        
        # 查找最匹配的行（优先匹配原文行，跳过翻译行）
        for i, (row, start_ms) in enumerate(self.cached_timestamps):
            if start_ms < 0:
                continue  # 跳过无效时间戳
            
            # 跳过翻译行，只高亮原文
            if row in self.translation_rows:
                continue
            
            # 获取下一行的开始时间作为当前行的结束时间
            end_ms = None
            for j in range(i + 1, len(self.cached_timestamps)):
                # 跳过翻译行，寻找下一个原文行的时间戳
                if self.cached_timestamps[j][0] not in self.translation_rows and self.cached_timestamps[j][1] > 0:
                    end_ms = self.cached_timestamps[j][1]
                    break
            
            if end_ms is None:
                # 最后一行，持续到音频结束
                if current_pos_ms >= start_ms:
                    target_row = row
                    break
            else:
                # 判断当前位置是否在此行的时间范围内
                if start_ms <= current_pos_ms < end_ms:
                    target_row = row
                    break
        
        # 更新高亮
        if target_row != self.last_highlight_row:
            # 清除旧高亮
            if self.last_highlight_row >= 0:
                self.clear_row_highlight(self.last_highlight_row)
                # 同时清除翻译行的高亮
                self.clear_translation_highlight(self.last_highlight_row)
            
            # 应用新高亮
            if target_row >= 0:
                self.set_row_highlight(target_row, True)
                # 同时高亮翻译行
                self.highlight_translation_rows(target_row, True)
                # 自动滚动到当前行
                self.table.scrollToItem(self.table.item(target_row, 0))
            
            self.last_highlight_row = target_row
    
    def highlight_translation_rows(self, original_row, is_playing):
        """高亮原文行对应的翻译行"""
        if original_row < 0:
            return
        
        # 获取原文行的时间戳
        time_item = self.table.item(original_row, 0)
        if not time_item:
            return
        
        original_timestamp = time_item.text()
        
        # 查找所有相同时间戳的翻译行
        for row in range(original_row + 1, self.table.rowCount()):
            if row not in self.translation_rows:
                break  # 遇到非翻译行，停止查找
            
            trans_time_item = self.table.item(row, 0)
            if trans_time_item and trans_time_item.text() == original_timestamp:
                self.set_row_highlight(row, is_playing)
    
    def clear_translation_highlight(self, original_row):
        """清除原文行对应的翻译行高亮"""
        self.highlight_translation_rows(original_row, False)
    
    def set_row_highlight(self, row, is_playing):
        """设置行高亮样式"""
        if is_playing:
            bg_color = QColor("#e6f7ff")  # 淡蓝色背景
            text_color = QColor("#1890ff")  # 深蓝色文字
        else:
            bg_color = QColor(Qt.GlobalColor.white)
            text_color = QColor(Qt.GlobalColor.black)
        
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(bg_color)
                item.setForeground(text_color)
    
    def clear_row_highlight(self, row):
        """清除行高亮"""
        self.set_row_highlight(row, False)
    
    def adjust_timestamp(self, delta_ms):
        """调整当前选中行的时间戳"""
        current_rows = self.table.selectedItems()
        if not current_rows: return
        
        row = current_rows[0].row()
        time_item = self.table.item(row, 0)
        if not time_item or not time_item.text(): return
        
        old_time_ms = parse_time_tag(time_item.text())
        if old_time_ms < 0: return
        
        new_time_ms = max(0, old_time_ms + delta_ms)
        new_time_str = f"[{format_ms(new_time_ms)}]"
        
        self.table.setItem(row, 0, QTableWidgetItem(new_time_str))
        
        # 同时调整字级时间戳
        lyric_item = self.table.item(row, 1)
        if lyric_item:
            original_text = lyric_item.text()
            shifted_text = self.shift_timestamps_in_string(original_text, delta_ms)
            self.table.setItem(row, 1, QTableWidgetItem(shifted_text))
        
        # 重新缓存
        self.cache_timestamps()
    
    def update_line_preview(self, current_pos_ms):
        """更新顶部预览区"""
        # 找到当前行（优先原文行）
        current_row = -1
        for i, (row, start_ms) in enumerate(self.cached_timestamps):
            if start_ms < 0:
                continue
            
            # 跳过翻译行
            if row in self.translation_rows:
                continue
            
            end_ms = None
            for j in range(i + 1, len(self.cached_timestamps)):
                if self.cached_timestamps[j][0] not in self.translation_rows and self.cached_timestamps[j][1] > 0:
                    end_ms = self.cached_timestamps[j][1]
                    break
            
            if end_ms is None:
                if current_pos_ms >= start_ms:
                    current_row = row
                    break
            else:
                if start_ms <= current_pos_ms < end_ms:
                    current_row = row
                    break
        
        if current_row < 0:
            self.lbl_line_preview.setText("<span style='color:#909399;'>等待播放...</span>")
            return
        
        # 获取原文
        text_item = self.table.item(current_row, 1)
        if not text_item:
            return
        
        line_text = text_item.text()
        
        # 查找翻译行
        translations = []
        time_item = self.table.item(current_row, 0)
        if time_item:
            original_timestamp = time_item.text()
            for row in range(current_row + 1, self.table.rowCount()):
                if row not in self.translation_rows:
                    break
                trans_time_item = self.table.item(row, 0)
                trans_text_item = self.table.item(row, 1)
                if trans_time_item and trans_text_item and trans_time_item.text() == original_timestamp:
                    translations.append(trans_text_item.text())
        
        # 渲染预览
        if '[' in line_text and ']' in line_text and re.search(r'\[\d{2}:\d{2}\.\d{2,3}\]', line_text):
            # 有字级时间戳，渲染卡拉OK效果
            html = self.render_karaoke_html(line_text, current_pos_ms)
        else:
            # 整行高亮
            html = f"<span style='color:#67c23a;'>{line_text}</span>"
        
        # 添加翻译（灰色小字）
        if translations:
            trans_html = "<br><span style='color:#909399; font-size:18px;'>" + " / ".join(translations) + "</span>"
            html += trans_html
        
        self.lbl_line_preview.setText(html)
    
    def render_karaoke_html(self, line_text, current_pos_ms):
        """渲染卡拉OK效果的HTML"""
        # 移除开头的时间戳
        clean_text = re.sub(r'^\[\d{2}:\d{2}\.\d{2,3}\]', '', line_text)
        
        # 分割文本和时间戳
        parts = re.split(r'(\[\d{2}:\d{2}\.\d{2,3}\])', clean_text)
        
        html = ""
        current_time = 0
        
        for part in parts:
            if not part:
                continue
            
            if re.match(r'^\[\d{2}:\d{2}\.\d{2,3}\]$', part):
                # 这是时间戳
                current_time = parse_time_tag(part)
            else:
                # 这是文本
                for char in part:
                    # 判断字符状态
                    if current_pos_ms >= current_time:
                        # 已播放或正在播放
                        color = "#67c23a"  # 绿色（已唱）
                    else:
                        # 未播放
                        color = "#909399"  # 灰色
                    
                    html += f"<span style='color:{color};'>{char}</span>"
        
        return html if html else "<span style='color:#909399;'>无歌词</span>"
    
    def closeEvent(self, event):
        self.stop_and_release()
        event.accept()
