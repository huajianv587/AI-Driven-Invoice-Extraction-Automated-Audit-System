from __future__ import annotations
import os
from dotenv import load_dotenv
from src.db.mysql_client import MySQLClient
from src.utils.logger import get_logger

logger = get_logger()

def main():
    load_dotenv()
    db = MySQLClient()
    sql_path = os.path.join(os.path.dirname(__file__), "..", "migrations", "001_init.sql")
    sql_path = os.path.abspath(sql_path)
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    # split by semicolon safely (simple)
    stmts = [s.strip() for s in sql.split(";") if s.strip()]
    for s in stmts:
        db.execute(s)
    logger.info("Migration done. Tables created/updated.")

if __name__ == "__main__":
    main()
