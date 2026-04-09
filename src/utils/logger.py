import logging
import os
from logging.handlers import RotatingFileHandler

_LOGGER_CACHE = {}

def get_logger(name: str = "invoice_audit", log_file: str = "logs/app.log", level=logging.INFO) -> logging.Logger:
    """
    Create or return a singleton logger instance.
    """
    if name in _LOGGER_CACHE:
        return _LOGGER_CACHE[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s - %(message)s"
        )

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _LOGGER_CACHE[name] = logger
    return logger
