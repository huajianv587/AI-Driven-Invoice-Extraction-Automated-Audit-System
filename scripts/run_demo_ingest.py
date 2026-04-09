from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.main import build_service
from src.services.ingestion_service import process_one_image


def main() -> None:
    load_env(override=True)
    cfg = load_flat_config()

    raw_arg = sys.argv[1] if len(sys.argv) > 1 else "invoice.jpg"
    file_path = Path(raw_arg)
    if not file_path.is_absolute():
        candidate = ROOT / "invoices" / raw_arg
        file_path = candidate if candidate.exists() else ROOT / raw_arg
    file_path = file_path.resolve()

    if not file_path.exists():
        raise FileNotFoundError(file_path)

    svc = build_service(cfg)
    try:
        result = process_one_image(str(file_path), cfg, svc)
        if not result.ok:
            raise RuntimeError(f"Ingestion failed: {result}")
        if result.action != "inserted":
            raise RuntimeError(f"Expected a fresh demo insert, got action={result.action}")

        db = svc.invoice_repo.db
        invoice = db.fetch_one(
            """
            SELECT id, invoice_code, invoice_number, purchase_order_no,
                   total_amount_with_tax, expected_amount, amount_diff,
                   risk_flag, invoice_status, unique_hash
            FROM invoices
            WHERE id=%s
            """,
            (result.invoice_id,),
        )
        email_event = db.fetch_one(
            """
            SELECT event_type, event_status, payload
            FROM invoice_events
            WHERE invoice_id=%s AND event_type='EMAIL_ALERT'
            ORDER BY id DESC
            LIMIT 1
            """,
            (result.invoice_id,),
        )
        if email_event and isinstance(email_event.get("payload"), str):
            try:
                email_event["payload"] = json.loads(email_event["payload"])
            except Exception:
                pass

        summary = {
            "file_path": str(file_path),
            "result": {
                "ok": result.ok,
                "action": result.action,
                "invoice_id": result.invoice_id,
                "unique_hash": result.unique_hash,
            },
            "invoice": invoice,
            "email_event": email_event,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    finally:
        db = getattr(getattr(svc, "invoice_repo", None), "db", None)
        if db and hasattr(db, "close"):
            db.close()


if __name__ == "__main__":
    main()
