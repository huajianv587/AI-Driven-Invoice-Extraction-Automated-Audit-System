from __future__ import annotations
import pymysql
from typing import Any, Dict, List, Optional, Sequence, Tuple
from src.config import get_mysql_cfg
from src.utils.logger import get_logger

logger = get_logger()

class MySQLClient:
    def __init__(self):
        cfg = get_mysql_cfg()
        self.cfg = cfg

    def _conn(self):
        return pymysql.connect(
            host=self.cfg.host,
            port=self.cfg.port,
            user=self.cfg.user,
            password=self.cfg.password,
            database=self.cfg.db,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
        )

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.rowcount

    def fetch_one(self, sql: str, params: Sequence[Any] | None = None) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def fetch_all(self, sql: str, params: Sequence[Any] | None = None) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())
