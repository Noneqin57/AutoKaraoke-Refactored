# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""daemon worker 启动跳板（torch-free）。

UI 主进程仅通过本模块引用 worker 入口，避免在主进程 import
torch / stable_whisper（它们只在推理子进程内需要）。Windows spawn
模式下 Process(target=...) 只按「模块路径 + 函数名」序列化引用，
torch 的实际加载发生在子进程执行函数体时。
"""


def daemon_worker_entry(task_queue, result_queue, progress_queue, stop_event):
    """在子进程内延迟导入并启动真正的 daemon worker 主循环。"""
    from core.whisper_worker import daemon_worker

    daemon_worker(task_queue, result_queue, progress_queue, stop_event)
