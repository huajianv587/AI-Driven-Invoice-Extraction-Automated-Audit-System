from __future__ import annotations
import argparse
import csv
from dotenv import load_dotenv
from src.db.mysql_client import MySQLClient
from src.db.repositories import PORepository
from src.utils.logger import get_logger

logger = get_logger()

def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="CSV with columns: po_no, expected_amount, currency(optional), vendor_name(optional)")
    args = ap.parse_args()

    db = MySQLClient()
    repo = PORepository(db)

    with open(args.csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        cnt = 0
        for row in reader:
            repo.upsert(
                po_no=row["po_no"],
                expected_amount=float(row["expected_amount"]),
                currency=row.get("currency"),
                vendor_name=row.get("vendor_name"),
            )
            cnt += 1
    logger.info("Seeded %s purchase orders.", cnt)

if __name__ == "__main__":
    main()
