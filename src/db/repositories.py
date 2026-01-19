from __future__ import annotations
import pymysql
# NOTE: do NOT put any code/print before the __future__ import.
print(">>> repositories.py loaded from:", __file__)
from typing import Any, Dict, Optional, List
import json
from typing import Any, Dict, Optional, List
from src.db.mysql_client import MySQLClient
from typing import Dict, Any, List
class InvoiceRepository:
    def __init__(self, db):
        self.db = db

    def find_by_code_number(self, invoice_code: str, invoice_number: str):
        sql = """
        SELECT *
        FROM invoices
        WHERE invoice_code=%s AND invoice_number=%s
        LIMIT 1
        """
        return self.db.fetch_one(sql, (invoice_code, invoice_number))

    def _get_invoice_columns(self) -> List[str]:
        # 缓存一次就行（进程内）
        if hasattr(self, "_invoice_cols_cache") and self._invoice_cols_cache:
            return self._invoice_cols_cache

        rows = self.db.fetch_all("SHOW COLUMNS FROM invoices", ())
        cols = [r["Field"] for r in rows]
        self._invoice_cols_cache = cols
        return cols

    def _jsonify(self, v):
        # 你原来如果已有 _jsonify，就保留原实现；没有就用下面这个
        import json
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False, default=str)
        return v

    def insert_invoice(self, row: Dict[str, Any]) -> int:
        cols = list(row.keys())
        vals = [self._jsonify(row[c]) for c in cols]

        sql = "INSERT INTO invoices(" + ",".join(cols) + ") VALUES(" + ",".join(["%s"] * len(cols)) + ")"

        try:
            self.db.execute(sql, vals)
        except pymysql.err.IntegrityError as e:
            # 1062 = Duplicate entry (unique key)
            if len(e.args) >= 1 and int(e.args[0]) == 1062:
                got = self.db.fetch_one(
                    sql="SELECT id FROM invoices WHERE unique_hash=%s",
                    params=(row["unique_hash"],)
                )
                if got:
                    return int(got["id"])
            raise

        got = self.db.fetch_one(
            sql="SELECT id FROM invoices WHERE unique_hash=%s",
            params=(row["unique_hash"],)
        )
        return int(got["id"])

    def update_invoice(self, invoice_id: int, patch: Dict[str, Any]) -> None:
        cols = list(patch.keys())
        # ✅ 同样转一下
        vals = [self._jsonify(patch[c]) for c in cols]

        sets = ", ".join([f"{c}=%s" for c in cols])
        sql = f"UPDATE invoices SET {sets} WHERE id=%s"
        self.db.execute(sql, vals + [invoice_id])

    def get(self, invoice_id: int) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one("SELECT * FROM invoices WHERE id=%s", (invoice_id,))

    def list_recent(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.db.fetch_all("SELECT * FROM invoices ORDER BY id DESC LIMIT %s", (int(limit),))

import json

class InvoiceItemRepository:
    def __init__(self, db):
        self.db = db
        self._table_cols_cache = None

    def _jsonify(self, v: Any) -> Any:
        """把 dict/list 转成 JSON 字符串，避免 pymysql: dict can not be used as parameter"""
        if v is None:
            return None
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return v

    def _get_table_cols(self):
        if self._table_cols_cache is not None:
            return self._table_cols_cache
        rows = self.db.fetch_all("SHOW COLUMNS FROM invoice_items", params=None)
        cols = [r["Field"] for r in rows]  # DataGrip/SHOW COLUMNS 的字段名是 Field
        self._table_cols_cache = cols
        return cols

    def replace_items(self, invoice_id: int, items: List[Dict[str, Any]]):
        # 1) 先删旧行
        self.db.execute("DELETE FROM invoice_items WHERE invoice_id=%s", (invoice_id,))

        if not items:
            return

        # 2) 逐行插入（必须包含 line_no）
        sql = """
        INSERT INTO invoice_items
        (invoice_id, line_no, item_name, spec, qty, unit, unit_price, amount, tax_rate, tax_amount, remark, raw_json)
        VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        for idx, it in enumerate(items, start=1):
            # 兼容你现在 LLM 输出的两套 key（发票1和发票2不一样）
            item_name = it.get("item_name") or it.get("description")
            spec = it.get("item_specification") or it.get("specification") or it.get("item_code")
            qty = it.get("item_quantity") if it.get("item_quantity") is not None else it.get("quantity")
            unit = it.get("item_unit") or it.get("unit")
            unit_price = it.get("item_unit_price") if it.get("item_unit_price") is not None else it.get("unit_price")

            amount = (
                it.get("item_total_amount")
                if it.get("item_total_amount") is not None
                else it.get("item_total_price")
            )
            if amount is None:
                amount = it.get("amount")

            tax_rate = it.get("item_tax_rate") if it.get("item_tax_rate") is not None else it.get("tax_rate")
            tax_amount = it.get("item_tax_amount") if it.get("item_tax_amount") is not None else it.get("tax_amount")

            remark = it.get("remark") or it.get("remarks")

            # ✅ 关键：pymysql 不允许 dict 直接当参数，必须 json.dumps
            raw_json = json.dumps(it, ensure_ascii=False)

            vals = (
                invoice_id,
                idx,  # ✅ line_no
                item_name,
                spec,
                qty,
                unit,
                unit_price,
                amount,
                tax_rate,
                tax_amount,
                remark,
                raw_json,
            )
            self.db.execute(sql, vals)


class EventRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def _jsonify(v):
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        return v

    def add(self, invoice_id: int, event_type: str, message: str, payload: Optional[Dict[str, Any]] = None):
        sql = "INSERT INTO invoice_events(invoice_id,event_type,message,payload) VALUES(%s,%s,%s,%s)"
        self.db.execute(sql, (invoice_id, event_type, message, self._jsonify(payload)))

class RiskRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def add_hit(self, invoice_id: int, rule_id: str, severity: str, reason: str, evidence: str | None = None):
        self.db.execute(
            "INSERT INTO risk_hits(invoice_id,rule_id,severity,reason,evidence) VALUES(%s,%s,%s,%s,%s)",
            (invoice_id, rule_id, severity, reason, evidence),
        )

    def list_hits(self, invoice_id: int) -> List[Dict[str, Any]]:
        return self.db.fetch_all("SELECT * FROM risk_hits WHERE invoice_id=%s ORDER BY id DESC", (invoice_id,))

class PORepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def get(self, po_no: str) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one("SELECT * FROM purchase_orders WHERE po_no=%s", (po_no,))

    def upsert(self, po_no: str, expected_amount: float, currency: str | None = None, vendor_name: str | None = None):
        self.db.execute(
            "INSERT INTO purchase_orders(po_no, expected_amount, currency, vendor_name) VALUES(%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE expected_amount=VALUES(expected_amount), currency=VALUES(currency), vendor_name=VALUES(vendor_name)",
            (po_no, expected_amount, currency, vendor_name),
        )
