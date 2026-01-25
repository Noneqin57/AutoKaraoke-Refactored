# -*- coding: utf-8 -*-
"""日志管理模块"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler


def setup_logger(name="AutoKaraoke", level=logging.INFO):
    """配置并返回日志记录器
    
    Args:
        name: 日志记录器名称
        level: 日志级别，默认为 INFO
        
    Returns:
        配置好的 logger 实例
    """
    logger = logging.getLogger(name)
    
    # 防止重复添加 handler
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # 防止日志传播到根记录器

    # 确保 logs 目录存在
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 文件日志 - 使用 RotatingFileHandler 防止日志文件过大
    log_file_path = os.path.join(log_dir, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file_path,
        encoding="utf-8",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5  # 保留5个备份
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - [%(levelname)s] - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 控制台日志
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '%(levelname)s: %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger


def get_logger(name="AutoKaraoke"):
    """获取已存在的日志记录器
    
    Args:
        name: 日志记录器名称
        
    Returns:
        logger 实例
    """
    return logging.getLogger(name)
