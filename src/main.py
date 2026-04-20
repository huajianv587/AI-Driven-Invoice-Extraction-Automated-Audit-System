import inspect
import os
from glob import glob
from typing import Any, Dict, List

from src.config import load_env, load_flat_config
from src.api.services import mark_intake_upload_failed, mark_intake_upload_processing, sync_intake_upload_result
from src.db.mysql_client import MySQLClient
from src.runtime_preflight import ensure_runtime_preflight
from src.services import ingestion_service
from src.utils.logger import get_logger


logger = get_logger()


def _mask(s: str, keep: int = 4) -> str:
    if not s:
        return "EMPTY"
    s = str(s).strip()
    if len(s) <= keep * 2:
        return f"{s} (len={len(s)})"
    return s[:keep] + "..." + s[-keep:] + f" (len={len(s)})"


def list_invoice_files(folder: str) -> List[str]:
    patterns = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.pdf"]
    files: List[str] = []
    for pattern in patterns:
        files.extend(glob(os.path.join(folder, pattern)))
    return sorted(set(files))


def build_db(cfg: Dict[str, Any]) -> MySQLClient:
    return MySQLClient(
        host=cfg["mysql_host"],
        port=int(cfg["mysql_port"]),
        user=cfg["mysql_user"],
        password=cfg["mysql_password"],
        db=cfg["mysql_db"],
        connect_timeout=10,
        autocommit=False,
    )


def _pick_class(mod, candidates: List[str]):
    for name in candidates:
        cls = getattr(mod, name, None)
        if cls is not None and inspect.isclass(cls):
            return cls
    return None


def build_service(cfg: Dict[str, Any]):
    db = build_db(cfg)
    from src.db import repositories as repo_mod
    from src.services.ingestion_service import IngestionService

    invoice_repo_cls = _pick_class(repo_mod, ["InvoiceRepository", "InvoicesRepository", "InvoiceRepo"])
    item_repo_cls = _pick_class(
        repo_mod,
        ["InvoiceItemRepository", "ItemsRepository", "InvoiceItemsRepository", "ItemRepository", "ItemRepo"],
    )
    event_repo_cls = _pick_class(
        repo_mod,
        ["InvoiceEventRepository", "EventsRepository", "InvoiceEventsRepository", "EventRepository", "EventRepo"],
    )

    if invoice_repo_cls is None:
        raise ImportError(
            "Cannot find InvoiceRepository class in src/db/repositories.py. "
            f"Available: {[name for name in dir(repo_mod) if not name.startswith('_')]}"
        )

    invoice_repo = invoice_repo_cls(db)
    item_repo = item_repo_cls(db) if item_repo_cls else None
    event_repo = event_repo_cls(db) if event_repo_cls else None

    sig = inspect.signature(IngestionService.__init__)
    kwargs = {}
    if "invoice_repo" in sig.parameters:
        kwargs["invoice_repo"] = invoice_repo
    if "item_repo" in sig.parameters:
        kwargs["item_repo"] = item_repo
    if "event_repo" in sig.parameters:
        kwargs["event_repo"] = event_repo

    try:
        return IngestionService(**kwargs)
    except TypeError:
        args = [invoice_repo]
        if item_repo is not None:
            args.append(item_repo)
        if event_repo is not None:
            args.append(event_repo)
        return IngestionService(*args)


def main() -> None:
    env_path = load_env()
    if env_path:
        logger.info("Loaded .env from: %s", env_path)
    else:
        logger.warning("No .env found (project root or src/). Continue with system env.")

    cfg = load_flat_config()
    ensure_runtime_preflight(cfg, context="Invoice ingestion worker")

    logger.info(
        "MYSQL_HOST=%s MYSQL_PORT=%s MYSQL_DB=%s",
        cfg["mysql_host"],
        cfg["mysql_port"],
        cfg["mysql_db"],
    )
    logger.info("DIFY_WORKFLOW_ID=%s", _mask(cfg["dify_workflow_id"]))
    logger.info("DIFY_IMAGE_KEY=%s", cfg["dify_image_key"])
    logger.info("FEISHU_APP_ID=%s", _mask(cfg["feishu_app_id"]))
    logger.info("FEISHU_APP_TOKEN=%s", _mask(cfg["feishu_app_token"]))
    logger.info("FEISHU_TABLE_ID=%s", _mask(cfg["feishu_table_id"]))

    invoices_dir = cfg["invoices_dir"]
    if not os.path.isdir(invoices_dir):
        raise FileNotFoundError(f"invoices_dir not found: {invoices_dir}")

    files = list_invoice_files(invoices_dir)
    if not files:
        logger.warning("No invoice images/pdfs found in: %s", invoices_dir)
        return

    logger.info("Found %s file(s) in %s", len(files), invoices_dir)

    svc = build_service(cfg)
    ok = 0
    fail = 0

    try:
        db = getattr(getattr(svc, "invoice_repo", None), "db", None)
        for fp in files:
            try:
                logger.info("Processing: %s", fp)
                mark_intake_upload_processing(db, source_file_path=fp)
                result = ingestion_service.process_one_image(fp, cfg, svc)
                sync_intake_upload_result(db, source_file_path=fp, result=result)
                if bool(getattr(result, "ok", False)):
                    ok += 1
                else:
                    fail += 1
                    logger.error("Worker returned error state for %s: %s", fp, getattr(result, "error", "unknown error"))
            except Exception as exc:
                fail += 1
                mark_intake_upload_failed(db, source_file_path=fp, error_message=str(exc))
                logger.exception("Failed processing %s: %s", fp, exc)
    finally:
        db = getattr(getattr(svc, "invoice_repo", None), "db", None)
        if db and hasattr(db, "close"):
            db.close()

    logger.info("Done. success=%s, failed=%s", ok, fail)


if __name__ == "__main__":
    main()
