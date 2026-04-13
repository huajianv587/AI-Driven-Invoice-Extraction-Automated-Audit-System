from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.services.feishu_bitable_client import FeishuBitableClient
from src.utils.logger import get_logger


logger = get_logger()


def _cfg_pick(cfg: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        value = cfg.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return default


def _build_feishu_fields_from_invoice(row: Dict[str, Any], ingest_action: str = "replay_sync") -> Dict[str, Any]:
    source_file_path = str(row.get("source_file_path") or "")
    file_name = os.path.basename(source_file_path) if source_file_path else ""

    def normalize(value: Any) -> Any:
        if isinstance(value, (dt.date, dt.datetime)):
            return value.isoformat()
        return value

    return {
        "invoice_id": str(row.get("id") or ""),
        "unique_hash": str(row.get("unique_hash") or ""),
        "ingest_action": ingest_action,
        "file_name": file_name,
        "source_file_path": source_file_path,
        "purchase_order_no": str(row.get("purchase_order_no") or ""),
        "invoice_code": normalize(row.get("invoice_code")),
        "invoice_number": normalize(row.get("invoice_number")),
        "invoice_date": normalize(row.get("invoice_date")),
        "invoice_type": normalize(row.get("invoice_type")),
        "seller_name": normalize(row.get("seller_name")),
        "seller_tax_id": normalize(row.get("seller_tax_id")),
        "buyer_name": normalize(row.get("buyer_name")),
        "buyer_tax_id": normalize(row.get("buyer_tax_id")),
        "total_amount_without_tax": normalize(row.get("total_amount_without_tax")),
        "total_tax_amount": normalize(row.get("total_tax_amount")),
        "total_amount_with_tax": normalize(row.get("total_amount_with_tax")),
        "expected_amount": normalize(row.get("expected_amount")),
        "amount_diff": normalize(row.get("amount_diff")),
        "risk_flag": normalize(row.get("risk_flag")),
        "risk_reason": normalize(row.get("risk_reason")),
    }


def _upsert_sync_success(db, invoice_id: int, record_id: Optional[str]) -> None:
    db.execute(
        """
        INSERT INTO invoice_feishu_sync(invoice_id, feishu_record_id, synced_at, sync_error)
        VALUES(%s, %s, NOW(), NULL)
        ON DUPLICATE KEY UPDATE
          feishu_record_id=VALUES(feishu_record_id),
          synced_at=VALUES(synced_at),
          sync_error=NULL,
          updated_at=NOW()
        """,
        (invoice_id, record_id),
    )


def _upsert_sync_failure(db, invoice_id: int, error: Any) -> None:
    db.execute(
        """
        INSERT INTO invoice_feishu_sync(invoice_id, feishu_record_id, synced_at, sync_error)
        VALUES(%s, NULL, NULL, %s)
        ON DUPLICATE KEY UPDATE
          feishu_record_id=NULL,
          synced_at=NULL,
          sync_error=VALUES(sync_error),
          updated_at=NOW()
        """,
        (invoice_id, str(error)[:2000]),
    )


def _build_select_sql(mode: str, invoice_ids: Optional[Iterable[int]], limit: int) -> Tuple[str, Tuple[Any, ...]]:
    clauses: List[str] = []
    params: List[Any] = []

    invoice_id_list = [int(item) for item in (invoice_ids or []) if str(item).strip()]
    if invoice_id_list:
        placeholders = ", ".join(["%s"] * len(invoice_id_list))
        clauses.append(f"i.id IN ({placeholders})")
        params.extend(invoice_id_list)
    elif mode == "pending":
        clauses.append("s.invoice_id IS NULL")
    elif mode == "failed":
        clauses.append("s.invoice_id IS NOT NULL AND (s.feishu_record_id IS NULL OR s.sync_error IS NOT NULL)")
    elif mode == "recoverable":
        clauses.append("(s.invoice_id IS NULL OR s.feishu_record_id IS NULL OR s.sync_error IS NOT NULL)")
    elif mode != "all":
        raise ValueError(f"Unsupported Feishu sync mode: {mode}")

    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"""
    SELECT
      i.*,
      s.feishu_record_id,
      s.synced_at,
      s.sync_error
    FROM invoices i
    LEFT JOIN invoice_feishu_sync s ON s.invoice_id = i.id
    {where_clause}
    ORDER BY i.id ASC
    LIMIT %s
    """
    params.append(int(limit))
    return sql, tuple(params)


def sync_invoices_to_feishu(
    db,
    cfg: Dict[str, Any],
    *,
    mode: str = "recoverable",
    limit: int = 50,
    invoice_ids: Optional[Iterable[int]] = None,
) -> Tuple[int, int, List[Dict[str, Any]]]:
    app_id = _cfg_pick(cfg, ["feishu_app_id", "FEISHU_APP_ID"])
    app_secret = _cfg_pick(cfg, ["feishu_app_secret", "FEISHU_APP_SECRET"])
    app_token = _cfg_pick(cfg, ["feishu_app_token", "FEISHU_APP_TOKEN", "bitable_app_token"])
    table_id = _cfg_pick(cfg, ["feishu_table_id", "FEISHU_TABLE_ID", "bitable_table_id"])

    if not (app_id and app_secret and app_token and table_id):
        logger.warning("[FeishuSync] missing feishu config -> skip")
        return 0, 0, []

    client = FeishuBitableClient(app_id=app_id, app_secret=app_secret, app_token=app_token, table_id=table_id)
    token = client.get_tenant_token()
    if not token:
        logger.warning("[FeishuSync] cannot get tenant token -> skip")
        return 0, 0, []

    sql, params = _build_select_sql(mode, invoice_ids, limit)
    rows = db.fetch_all(sql, params)
    if not rows:
        logger.info("[FeishuSync] nothing to sync for mode=%s", mode)
        return 0, 0, []

    success_count = 0
    fail_count = 0
    details: List[Dict[str, Any]] = []

    for row in rows:
        invoice_id = int(row.get("id") or 0)
        try:
            fields = _build_feishu_fields_from_invoice(row)
            ok, resp = client.add_record(token, fields)
            if ok:
                record_id = ((resp.get("data") or {}).get("record") or {}).get("record_id")
                _upsert_sync_success(db, invoice_id, record_id)
                success_count += 1
                details.append(
                    {
                        "invoice_id": invoice_id,
                        "ok": True,
                        "record_id": record_id,
                        "error": None,
                    }
                )
            else:
                _upsert_sync_failure(db, invoice_id, json.dumps(resp, ensure_ascii=False))
                fail_count += 1
                details.append(
                    {
                        "invoice_id": invoice_id,
                        "ok": False,
                        "record_id": None,
                        "error": resp,
                    }
                )
        except Exception as exc:
            _upsert_sync_failure(db, invoice_id, repr(exc))
            fail_count += 1
            details.append(
                {
                    "invoice_id": invoice_id,
                    "ok": False,
                    "record_id": None,
                    "error": repr(exc),
                }
            )
            logger.exception("[FeishuSync] failed invoice_id=%s err=%s", invoice_id, repr(exc))

    logger.info("[FeishuSync] done mode=%s ok=%s fail=%s", mode, success_count, fail_count)
    return success_count, fail_count, details


def sync_pending_invoices_to_feishu(db, cfg: Dict[str, Any], limit: int = 50) -> Tuple[int, int]:
    ok, fail, _ = sync_invoices_to_feishu(db, cfg, mode="pending", limit=limit)
    return ok, fail


def retry_failed_invoices_to_feishu(db, cfg: Dict[str, Any], limit: int = 50) -> Tuple[int, int]:
    ok, fail, _ = sync_invoices_to_feishu(db, cfg, mode="failed", limit=limit)
    return ok, fail
