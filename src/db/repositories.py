# src/db/repositories.py
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from src.db.mysql_client import MySQLClient


class InvoiceRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def find_by_unique_hash(self, unique_hash: str) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one(
            "SELECT * FROM invoices WHERE unique_hash=%s LIMIT 1",
            (unique_hash,),
        )

    def insert_invoice(self, row: Dict[str, Any]) -> int:
        """
        插入发票主表（幂等由 unique_hash 唯一键保证）
        如果插入冲突，抛异常由上层处理（或你也可以改成 ON DUPLICATE KEY UPDATE）
        """
        sql = """
        INSERT INTO invoices(
          invoice_type, invoice_code, invoice_number, invoice_date, check_code, machine_code,
          invoice_status, is_red_invoice, red_invoice_ref,
          seller_name, seller_tax_id, seller_address, seller_phone, seller_bank, seller_bank_account,
          buyer_name, buyer_tax_id, buyer_address, buyer_phone, buyer_bank, buyer_bank_account,
          total_amount_without_tax, total_tax_amount, total_amount_with_tax, amount_in_words,
          drawer, reviewer, payee, remarks, purchase_order_no,
          source_file_path, raw_ocr_json, llm_json, schema_version,
          expected_amount, amount_diff, risk_flag, risk_reason,
          unique_hash
        )
        VALUES(
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,
          %s,%s,%s,%s,%s,
          %s,%s,%s,%s,
          %s,%s,%s,%s,
          %s
        )
        """
        params = (
            row.get("invoice_type"), row.get("invoice_code"), row.get("invoice_number"), row.get("invoice_date"),
            row.get("check_code"), row.get("machine_code"),
            row.get("invoice_status", "Pending"), row.get("is_red_invoice", 0), row.get("red_invoice_ref"),

            row.get("seller_name"), row.get("seller_tax_id"), row.get("seller_address"), row.get("seller_phone"),
            row.get("seller_bank"), row.get("seller_bank_account"),

            row.get("buyer_name"), row.get("buyer_tax_id"), row.get("buyer_address"), row.get("buyer_phone"),
            row.get("buyer_bank"), row.get("buyer_bank_account"),

            row.get("total_amount_without_tax"), row.get("total_tax_amount"), row.get("total_amount_with_tax"),
            row.get("amount_in_words"),

            row.get("drawer"), row.get("reviewer"), row.get("payee"), row.get("remarks"),
            row.get("purchase_order_no"),

            row.get("source_file_path"),
            json.dumps(row.get("raw_ocr_json"), ensure_ascii=False) if row.get("raw_ocr_json") is not None else None,
            json.dumps(row.get("llm_json"), ensure_ascii=False) if row.get("llm_json") is not None else None,
            row.get("schema_version", "v1"),

            row.get("expected_amount"), row.get("amount_diff"), row.get("risk_flag", 0),
            json.dumps(row.get("risk_reason"), ensure_ascii=False) if row.get("risk_reason") is not None else None,

            row["unique_hash"],
        )
        return self.db.execute_returning_id(sql, params)

    def update_llm_json(self, invoice_id: int, llm_json: Dict[str, Any]) -> int:
        return self.db.execute(
            "UPDATE invoices SET llm_json=%s, updated_at=NOW() WHERE id=%s",
            (json.dumps(llm_json, ensure_ascii=False), invoice_id),
        )


class InvoiceItemRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def insert_items(self, invoice_id: int, items: List[Dict[str, Any]]) -> int:
        if not items:
            return 0

        sql = """
        INSERT INTO invoice_items(
          invoice_id, item_name, item_spec, item_unit, item_quantity,
          item_unit_price, item_amount, tax_rate, tax_amount
        )
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """

        params_list = []
        for it in items:
            params_list.append((
                invoice_id,
                it.get("item_name"),
                it.get("item_spec"),
                it.get("item_unit"),
                it.get("item_quantity"),
                it.get("item_unit_price"),
                it.get("item_amount"),
                it.get("tax_rate"),
                it.get("tax_amount"),
            ))

        return self.db.executemany(sql, params_list)

    def delete_by_invoice_id(self, invoice_id: int) -> int:
        return self.db.execute("DELETE FROM invoice_items WHERE invoice_id=%s", (invoice_id,))


class InvoiceEventRepository:
    def __init__(self, db: MySQLClient):
        self.db = db

    def add_event(self, invoice_id: int, event_type: str, event_status: str, payload: Optional[Dict[str, Any]] = None) -> int:
        sql = """
        INSERT INTO invoice_events(invoice_id, event_type, event_status, payload)
        VALUES(%s, %s, %s, %s)
        """
        payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        return self.db.execute_returning_id(sql, (invoice_id, event_type, event_status, payload_json))
