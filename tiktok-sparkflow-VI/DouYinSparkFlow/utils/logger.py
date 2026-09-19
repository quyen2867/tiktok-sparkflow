import logging
import os
from logging.handlers import RotatingFileHandler

# Tạo thư mục logs nếu chưa có
if not os.path.exists("logs"):
    os.makedirs("logs")

# Định dạng log
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"

# Đường dẫn file log
LOG_FILE = "logs/app.log"

# Cấu hình log
def setup_logger(name="app", level=logging.INFO):
    """
    Cấu hình logger
    :param name: Tên logger
    :param level: Mức log
    :return: Logger đã cấu hình
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Tránh thêm handler trùng lặp
    if not logger.handlers:
        # Handler log ra console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(LOG_FORMAT)
        console_handler.setFormatter(console_formatter)

        # Handler ghi file log (có xoay vòng)
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(LOG_FORMAT)
        file_handler.setFormatter(file_formatter)

        # Gắn handler vào logger
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger


# Ví dụ: dùng logger
if __name__ == "__main__":
    logger = setup_logger(level=logging.DEBUG)
    logger.debug("Đây là log debug")
    logger.info("Đây là log thông thường")
    logger.warning("Đây là log cảnh báo")
    logger.error("Đây là log lỗi")
    logger.critical("Đây là log lỗi nghiêm trọng")