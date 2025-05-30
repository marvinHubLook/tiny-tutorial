"""
日志配置模块，提供工业级的日志记录功能。
"""
import os
import sys

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import logging
import logging.handlers
from datetime import datetime
from pathlib import Path
from typing import Optional

# 日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def get_logger(name: str) -> logging.Logger:
    """
    获取一个配置好的logger实例

    Args:
        name: logger名称

    Returns:
        配置好的logger实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 清除现有的处理器
    logger.handlers.clear()

    # 设置日志格式
    formatter = logging.Formatter(
        fmt='%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 添加控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 添加文件处理器
    log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def set_log_level(level: str):
    """
    设置日志级别

    Args:
        level: 日志级别，可选值：DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
    logging.getLogger().setLevel(log_level)