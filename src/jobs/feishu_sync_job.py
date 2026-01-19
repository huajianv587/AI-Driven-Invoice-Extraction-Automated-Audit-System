from __future__ import annotations
import argparse
import os
import json
from typing import Any, Dict, List, Optional, Tuple
from dotenv import load_dotenv

from src.utils.logger import get_logger
from src.db.mysql_client import MySQLClient
from src.clients.feishu_bitable_client import FeishuBitableClient
from src.utils.flatten import build_feishu_fields_from_normalized

logger = get_logger()

def _env(key: str, default: str = "") -> str:
    v = os.getenv(key)
    return v if v is not None else default

def ensure_sync_table(db: MySQLClient):
    db.execute("""CREATE TABLE IF NOT EXISTS invoice_feishu_sync (
      invoice_id BIGINT PRIMARY KEY,
      feishu_record_id VARCHAR(64) NULL,
      synced_at DATETIME NULL,
      attempt_count INT NOT NULL DEFAULT 0,
      last_attempt_at DATETIME NULL,
      sync_error TEXT NULL
    );""")

def sync(limit: int = 200) -> Tuple[int, int]:
    db = MySQLClient()
    ensure_sync_table(db)

    app_id = _env("FEISHU_APP_ID")
    app_secret = _env("FEISHU_APP_SECRET")
    app_token = _env("FEISHU_APP_TOKEN")
    table_id = _env("FEISHU_TABLE_ID")
    unique_field = _env("FEISHU_UNIQUE_FIELD", "unique_hash")

    if not (app_id and app_secret and app_token and table_id):
        logger.warning("Feishu config missing, skip sync.")
        return 0, 0

    client = FeishuBitableClient(app_id, app_secret, app_token, table_id)
    token = client.get_tenant_token()
    if not token:
        logger.warning("Cannot get tenant token, skip sync.")
        return 0, 0

    rows = db.fetch_all(
        """SELECT i.* FROM invoices i
            LEFT JOIN invoice_feishu_sync s ON s.invoice_id=i.id
            WHERE s.invoice_id IS NULL OR (s.synced_at IS NULL AND s.attempt_count < 10)
            ORDER BY i.id ASC
            LIMIT %s""",
        (int(limit),)
    )

    ok, fail = 0, 0
    for r in rows:
        invoice_id = int(r["id"])
        unique_value = r.get("unique_hash") or ""
        try:
            db.execute(
                """INSERT INTO invoice_feishu_sync(invoice_id, attempt_count, last_attempt_at)
                     VALUES(%s,1,NOW())
                     ON DUPLICATE KEY UPDATE attempt_count=attempt_count+1, last_attempt_at=NOW()""",
                (invoice_id,)
            )

            normalized = r.get("normalized_json") or {}
            fields = build_feishu_fields_from_normalized(normalized)
            # Add operational fields
            fields["invoice_id"] = str(invoice_id)
            fields["unique_hash"] = unique_value
            fields["status"] = r.get("status")

            ok_up, resp, record_id = client.upsert_by_unique_field(token, unique_field, unique_value, fields)
            if ok_up:
                db.execute(
                    """UPDATE invoice_feishu_sync SET feishu_record_id=%s, synced_at=NOW(), sync_error=NULL
                         WHERE invoice_id=%s""",
                    (record_id, invoice_id)
                )
                ok += 1
            else:
                db.execute(
                    """UPDATE invoice_feishu_sync SET sync_error=%s WHERE invoice_id=%s""",
                    (json.dumps(resp, ensure_ascii=False)[:2000], invoice_id)
                )
                fail += 1
        except Exception as e:
            fail += 1
            db.execute(
                """UPDATE invoice_feishu_sync SET sync_error=%s WHERE invoice_id=%s""",
                (repr(e)[:2000], invoice_id)
            )
            logger.exception("sync failed invoice_id=%s", invoice_id)

    logger.info("Feishu sync done ok=%s fail=%s", ok, fail)
    return ok, fail

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    sync(limit=args.limit)

if __name__ == "__main__":
    main()
