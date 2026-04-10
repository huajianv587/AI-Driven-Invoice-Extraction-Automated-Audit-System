from __future__ import annotations

import sys

from src.product.bootstrap import bootstrap_product_schema
from src.product.services import create_db
from src.product.settings import get_settings


def main() -> None:
    settings = get_settings()
    db = create_db(settings)
    try:
        bootstrap_product_schema(db, settings)
    finally:
        db.close()
    print("[ok] Product migrations applied successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        sys.exit(1)

