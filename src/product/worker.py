from __future__ import annotations

import time
from typing import Optional

from src.product.bootstrap import bootstrap_product_schema
from src.product.repositories import TaskRepository
from src.product.services import ProductApplication, create_db, normalize_exception
from src.product.settings import ProductSettings, get_settings
from src.utils.logger import get_logger


logger = get_logger("invoice_audit.worker")


def run_worker(settings: Optional[ProductSettings] = None) -> None:
    config = settings or get_settings()
    db = create_db(config)
    bootstrap_product_schema(db, config)
    app = ProductApplication(db, config)
    tasks = TaskRepository(db)

    logger.info("worker started worker_id=%s poll_interval=%s", config.worker_id, config.task_poll_interval_sec)
    while True:
        claimed = tasks.claim_next(config.worker_id)
        if not claimed:
            time.sleep(config.task_poll_interval_sec)
            continue
        task_id = int(claimed["id"])
        logger.info("claimed task_id=%s trace_id=%s", task_id, claimed["trace_id"])
        try:
            app.process_task(task_id)
        except Exception as exc:
            error_code, error_message = normalize_exception(exc)
            logger.exception("task failed task_id=%s error=%s", task_id, exc)
            tasks.mark_failed(task_id, error_code, error_message)
