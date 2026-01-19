import logging
import os

def get_logger(name: str = "invoice_ai_audit"):
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger(name)
