# src/db/explanation_repo.py
from __future__ import annotations

import secrets
from datetime import datetime
from typing import Any, Dict, Optional

class ExplanationRepository:
    """
    负责：
    1) 创建 explanation token（用于邮件链接）
    2) 表单提交后写回 explanations 表
    """

    def __init__(self, db):
        self.db = db

    def create_token_row(
        self,
        invoice_id: int,
        po_no: Optional[str],
        expected_amount: Optional[float],
        invoice_amount: Optional[float],
        amount_diff: Optional[float],
        to_email: str,
        cc_email: str,
    ) -> str:
        token = secrets.token_urlsafe(24)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 如果你 explanations 表字段不一样：按你表结构把列名对齐
        self.db.execute(
            """
            INSERT INTO explanations
              (invoice_id, token, po_no, expected_amount, invoice_amount, amount_diff,
               to_email, cc_email, status, created_at)
            VALUES
              (%s, %s, %s, %s, %s, %s,
               %s, %s, 'PENDING', %s)
            """,
            (invoice_id, token, po_no, expected_amount, invoice_amount, amount_diff,
             to_email, cc_email, now)
        )
        return token

    def get_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        return self.db.fetch_one(
            "SELECT * FROM explanations WHERE token=%s LIMIT 1",
            (token,)
        )

    def submit_reason(self, token: str, reason: str, submitter: str = "") -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.db.execute(
            """
            UPDATE explanations
            SET reason=%s, submitter=%s, status='SUBMITTED', submitted_at=%s
            WHERE token=%s
            """,
            (reason, submitter, now, token)
        )
        return True
