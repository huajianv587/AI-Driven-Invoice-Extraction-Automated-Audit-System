from __future__ import annotations

import uvicorn

from src.config import load_env, load_flat_config


def main() -> None:
    load_env()
    cfg = load_flat_config()
    uvicorn.run("src.api.app:app", host="127.0.0.1", port=int(cfg["API_PORT"]), reload=False)


if __name__ == "__main__":
    main()
