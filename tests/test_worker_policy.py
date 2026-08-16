# -*- coding: utf-8 -*-
"""core.worker_policy 崩溃恢复策略测试。"""
from core.worker_policy import decide_worker_recovery


def test_idle_worker_restarts_quietly():
    assert decide_worker_recovery(False, False, False) == "restart"
    assert decide_worker_recovery(False, True, True) == "restart"


def test_running_task_with_pending_args_retries_once():
    assert decide_worker_recovery(True, True, False) == "retry"


def test_running_task_after_retry_reports_error():
    assert decide_worker_recovery(True, True, True) == "error"


def test_running_task_without_pending_args_reports_error():
    assert decide_worker_recovery(True, False, False) == "error"
