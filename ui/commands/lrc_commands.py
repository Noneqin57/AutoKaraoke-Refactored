# -*- coding: utf-8 -*-
"""
歌词打轴撤销/重做指令封装 (Undo/Redo Commands)
"""
from typing import Callable, List, Dict, Any, Tuple
from PyQt6.QtGui import QUndoCommand

class WordTimestampCommand(QUndoCommand):
    """单个字的时间戳修改指令"""
    def __init__(
        self,
        token_index: int,
        old_time_ms: int,
        new_time_ms: int,
        update_callback: Callable[[int, int], None],
        description: str = "修改时间戳"
    ):
        super().__init__(description)
        self.token_index = token_index
        self.old_time_ms = old_time_ms
        self.new_time_ms = new_time_ms
        self.update_callback = update_callback

    def redo(self):
        self.update_callback(self.token_index, self.new_time_ms)

    def undo(self):
        self.update_callback(self.token_index, self.old_time_ms)


class BatchTimeShiftCommand(QUndoCommand):
    """字级批量时间平移指令"""
    def __init__(
        self,
        tokens_backup: List[Dict[str, Any]],
        delta_ms: int,
        apply_callback: Callable[[int], None],
        description: str = "批量时间平移"
    ):
        super().__init__(description)
        self.tokens_backup = tokens_backup
        self.delta_ms = delta_ms
        self.apply_callback = apply_callback

    def redo(self):
        self.apply_callback(self.delta_ms)

    def undo(self):
        self.apply_callback(-self.delta_ms)


class BatchLineShiftCommand(QUndoCommand):
    """整行或多行时间戳批量平移指令"""
    def __init__(
        self,
        old_data: List[Tuple[int, str, str]], # [(row, old_time_str, old_text)]
        new_data: List[Tuple[int, str, str]], # [(row, new_time_str, new_text)]
        apply_callback: Callable[[List[Tuple[int, str, str]]], None],
        description: str = "批量时间偏移"
    ):
        super().__init__(description)
        self.old_data = old_data
        self.new_data = new_data
        self.apply_callback = apply_callback

    def redo(self):
        self.apply_callback(self.new_data)

    def undo(self):
        self.apply_callback(self.old_data)
