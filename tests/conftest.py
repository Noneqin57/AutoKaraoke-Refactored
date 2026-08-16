# -*- coding: utf-8 -*-
"""pytest 全局配置：阻止测试期间写入日志文件。"""
import logging


def pytest_configure(config):
    for name in ("Worker", "WorkerDaemon", "ModelCache", "AutoKaraoke"):
        logger = logging.getLogger(name)
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
