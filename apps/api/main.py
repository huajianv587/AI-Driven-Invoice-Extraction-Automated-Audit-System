from __future__ import annotations

import uvicorn

from src.product.api import app
from src.product.settings import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
