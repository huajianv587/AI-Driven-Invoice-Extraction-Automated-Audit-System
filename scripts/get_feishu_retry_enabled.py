from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config


def main() -> int:
    load_env(override=True)
    cfg = load_flat_config()
    enabled = bool(cfg.get("FEISHU_RETRY_WORKER_ENABLED"))
    print("1" if enabled else "0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
