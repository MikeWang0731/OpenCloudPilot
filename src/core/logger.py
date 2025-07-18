# -*- coding: utf-8 -*-
"""
日志配置模块
"""

import logging
import sys
from typing import Optional


def setup_logger(level: str = "INFO", name: Optional[str] = None) -> logging.Logger:
    """设置日志配置"""
    logger = logging.getLogger(name or "cloudpilot")

    # 避免重复添加handler
    if logger.handlers:
        return logger

    # 设置日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # 设置日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(formatter)

    # 添加处理器
    logger.addHandler(console_handler)

    return logger
