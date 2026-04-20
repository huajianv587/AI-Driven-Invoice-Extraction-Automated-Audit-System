from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    os.environ.setdefault("WEB_E2E_MODE", "required")
    os.environ.setdefault("ALLOW_REAL_INTEGRATION_TESTS", "0")
    os.environ.setdefault("WEB_DEEP_RESET_DEMO_DB", "0")
    os.environ.setdefault("WEB_DEEP_EXTERNAL_PREFIX", "REQUIRED_TEST")
    os.environ.setdefault("DIFY_REQUIRED", "True")
    os.environ.setdefault("FEISHU_SYNC_REQUIRED", "True")
    os.environ.setdefault("FEISHU_SYNC_MODE", "inline")
    os.environ.setdefault("EMAIL_ALERT_REQUIRED", "True")
    os.environ.setdefault("PLAYWRIGHT_STACK_PORT", os.getenv("PLAYWRIGHT_REQUIRED_STACK_PORT", "3412"))

    from scripts.run_web_e2e_stack import main as run_stack

    run_stack()


if __name__ == "__main__":
    main()
