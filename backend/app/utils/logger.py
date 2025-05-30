"""
默认日志配置，提供简单的日志记录功能。
"""
from .logging_setup import get_logger, set_log_level

def getLogger(name: str):
    """
    获取一个配置好的logger实例

    Args:
        name: logger名称，通常使用模块名，如 __name__

    Returns:
        配置好的logger实例
    """
    set_log_level("DEBUG")
    return get_logger(name)


# 创建一个默认的logger实例
logger = getLogger("tiny_tools")

# 导出logger和getLogger函数
__all__ = ['logger', 'getLogger']