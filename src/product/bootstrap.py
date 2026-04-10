from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Tuple

from src.db.mysql_client import MySQLClient
from src.product.repositories import MigrationRepository, UserRepository
from src.product.security import hash_password
from src.product.settings import ProductSettings


Migration = Tuple[str, Callable[[MySQLClient], None]]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _column_exists(db: MySQLClient, table_name: str, column_name: str, database_name: str) -> bool:
    row = db.fetch_one(
        """
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
        LIMIT 1
        """,
        (database_name, table_name, column_name),
    )
    return bool(row)


def _table_exists(db: MySQLClient, table_name: str, database_name: str) -> bool:
    row = db.fetch_one(
        """
        SELECT 1
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s
        LIMIT 1
        """,
        (database_name, table_name),
    )
    return bool(row)


def migration_product_tables(db: MySQLClient) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
          id BIGINT NOT NULL AUTO_INCREMENT,
          username VARCHAR(64) NOT NULL,
          password_hash VARCHAR(255) NOT NULL,
          role VARCHAR(32) NOT NULL,
          is_active TINYINT(1) NOT NULL DEFAULT 1,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_users_username (username)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
          id BIGINT NOT NULL AUTO_INCREMENT,
          user_id BIGINT NOT NULL,
          token VARCHAR(255) NOT NULL,
          expires_at DATETIME NOT NULL,
          revoked_at DATETIME NULL,
          last_used_at DATETIME NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_user_sessions_token (token),
          KEY idx_user_sessions_user_id (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_files (
          id BIGINT NOT NULL AUTO_INCREMENT,
          file_name VARCHAR(255) NOT NULL,
          original_name VARCHAR(255) NOT NULL,
          mime_type VARCHAR(128) NOT NULL,
          size_bytes BIGINT NOT NULL,
          sha256 CHAR(64) NOT NULL,
          storage_path VARCHAR(512) NOT NULL,
          uploaded_by VARCHAR(64) NOT NULL,
          source_type VARCHAR(32) NOT NULL DEFAULT 'api_upload',
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_invoice_files_sha256 (sha256)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_tasks (
          id BIGINT NOT NULL AUTO_INCREMENT,
          invoice_file_id BIGINT NOT NULL,
          invoice_id BIGINT NULL,
          task_type VARCHAR(32) NOT NULL DEFAULT 'INGEST',
          processing_status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
          retry_count INT NOT NULL DEFAULT 0,
          error_code VARCHAR(64) NULL,
          error_message TEXT NULL,
          trace_id VARCHAR(64) NOT NULL,
          worker_id VARCHAR(64) NULL,
          started_at DATETIME NULL,
          finished_at DATETIME NULL,
          created_by VARCHAR(64) NOT NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_invoice_tasks_status (processing_status),
          KEY idx_invoice_tasks_invoice_file_id (invoice_file_id),
          KEY idx_invoice_tasks_invoice_id (invoice_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_extractions (
          id BIGINT NOT NULL AUTO_INCREMENT,
          invoice_id BIGINT NOT NULL,
          task_id BIGINT NOT NULL,
          provider VARCHAR(64) NOT NULL,
          model_name VARCHAR(128) NOT NULL,
          model_version VARCHAR(128) NOT NULL,
          prompt_version VARCHAR(64) NOT NULL,
          fallback_source VARCHAR(64) NOT NULL DEFAULT 'none',
          confidence_overall DECIMAL(5, 4) NULL,
          confidence_by_field JSON NULL,
          raw_response JSON NULL,
          normalized_schema JSON NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_invoice_extractions_invoice_id (invoice_id),
          KEY idx_invoice_extractions_task_id (task_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS invoice_review_actions (
          id BIGINT NOT NULL AUTO_INCREMENT,
          invoice_id BIGINT NOT NULL,
          action_type VARCHAR(32) NOT NULL,
          review_status VARCHAR(32) NOT NULL,
          actor_user_id BIGINT NOT NULL,
          actor_username VARCHAR(64) NOT NULL,
          note TEXT NULL,
          payload JSON NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_invoice_review_actions_invoice_id (invoice_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_deliveries (
          id BIGINT NOT NULL AUTO_INCREMENT,
          invoice_id BIGINT NOT NULL,
          delivery_type VARCHAR(32) NOT NULL,
          channel VARCHAR(32) NOT NULL,
          recipient VARCHAR(255) NOT NULL,
          cc JSON NULL,
          status VARCHAR(32) NOT NULL,
          subject VARCHAR(255) NULL,
          payload JSON NULL,
          error_message TEXT NULL,
          delivered_at DATETIME NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          KEY idx_notification_deliveries_invoice_id (invoice_id),
          KEY idx_notification_deliveries_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS risk_rule_versions (
          id BIGINT NOT NULL AUTO_INCREMENT,
          version VARCHAR(64) NOT NULL,
          rule_name VARCHAR(128) NOT NULL,
          config_json JSON NULL,
          is_active TINYINT(1) NOT NULL DEFAULT 1,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (id),
          UNIQUE KEY uq_risk_rule_versions_name_version (rule_name, version)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def ensure_legacy_core_tables(db: MySQLClient, settings: ProductSettings) -> None:
    sql_dir = _project_root() / "sql"
    base_files = [
        "01_create_invoices.sql",
        "02_create_invoice_items.sql",
        "03_create_invoice_events.sql",
        "04_create_purchase_orders.sql",
        "05_create_invoice_feishu_sync.sql",
        "06_create_invoice_review_tasks.sql",
        "08_alter_invoices_add_purchase_order_no.sql",
    ]
    if settings.app_env == "local":
        base_files.append("07_seed_demo_purchase_orders.sql")
    for name in base_files:
        path = sql_dir / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        for statement in [part.strip() for part in text.split(";") if part.strip()]:
            db.execute(statement)


def migration_invoice_columns(db: MySQLClient, settings: ProductSettings) -> None:
    desired_columns = [
        ("processing_status", "ALTER TABLE invoices ADD COLUMN processing_status VARCHAR(32) NOT NULL DEFAULT 'PENDING' AFTER invoice_status"),
        ("review_status", "ALTER TABLE invoices ADD COLUMN review_status VARCHAR(32) NOT NULL DEFAULT 'PENDING' AFTER processing_status"),
        ("source_file_id", "ALTER TABLE invoices ADD COLUMN source_file_id BIGINT NULL AFTER handled_at"),
        ("current_task_id", "ALTER TABLE invoices ADD COLUMN current_task_id BIGINT NULL AFTER source_file_id"),
        ("latest_extraction_id", "ALTER TABLE invoices ADD COLUMN latest_extraction_id BIGINT NULL AFTER current_task_id"),
        ("confidence_overall", "ALTER TABLE invoices ADD COLUMN confidence_overall DECIMAL(5,4) NULL AFTER latest_extraction_id"),
    ]
    for column_name, ddl in desired_columns:
        if not _column_exists(db, "invoices", column_name, settings.mysql_db):
            db.execute(ddl)


def migration_indexes(db: MySQLClient, settings: ProductSettings) -> None:
    if _table_exists(db, "invoices", settings.mysql_db):
        db.execute(
            "CREATE INDEX idx_invoices_processing_status ON invoices(processing_status)"
            if not db.fetch_one(
                """
                SELECT 1
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME='invoices' AND INDEX_NAME='idx_invoices_processing_status'
                LIMIT 1
                """,
                (settings.mysql_db,),
            )
            else "DO 0"
        )
        db.execute(
            "CREATE INDEX idx_invoices_review_status ON invoices(review_status)"
            if not db.fetch_one(
                """
                SELECT 1
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA=%s AND TABLE_NAME='invoices' AND INDEX_NAME='idx_invoices_review_status'
                LIMIT 1
                """,
                (settings.mysql_db,),
            )
            else "DO 0"
        )


def available_migrations(settings: ProductSettings) -> List[Migration]:
    return [
        ("20260410_0001_product_tables", migration_product_tables),
        ("20260410_0002_invoice_columns", lambda db: migration_invoice_columns(db, settings)),
        ("20260410_0003_invoice_indexes", lambda db: migration_indexes(db, settings)),
    ]


def seed_default_users(db: MySQLClient, settings: ProductSettings) -> None:
    users = UserRepository(db)
    users.seed_user(settings.admin_username, hash_password(settings.admin_password), "admin")
    users.seed_user(settings.operator_username, hash_password(settings.operator_password), "operator")
    users.seed_user(settings.reviewer_username, hash_password(settings.reviewer_password), "reviewer")


def bootstrap_product_schema(db: MySQLClient, settings: ProductSettings) -> None:
    ensure_legacy_core_tables(db, settings)
    repo = MigrationRepository(db)
    repo.ensure_table()
    for name, migration in available_migrations(settings):
        if repo.has_migration(name):
            continue
        with db.transaction():
            migration(db)
            repo.mark_applied(name)
    seed_default_users(db, settings)
