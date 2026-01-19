from __future__ import annotations
import argparse
import os
from glob import glob
from dotenv import load_dotenv

from src.db.mysql_client import MySQLClient
from src.db.repositories import InvoiceRepository, InvoiceItemRepository, EventRepository, RiskRepository, PORepository
from src.services.ingestion_service import run_pipeline_for_invoice_file
from src.utils.logger import get_logger

logger = get_logger()

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="folder path containing invoice images/pdfs")
    args = ap.parse_args()

    db = MySQLClient()
    invoice_repo = InvoiceRepository(db)
    item_repo = InvoiceItemRepository(db)
    event_repo = EventRepository(db)
    risk_repo = RiskRepository(db)
    po_repo = PORepository(db)

    cfg = {k: os.getenv(k) for k in os.environ.keys()}

    files = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp", "*.pdf"):
        files.extend(glob(os.path.join(args.input, ext)))

    if not files:
        logger.warning("No files found in %s", args.input)
        return

    for fp in sorted(files):
        res = run_pipeline_for_invoice_file(fp, cfg, invoice_repo, item_repo, event_repo, risk_repo, po_repo)
        logger.info("Ingest %s -> %s (invoice_id=%s, fallback=%s)", os.path.basename(fp), res.action, res.invoice_id, res.used_fallback)

if __name__ == "__main__":
    main()
