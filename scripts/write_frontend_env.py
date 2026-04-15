from __future__ import annotations

import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config


def main() -> None:
    load_env(override=True)
    cfg = load_flat_config()
    public_host = os.getenv("FRONTEND_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"

    frontend_dir = ROOT / "frontend"
    frontend_dir.mkdir(exist_ok=True)
    env_path = frontend_dir / ".env.local"

    content = "\n".join(
        [
            "# Auto-generated from the repository .env by scripts/write_frontend_env.py.",
            "# Edit the root .env file, then rerun start_frontend.bat or start_web_stack.bat.",
            f"NEXT_PUBLIC_API_BASE_URL=http://{public_host}:{int(cfg['API_PORT'])}",
            f"NEXT_PUBLIC_REFRESH_COOKIE_NAME={cfg['AUTH_COOKIE_NAME']}",
            f"NEXT_PUBLIC_BOOTSTRAP_ADMIN_EMAIL={cfg['AUTH_BOOTSTRAP_ADMIN_EMAIL']}",
            "",
        ]
    )

    if env_path.exists() and env_path.read_text(encoding="utf-8") == content:
        print(f"[ok] Frontend env already current: {env_path}")
        return

    env_path.write_text(content, encoding="utf-8")
    print(f"[ok] Wrote frontend env: {env_path}")


if __name__ == "__main__":
    main()
