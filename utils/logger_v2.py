# -*- coding: utf-8 -*-
"""日志管理模块（清理版）。

文件日志写入失败时自动降级为仅控制台日志，绝不让日志系统导致应用崩溃。
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def _get_default_log_dir() -> str:
    """选择日志目录：优先用户数据目录，避免安装目录/当前目录不可写。

    优先级：
    1. 环境变量 AUTOKARAOKE_LOG_DIR
    2. Windows: %LOCALAPPDATA%\\AutoKaraoke\\logs
    3. 其他: ~/.autokaraoke/logs
    """
    env_dir = os.environ.get("AUTOKARAOKE_LOG_DIR")
    if env_dir:
        return env_dir

    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "AutoKaraoke", "logs")

    return os.path.join(os.path.expanduser("~"), ".autokaraoke", "logs")


def _ensure_log_dir(log_dir: str) -> str:
    """确保日志目录存在；失败时回退到 ./logs。"""
    for candidate in (log_dir, os.path.join(os.getcwd(), "logs")):
        try:
            os.makedirs(candidate, exist_ok=True)
            return candidate
        except OSError:
            continue
    os.makedirs(log_dir, exist_ok=True)
    return log_dir


def setup_logger(name="AutoKaraoke", level=logging.INFO):
    """配置并返回日志记录器；文件日志不可用时降级为仅控制台。"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console_handler)

    try:
        log_dir = _ensure_log_dir(_get_default_log_dir())
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, f"{name}.log"),
            encoding="utf-8",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - [%(levelname)s] - %(funcName)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
        logger.addHandler(file_handler)
    except OSError as exc:
        sys.stderr.write(f"Warning: failed to create log file handler: {exc}\n")

    return logger


def get_logger(name="AutoKaraoke"):
    """获取已存在的日志记录器。"""
    return logging.getLogger(name)
