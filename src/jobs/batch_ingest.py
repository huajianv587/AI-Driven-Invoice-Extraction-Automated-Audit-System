from typing import Any, Dict, Optional

from src.main import build_service, list_invoice_files
from src.services.ingestion_service import process_one_image
from src.utils.logger import get_logger


logger = get_logger()


def run_batch(cfg: Dict[str, Any], svc: Optional[Any] = None) -> None:
    invoices_dir = cfg["invoices_dir"]
    files = list_invoice_files(invoices_dir)

    if not files:
        logger.warning("No invoice files found in: %s", invoices_dir)
        return

    logger.info("Found %s invoice files", len(files))

    own_service = False
    if svc is None:
        svc = build_service(cfg)
        own_service = True

    try:
        for path in files:
            try:
                logger.info("Processing: %s", path)
                result = process_one_image(path, cfg, svc)
                logger.info("Done: %s => %s", path, result)
            except Exception as exc:
                logger.exception("Failed: %s error=%s", path, exc)
    finally:
        if own_service:
            db = getattr(getattr(svc, "invoice_repo", None), "db", None)
            if db and hasattr(db, "close"):
                db.close()
