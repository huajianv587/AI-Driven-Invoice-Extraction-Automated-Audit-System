from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

import pymysql


Params = Union[Tuple[Any, ...], List[Any], None]


class MySQLClient:
    """
    Lightweight pymysql client with reconnect and common helpers.
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        db: str,
        connect_timeout: int = 10,
        autocommit: bool = False,
    ):
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.db = db
        self.connect_timeout = int(connect_timeout)
        self.autocommit = bool(autocommit)
        self._in_transaction = False
        self.conn = self._connect()

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.db,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=self.connect_timeout,
            autocommit=self.autocommit,
        )

    def _ensure_conn(self) -> None:
        if self.conn is None:
            self.conn = self._connect()
            return
        try:
            self.conn.ping(reconnect=True)
        except Exception:
            self.conn = self._connect()

    def close(self) -> None:
        try:
            if self.conn is not None:
                self.conn.close()
        except Exception:
            pass
        finally:
            self.conn = None
            self._in_transaction = False

    def _cursor(self):
        self._ensure_conn()
        return self.conn.cursor()

    def begin(self) -> None:
        if self.autocommit:
            raise RuntimeError("Transactions are not available when autocommit=True")
        self._ensure_conn()
        if self._in_transaction:
            raise RuntimeError("Transaction already started")
        self.conn.begin()
        self._in_transaction = True

    def commit(self) -> None:
        if self.conn is None:
            return
        self.conn.commit()
        self._in_transaction = False

    def rollback(self) -> None:
        if self.conn is None:
            return
        self.conn.rollback()
        self._in_transaction = False

    @contextmanager
    def transaction(self) -> Iterator["MySQLClient"]:
        self.begin()
        try:
            yield self
            self.commit()
        except Exception:
            self.rollback()
            raise

    def fetch_one(self, sql: str, params: Params = None) -> Optional[Dict[str, Any]]:
        cur = self._cursor()
        try:
            cur.execute(sql, params)
            return cur.fetchone()
        finally:
            cur.close()

    def fetch_all(self, sql: str, params: Params = None) -> List[Dict[str, Any]]:
        cur = self._cursor()
        try:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return list(rows) if rows else []
        finally:
            cur.close()

    def execute(self, sql: str, params: Params = None) -> int:
        cur = self._cursor()
        try:
            cur.execute(sql, params)
            if not self.autocommit and not self._in_transaction:
                self.conn.commit()
            return int(cur.rowcount or 0)
        except Exception:
            if not self.autocommit and not self._in_transaction:
                self.conn.rollback()
            raise
        finally:
            cur.close()

    def execute_returning_id(self, sql: str, params: Params = None) -> int:
        cur = self._cursor()
        try:
            cur.execute(sql, params)
            last_id = cur.lastrowid
            if not self.autocommit and not self._in_transaction:
                self.conn.commit()
            return int(last_id or 0)
        except Exception:
            if not self.autocommit and not self._in_transaction:
                self.conn.rollback()
            raise
        finally:
            cur.close()

    def executemany(self, sql: str, seq_params: Sequence[Tuple[Any, ...]]) -> int:
        if not seq_params:
            return 0

        cur = self._cursor()
        try:
            cur.executemany(sql, seq_params)
            if not self.autocommit and not self._in_transaction:
                self.conn.commit()
            return int(cur.rowcount or 0)
        except Exception:
            if not self.autocommit and not self._in_transaction:
                self.conn.rollback()
            raise
        finally:
            cur.close()


class DB(MySQLClient):
    pass
