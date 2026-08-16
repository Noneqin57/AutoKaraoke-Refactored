# -*- coding: utf-8 -*-
"""utils.logger 降级健壮性测试。"""
import io
import logging

import utils.logger_v2 as log_mod


def test_setup_logger_exposed_directly():
    assert callable(log_mod.setup_logger)
    assert callable(log_mod.get_logger)


def test_robust_logger_falls_back_to_console_when_dir_unwritable(monkeypatch):
    name = "TestFallbackLogger"
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    monkeypatch.setattr(log_mod.sys, "stderr", io.StringIO())

    def raise_oserror(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(log_mod, "_ensure_log_dir", raise_oserror)

    result = log_mod.setup_logger(name)

    assert len(result.handlers) == 1
    assert isinstance(result.handlers[0], logging.StreamHandler)
    assert "failed to create log file handler" in log_mod.sys.stderr.getvalue()
