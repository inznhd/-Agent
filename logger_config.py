import logging
import os
from datetime import datetime


def setup_logger() -> str:
    """
    配置根 logger，每启动一次生成一个独立日志文件。
    日志文件位于 logs/YYYYMMDD_HHMMSS.log

    Returns:
        str: 日志文件路径
    """
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"{timestamp}.log")

    # 日志格式
    formatter = logging.Formatter(
        "%(asctime)s - [%(levelname)s] - [%(name)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # FileHandler（追加模式，但每次启动文件名不同，等价于独立文件）
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # 根 logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    # 清除已有 handler（防止重复调用 setup_logger 时重复）
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)

    logging.getLogger(__name__).info(f"日志系统初始化完成, 文件: {log_path}")
    return log_path
