from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from scripts.apply_schema import load_settings, split_sql, wait_for_mysql
from src.config import load_env


DEFAULT_SQL_PATH = ROOT / "demo" / "demo_snapshot.sql"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import the git-tracked demo SQL snapshot into MySQL.")
    parser.add_argument("--sql-file", default=str(DEFAULT_SQL_PATH), help="Path to the .sql file to import.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env(override=True)

    sql_path = Path(args.sql_file).expanduser()
    if not sql_path.is_absolute():
        sql_path = (ROOT / sql_path).resolve()
    if not sql_path.exists():
        raise FileNotFoundError(sql_path)

    settings = load_settings()
    conn = wait_for_mysql(settings)
    try:
        sql_text = sql_path.read_text(encoding="utf-8").strip()
        if not sql_text:
            raise RuntimeError(f"SQL file is empty: {sql_path}")

        with conn.cursor() as cur:
            for statement in split_sql(sql_text):
                cur.execute(statement)
        conn.commit()
    finally:
        conn.close()

    print(f"[ok] Imported demo SQL from: {sql_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
