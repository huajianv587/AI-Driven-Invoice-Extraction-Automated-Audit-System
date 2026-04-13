from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.db.mysql_client import MySQLClient
from src.jobs.feishu_sync_job import sync_invoices_to_feishu


def build_db(cfg):
    return MySQLClient(
        host=cfg["mysql_host"],
        port=int(cfg["mysql_port"]),
        user=cfg["mysql_user"],
        password=cfg["mysql_password"],
        db=cfg["mysql_db"],
        connect_timeout=10,
        autocommit=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry or replay Feishu Bitable sync from MySQL invoices.")
    parser.add_argument("--mode", choices=["pending", "failed", "recoverable", "all"], default="failed")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--invoice-id", dest="invoice_ids", action="append", type=int, default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env(override=True)
    cfg = load_flat_config()
    db = build_db(cfg)
    try:
        ok, fail, details = sync_invoices_to_feishu(
            db,
            cfg,
            mode=args.mode,
            limit=args.limit,
            invoice_ids=args.invoice_ids or None,
        )
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "limit": args.limit,
                    "invoice_ids": args.invoice_ids,
                    "ok_count": ok,
                    "fail_count": fail,
                    "details": details,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
