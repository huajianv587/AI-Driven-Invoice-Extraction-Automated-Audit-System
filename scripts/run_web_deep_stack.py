from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ.setdefault("WEB_E2E_MODE", "deep")
    os.environ.setdefault("ALLOW_REAL_INTEGRATION_TESTS", "0")
    os.environ.setdefault("WEB_DEEP_RESET_DEMO_DB", "0")
    os.environ.setdefault("WEB_DEEP_EXTERNAL_PREFIX", "DEEP_TEST")
    os.environ.setdefault("PLAYWRIGHT_STACK_PORT", os.getenv("PLAYWRIGHT_DEEP_STACK_PORT", "3411"))

    from scripts.run_web_e2e_stack import main as run_stack

    run_stack()


if __name__ == "__main__":
    main()
