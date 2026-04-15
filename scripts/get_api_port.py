from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config


def main() -> None:
    load_env(override=True)
    cfg = load_flat_config()
    print(int(cfg["API_PORT"]))


if __name__ == "__main__":
    main()
