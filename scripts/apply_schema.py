import hashlib
import os
import sys
import time
from pathlib import Path

import pymysql
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"


ADD_COLUMNS = {
    "app_refresh_tokens": [
        ("ip_address", "VARCHAR(64) NULL"),
        ("device_label", "VARCHAR(128) NULL"),
        ("last_seen_at", "DATETIME NULL"),
        ("revoked_reason", "VARCHAR(64) NULL"),
    ],
    "invoice_review_tasks": [
        ("idempotency_key", "VARCHAR(128) NULL"),
        ("request_id", "VARCHAR(64) NULL"),
    ],
}

ADD_INDEXES = {
    "invoice_review_tasks": [
        (
            "uq_invoice_review_tasks_idempotency",
            "UNIQUE KEY `uq_invoice_review_tasks_idempotency` (`idempotency_key`)",
        ),
        ("idx_invoice_review_tasks_request_id", "KEY `idx_invoice_review_tasks_request_id` (`request_id`)"),
    ],
}


def load_settings():
    load_dotenv(ROOT / ".env")
    return {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3307")),
        "user": os.getenv("MYSQL_USER", "invoice_app"),
        "password": os.getenv("MYSQL_PASSWORD", "invoice_app_password"),
        "database": os.getenv("MYSQL_DB", "enterprise_ai"),
        "root_password": os.getenv("MYSQL_ROOT_PASSWORD", "root123456"),
    }


def connect_mysql(settings, *, use_root: bool = False, database: str | None = None):
    user = "root" if use_root else settings["user"]
    password = settings["root_password"] if use_root else settings["password"]
    db_name = database if database is not None else settings["database"]
    return pymysql.connect(
        host=settings["host"],
        port=settings["port"],
        user=user,
        password=password,
        database=db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
    )


def bootstrap_database_and_user(settings):
    db_name = settings["database"].replace("`", "")
    user = settings["user"].replace("'", "''")
    password = settings["password"].replace("'", "''")

    conn = connect_mysql(settings, use_root=True, database="mysql")
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            if user.lower() != "root":
                cur.execute(f"CREATE USER IF NOT EXISTS '{user}'@'%' IDENTIFIED BY '{password}'")
                cur.execute(f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{user}'@'%'")
            cur.execute("FLUSH PRIVILEGES")
        conn.commit()
    finally:
        conn.close()


def wait_for_mysql(settings, timeout_sec: int = 90):
    deadline = time.time() + timeout_sec
    last_error = None

    while time.time() < deadline:
        try:
            return connect_mysql(settings)
        except Exception as exc:
            last_error = exc
            try:
                bootstrap_database_and_user(settings)
                return connect_mysql(settings)
            except Exception as bootstrap_exc:
                last_error = bootstrap_exc
            print(f"[wait] MySQL not ready yet: {exc}")
            time.sleep(2)

    raise RuntimeError(f"MySQL not ready after {timeout_sec}s: {last_error}")


def split_sql(sql_text: str):
    return [statement.strip() for statement in sql_text.split(";") if statement.strip()]


def ensure_schema_tracking_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_schema_migrations (
              file_name VARCHAR(255) NOT NULL,
              checksum CHAR(64) NOT NULL,
              applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
              PRIMARY KEY (file_name),
              KEY idx_app_schema_migrations_updated (updated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        )
    conn.commit()


def record_schema_file(conn, path: Path, sql_text: str):
    checksum = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_schema_migrations(file_name, checksum, applied_at)
            VALUES(%s, %s, NOW())
            ON DUPLICATE KEY UPDATE
              checksum=VALUES(checksum),
              applied_at=VALUES(applied_at),
              updated_at=NOW()
            """,
            (path.name, checksum),
        )
    conn.commit()


def apply_schema(conn):
    files = sorted(SQL_DIR.glob("*.sql"))
    if not files:
        raise RuntimeError(f"No SQL files found in {SQL_DIR}")

    ensure_schema_tracking_table(conn)
    for path in files:
        sql_text = path.read_text(encoding="utf-8").strip()
        if not sql_text:
            print(f"[skip] {path.name} is empty")
            continue

        print(f"[apply] {path.name}")
        with conn.cursor() as cur:
            for statement in split_sql(sql_text):
                cur.execute(statement)
        conn.commit()
        record_schema_file(conn, path, sql_text)


def column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS column_count
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND column_name = %s
            """,
            (table_name, column_name),
        )
        row = cur.fetchone() or {}
    return int(row.get("column_count") or 0) > 0


def index_exists(conn, table_name: str, index_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS index_count
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND index_name = %s
            """,
            (table_name, index_name),
        )
        row = cur.fetchone() or {}
    return int(row.get("index_count") or 0) > 0


def ensure_additive_columns(conn):
    with conn.cursor() as cur:
        for table_name, columns in ADD_COLUMNS.items():
            cur.execute(
                """
                SELECT COUNT(*) AS table_count
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = %s
                """,
                (table_name,),
            )
            if int((cur.fetchone() or {}).get("table_count") or 0) == 0:
                continue

            for column_name, definition in columns:
                if column_exists(conn, table_name, column_name):
                    continue
                print(f"[alter] {table_name}.{column_name}")
                cur.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{column_name}` {definition}")
    conn.commit()


def ensure_additive_indexes(conn):
    with conn.cursor() as cur:
        for table_name, indexes in ADD_INDEXES.items():
            cur.execute(
                """
                SELECT COUNT(*) AS table_count
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = %s
                """,
                (table_name,),
            )
            if int((cur.fetchone() or {}).get("table_count") or 0) == 0:
                continue

            for index_name, definition in indexes:
                if index_exists(conn, table_name, index_name):
                    continue
                print(f"[alter] {table_name}.{index_name}")
                cur.execute(f"ALTER TABLE `{table_name}` ADD {definition}")
    conn.commit()


def main():
    if not SQL_DIR.exists():
        raise RuntimeError(f"SQL directory not found: {SQL_DIR}")

    settings = load_settings()
    conn = wait_for_mysql(settings)
    try:
        apply_schema(conn)
        ensure_additive_columns(conn)
        ensure_additive_indexes(conn)
    finally:
        conn.close()
    print("[ok] Schema applied successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        sys.exit(1)
