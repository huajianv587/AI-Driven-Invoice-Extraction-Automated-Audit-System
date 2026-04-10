from __future__ import annotations

from src.product.settings import get_settings
from src.product.worker import run_worker


def main() -> None:
    run_worker(get_settings())


if __name__ == "__main__":
    main()
