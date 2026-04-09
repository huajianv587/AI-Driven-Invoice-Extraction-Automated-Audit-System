# src/jobs/feishu_sync_job.py
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger
from src.services.feishu_bitable_client import FeishuBitableClient

logger = get_logger()


def _cfg_pick(cfg: Dict[str, Any], keys: List[str], default: Any = None) -> Any:
    for k in keys:
        v = cfg.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return default


def sync_pending_invoices_to_feishu(db, cfg: Dict[str, Any], limit: int = 50) -> Tuple[int, int]:
    """
    db: 你的 main.DB 适配器（有 fetch_all/execute）
    返回：(success_count, fail_count)
    """
    app_id = _cfg_pick(cfg, ["feishu_app_id", "FEISHU_APP_ID"])
    app_secret = _cfg_pick(cfg, ["feishu_app_secret", "FEISHU_APP_SECRET"])
    app_token = _cfg_pick(cfg, ["feishu_app_token", "FEISHU_APP_TOKEN", "bitable_app_token"])
    table_id = _cfg_pick(cfg, ["feishu_table_id", "FEISHU_TABLE_ID", "bitable_table_id"])

    if not (app_id and app_secret and app_token and table_id):
        logger.warning("[FeishuSync] missing feishu config -> skip")
        return 0, 0

    client = FeishuBitableClient(app_id=app_id, app_secret=app_secret, app_token=app_token, table_id=table_id)
    token = client.get_tenant_token()
    if not token:
        logger.warning("[FeishuSync] cannot get tenant token -> skip")
        return 0, 0

    # 1) 查未同步（用 sync 表做幂等）
    sql = """
    SELECT i.*
    FROM invoices i
    LEFT JOIN invoice_feishu_sync s ON s.invoice_id = i.id
    WHERE s.invoice_id IS NULL
    ORDER BY i.id ASC
    LIMIT %s
    """
    rows = db.fetch_all(sql, (int(limit),))

    if not rows:
        logger.info("[FeishuSync] nothing to sync")
        return 0, 0

    ok = 0
    fail = 0

    for r in rows:
        invoice_id = r.get("id")
        try:
            # 2) 组装飞书 fields（这里用 invoices 表字段为主，避免再跑一次 Dify）
            fields = {
                "invoice_id": str(invoice_id or ""),
                "unique_hash": str(r.get("unique_hash") or ""),
                "source_file_path": str(r.get("source_file_path") or ""),
                "invoice_code": r.get("invoice_code"),
                "invoice_number": r.get("invoice_number"),
                "invoice_date": r.get("invoice_date"),
                "seller_name": r.get("seller_name"),
                "buyer_name": r.get("buyer_name"),
                "total_amount_with_tax": r.get("total_amount_with_tax"),
                "expected_amount": r.get("expected_amount"),
                "amount_diff": r.get("amount_diff"),
                "risk_flag": r.get("risk_flag"),
                "risk_reason": r.get("risk_reason"),  # Feishu client 会把 list/dict json.dumps
            }

            ok_add, resp = client.add_record(token, fields)

            if ok_add:
                record_id = ((resp.get("data") or {}).get("record") or {}).get("record_id")
                db.execute(
                    "INSERT INTO invoice_feishu_sync(invoice_id, feishu_record_id, synced_at, sync_error) VALUES(%s,%s,NOW(),NULL)",
                    (invoice_id, record_id),
                )
                ok += 1
            else:
                db.execute(
                    "INSERT INTO invoice_feishu_sync(invoice_id, feishu_record_id, synced_at, sync_error) VALUES(%s,NULL,NULL,%s)",
                    (invoice_id, json.dumps(resp, ensure_ascii=False)[:2000]),
                )
                fail += 1

        except Exception as e:
            fail += 1
            try:
                db.execute(
                    "INSERT INTO invoice_feishu_sync(invoice_id, feishu_record_id, synced_at, sync_error) VALUES(%s,NULL,NULL,%s)",
                    (invoice_id, repr(e)[:2000]),
                )
            except Exception:
                pass
            logger.exception("[FeishuSync] failed invoice_id=%s err=%s", invoice_id, repr(e))

    logger.info("[FeishuSync] done ok=%s fail=%s", ok, fail)
    return ok, fail
