from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, TextIO


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.db.mysql_client import MySQLClient
from src.jobs.feishu_sync_job import sync_invoices_to_feishu


LOCK_PATH = Path(tempfile.gettempdir()) / "invoice_audit_feishu_retry_worker.lock"


def build_db(cfg: Dict[str, Any]) -> MySQLClient:
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
    parser = argparse.ArgumentParser(description="Run the periodic Feishu sync recovery worker.")
    parser.add_argument("--once", action="store_true", help="Run a single recovery cycle and exit.")
    parser.add_argument("--mode", choices=["pending", "failed", "recoverable", "all"], default=None)
    parser.add_argument("--interval", type=int, default=None, help="Polling interval in seconds.")
    parser.add_argument("--limit", type=int, default=None, help="Max invoices to retry in one cycle.")
    return parser.parse_args()


def _prepare_lock_handle(lock_path: Path) -> TextIO:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+", encoding="utf-8")
    handle.seek(0)
    if not handle.read(1):
        handle.write("0")
        handle.flush()
    handle.seek(0)
    return handle


def acquire_worker_lock(lock_path: Path) -> Optional[TextIO]:
    handle = _prepare_lock_handle(lock_path)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None

    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def release_worker_lock(handle: Optional[TextIO]) -> None:
    if not handle:
        return
    try:
        handle.seek(0)
        handle.truncate()
        handle.write("0")
        handle.flush()
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        handle.close()


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def main() -> int:
    args = parse_args()
    load_env(override=True)
    cfg = load_flat_config()

    enabled = bool(cfg.get("FEISHU_RETRY_WORKER_ENABLED"))
    mode = str(args.mode or cfg.get("FEISHU_RETRY_MODE") or "failed").strip().lower()
    interval = int(args.interval or cfg.get("FEISHU_RETRY_INTERVAL_SEC") or 300)
    limit = int(args.limit or cfg.get("FEISHU_RETRY_BATCH_LIMIT") or 20)

    if not args.once and not enabled:
        emit(
            {
                "status": "disabled",
                "message": "FEISHU_RETRY_WORKER_ENABLED is false. Worker will not start.",
            }
        )
        return 0

    if interval <= 0:
        raise ValueError(f"interval must be > 0, got {interval}")
    if limit <= 0:
        raise ValueError(f"limit must be > 0, got {limit}")

    lock_handle = acquire_worker_lock(LOCK_PATH)
    if lock_handle is None:
        emit(
            {
                "status": "already_running",
                "message": "Another Feishu retry worker already holds the lock.",
                "lock_path": str(LOCK_PATH),
            }
        )
        return 0

    db = build_db(cfg)
    cycle = 0
    try:
        emit(
            {
                "status": "started",
                "mode": mode,
                "interval_sec": interval,
                "limit": limit,
                "once": args.once,
                "lock_path": str(LOCK_PATH),
            }
        )
        while True:
            cycle += 1
            started_at = dt.datetime.now().isoformat(timespec="seconds")
            ok_count, fail_count, details = sync_invoices_to_feishu(
                db,
                cfg,
                mode=mode,
                limit=limit,
            )
            emit(
                {
                    "status": "cycle_complete",
                    "cycle": cycle,
                    "started_at": started_at,
                    "mode": mode,
                    "limit": limit,
                    "ok_count": ok_count,
                    "fail_count": fail_count,
                    "detail_count": len(details),
                    "details": details[:5],
                }
            )
            if args.once:
                break
            time.sleep(interval)
    except KeyboardInterrupt:
        emit({"status": "stopped", "message": "Feishu retry worker stopped by user."})
        return 0
    finally:
        db.close()
        release_worker_lock(lock_handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
