# -*- coding: utf-8 -*-
"""worker 崩溃恢复策略（纯函数，便于无 GUI 单元测试）。"""


def decide_worker_recovery(is_running_task: bool, has_pending_args: bool, retry_attempted: bool) -> str:
    """根据任务状态与重试状态，返回崩溃恢复动作。

    Returns:
        "retry"   —— 自动重启 worker 并重发当前任务
        "error"   —— 任务失败并通知用户
        "restart" —— 空闲状态，静默拉起新 worker
    """
    if not is_running_task:
        return "restart"
    if has_pending_args and not retry_attempted:
        return "retry"
    return "error"
