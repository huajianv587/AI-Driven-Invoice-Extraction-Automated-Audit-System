from __future__ import annotations

import sys
from pathlib import Path

import pymysql
import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config


TABLES_TO_CLEAR = [
    "invoice_state_transitions",
    "invoice_review_tasks",
    "invoice_feishu_sync",
    "invoice_events",
    "invoice_items",
    "invoices",
    "app_security_events",
    "app_login_attempts",
    "app_refresh_tokens",
]


def clear_mailpit() -> None:
    try:
        resp = requests.delete("http://127.0.0.1:8025/api/v1/messages", timeout=10)
        resp.raise_for_status()
        print("[ok] Cleared Mailpit inbox.")
    except Exception as exc:
        print(f"[warn] Failed to clear Mailpit inbox: {exc}")


def reset_mysql_tables(cfg) -> None:
    conn = pymysql.connect(
        host=cfg["mysql_host"],
        port=int(cfg["mysql_port"]),
        user=cfg["mysql_user"],
        password=cfg["mysql_password"],
        database=cfg["mysql_db"],
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        with conn.cursor() as cur:
            for table in TABLES_TO_CLEAR:
                cur.execute(f"DELETE FROM {table}")
            for table in TABLES_TO_CLEAR:
                cur.execute(f"ALTER TABLE {table} AUTO_INCREMENT = 1")
        conn.commit()
        print("[ok] Reset invoice demo tables.")
    finally:
        conn.close()


def main() -> None:
    load_env(override=True)
    cfg = load_flat_config()
    if str(cfg.get("APP_ENV") or "local").strip().lower() in {"prod", "production"}:
        raise RuntimeError("Refusing to reset demo invoice tables while APP_ENV is production.")
    reset_mysql_tables(cfg)
    clear_mailpit()
    print("[ok] Demo state reset complete.")


if __name__ == "__main__":
    main()
