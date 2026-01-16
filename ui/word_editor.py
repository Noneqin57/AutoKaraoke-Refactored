# -*- coding: utf-8 -*-
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
                             QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView)
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from utils.time_utils import format_ms, parse_time_tag

class WordLevelEditor(QDialog):
    """
    字级精细校对窗口 (支持区间播放与自动暂停)
    """
    def __init__(self, audio_path, line_text, start_time_ms, end_time_ms, parent=None):
        super().__init__(parent)
        self.setWindowTitle("逐字精细打轴 (Enter: 打点 | Space: 播放 | ←/→: 移动)")
        self.resize(1000, 450)
        self.audio_path = audio_path
        self.line_text = line_text
        self.base_time = start_time_ms
        self.end_time_ms = end_time_ms  # 记录本句结束时间
        self.result_text = None
        self.result_lrc_content = None
        self.result_start_time = None
        
        self.tokens = self.parse_line(line_text, start_time_ms)
        self.last_active_idx = -1
        
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self.on_media_status_changed)
        self.player.setSource(QUrl.fromLocalFile(audio_path))
        
        # 初始定位到该句开始前 1秒 (稍微留点预卷时间)
        self.start_pos = max(0, self.tokens[0]['time'] - 1000 if self.tokens else start_time_ms - 1000)
        
        self.setup_ui()
        
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.sync_highlight)
        self.timer.start()

    def on_media_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia or status == QMediaPlayer.MediaStatus.BufferedMedia:
            self.player.setPosition(self.start_pos)

    def replay_line(self):
        self.player.setPosition(self.start_pos)
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.player.play()
            self.update_play_icon()

    def parse_line(self, text, default_start):
        clean_text = re.sub(r'^\[\d{2}:\d{2}\.\d{2,3}\]', '', text)
        parts = re.split(r'(\[\d{2}:\d{2}\.\d{2,3}\])', clean_text)
        tokens = []
        current_time = default_start
        for part in parts:
            if not part: continue
            if re.match(r'^\[\d{2}:\d{2}\.\d{2,3}\]$', part):
                current_time = parse_time_tag(part)
            else:
                chars = list(part)
                for char in chars:
                    tokens.append({'char': char, 'time': current_time, 'edited': False})
        return tokens

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # === 顶部：卡拉OK预览区 ===
        preview_container = QVBoxLayout()
        preview_container.setSpacing(5)
        
        lbl_hint = QLabel("🎶 实时预览 (Karaoke Preview)")
        lbl_hint.setStyleSheet("color: #909399; font-size: 12px;")
        preview_container.addWidget(lbl_hint)
        
        self.lbl_preview = QLabel()
        self.lbl_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview.setStyleSheet("""
            background-color: #303133; 
            border-radius: 8px; 
            padding: 15px;
            font-family: 'Microsoft YaHei';
            font-size: 28px;
            font-weight: bold;
        """)
        self.lbl_preview.setTextFormat(Qt.TextFormat.RichText)
        self.update_preview_display(0) # Init
        preview_container.addWidget(self.lbl_preview)
        
        layout.addLayout(preview_container)
        
        # 顶部信息栏
        info_lay = QHBoxLayout()
        # 显示当前校对的区间
        range_str = f"当前区间: {format_ms(self.base_time)} -> {format_ms(self.end_time_ms)}"
        info_lay.addWidget(QLabel(f"<b>{range_str}</b>"))
        layout.addLayout(info_lay)

        # 控制栏
        top_lay = QHBoxLayout()
        self.btn_play = QPushButton("播放/暂停 (Space)")
        self.btn_play.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_play.clicked.connect(self.toggle_play)
        
        self.lbl_speed = QLabel("倍速:")
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "2.0x"])
        self.combo_speed.setCurrentText("1.0x")
        self.combo_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_speed.currentTextChanged.connect(self.change_speed)
        
        self.lbl_time = QLabel("00:00.000")
        self.lbl_time.setStyleSheet("font-size: 16px; font-weight: bold; color: #409eff;")
        
        top_lay.addWidget(self.btn_play)
        top_lay.addWidget(self.lbl_speed)
        top_lay.addWidget(self.combo_speed)
        top_lay.addStretch()
        top_lay.addWidget(self.lbl_time)
        layout.addLayout(top_lay)
        
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus) # 确保对话框本身能接收按键
        
        # 表格控件
        self.table = QTableWidget()
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 防止表格抢夺按键焦点
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
            font = item_char.font()
            font.setPointSize(20)
            item_char.setFont(font)
            self.table.setItem(0, col, item_char)
            
            time_str = format_ms(token['time'])
            item_time = QTableWidgetItem(time_str)
            item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(1, col, item_time)
            
        self.table.resizeRowsToContents()
        for i in range(self.table.columnCount()):
            self.table.setColumnWidth(i, 60)
            
        self.table.cellClicked.connect(self.on_cell_clicked)
        layout.addWidget(self.table)
        
        # 提示信息
        tips_lay = QHBoxLayout()
        tips = QLabel("💡 快捷键: [Space]播放/暂停 | [Enter]打点 | [←/→]切换选中 | [↑/↓]微调时间(±50ms) | [Ctrl+Z]撤销")
        tips.setStyleSheet("color: #606266; font-style: italic;")
        tips_lay.addWidget(tips)
        layout.addLayout(tips_lay)
        
        # 底部按钮
        btn_box = QHBoxLayout()
        btn_replay = QPushButton("⏪ 重播本句")
        btn_replay.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_replay.clicked.connect(self.replay_line)
        
        btn_save = QPushButton("💾 确认并保存")
        btn_save.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_save.setStyleSheet("background: #67c23a; color: white; font-weight: bold; padding: 10px;")
        btn_save.clicked.connect(self.save_and_close)
        
        btn_cancel = QPushButton("取消")
        btn_cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addWidget(btn_replay)
        btn_box.addStretch()
        btn_box.addWidget(btn_save)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        
        if self.table.columnCount() > 0:
            self.table.selectColumn(0)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            # 如果当前已经播放到了结束时间后面，重新从头播放
            if self.player.position() >= self.end_time_ms:
                self.player.setPosition(self.start_pos)
            self.player.play()

    def change_speed(self, text):
        # "1.0x" -> 1.0
        try:
            val = float(text.replace('x', ''))
            self.player.setPlaybackRate(val)
        except: pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            self.toggle_play()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.stamp_current_char()
        elif event.key() == Qt.Key.Key_Left:
            curr = self.table.currentColumn()
            if curr > 0: self.table.selectColumn(curr - 1)
        elif event.key() == Qt.Key.Key_Right:
            curr = self.table.currentColumn()
            if curr < self.table.columnCount() - 1: self.table.selectColumn(curr + 1)
        elif event.key() == Qt.Key.Key_Up:
            self.adjust_timestamp(50)
        elif event.key() == Qt.Key.Key_Down:
            self.adjust_timestamp(-50)
        else:
            super().keyPressEvent(event)

    def adjust_timestamp(self, delta_ms):
        curr = self.table.currentColumn()
        if curr < 0: return
        
        old_time = self.tokens[curr]['time']
        new_time = max(0, old_time + delta_ms)
        self.tokens[curr]['time'] = new_time
        self.tokens[curr]['edited'] = True
        
        self.table.item(1, curr).setText(format_ms(new_time))
        self.update_cell_color(curr, is_active=True)
        
        # Update preview immediately
        self.update_preview_display(self.player.position())

    def update_preview_display(self, current_pos):
        # 构建富文本
        html = ""
        
        # 未播放颜色 #909399 (灰色), 已播放颜色 #409eff (蓝色), 当前字 #67c23a (绿色)
        for i, token in enumerate(self.tokens):
            t = token['time']
            char = token['char']
            
            # 判断状态
            # 下一个字的时间
            next_t = self.tokens[i+1]['time'] if i < len(self.tokens)-1 else self.end_time_ms
            
            if current_pos >= next_t:
                # 已经完全唱完的字
                color = "#409eff" # Blue
            elif current_pos >= t:
                # 正在唱的字
                color = "#67c23a" # Green (Active)
            else:
                # 还没唱到的字
                color = "#909399" # Gray
            
            html += f"<span style='color:{color};'>{char}</span>"
            
        self.lbl_preview.setText(html)

    def stamp_current_char(self):
        curr_col = self.table.currentColumn()
        if curr_col < 0: return
        
        current_pos = self.player.position()
        self.tokens[curr_col]['time'] = current_pos
        self.tokens[curr_col]['edited'] = True
        
        self.table.item(1, curr_col).setText(format_ms(current_pos))
        self.update_cell_color(curr_col, is_active=True)
        
        if curr_col < self.table.columnCount() - 1:
            self.table.selectColumn(curr_col + 1)

    def sync_highlight(self):
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return
            
        pos = self.player.position()
        self.lbl_time.setText(format_ms(pos))
        
        # 更新卡拉OK预览
        self.update_preview_display(pos)
        
        # === 核心逻辑：超过本句结束时间自动暂停 ===
        # 允许超过 200ms 的缓冲，避免听到下一句的头
        if pos >= self.end_time_ms + 200:
            self.player.pause()
            self.update_play_icon()
            return
        # ======================================
        
        active_idx = -1
        for i, token in enumerate(self.tokens):
            if pos >= token['time']:
                active_idx = i
            else:
                break
        
        if active_idx != self.last_active_idx:
            if self.last_active_idx >= 0 and self.last_active_idx < self.table.columnCount():
                self.update_cell_color(self.last_active_idx, is_active=False)
            
            if active_idx >= 0 and active_idx < self.table.columnCount():
                self.update_cell_color(active_idx, is_active=True)
                self.table.scrollToItem(self.table.item(0, active_idx))
            
            self.last_active_idx = active_idx

    def update_cell_color(self, col, is_active):
        token = self.tokens[col]
        item = self.table.item(0, col)
        if not item: return

        if is_active: bg = Qt.GlobalColor.cyan
        elif token['edited']: bg = Qt.GlobalColor.yellow
        else: bg = Qt.GlobalColor.white
            
        if item.background().color() != bg:
            item.setBackground(bg)

    def update_play_icon(self):
        # 简单的图标更新
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("暂停 (Space)")
        else:
            self.btn_play.setText("播放 (Space)")

    def on_cell_clicked(self, row, col):
        time_ms = self.tokens[col]['time']
        self.player.setPosition(time_ms)
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            self.player.play()

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
