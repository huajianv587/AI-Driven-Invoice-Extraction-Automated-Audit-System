# src/api/routes/explanations.py
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from src.utils.logger import get_logger

logger = get_logger()
router = APIRouter()

HTML_FORM = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Invoice Explanation</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 30px; }}
    .box {{ max-width: 720px; }}
    textarea {{ width: 100%; height: 160px; }}
    .meta {{ background:#f7f7f7; padding:12px; border-radius:8px; margin-bottom:16px; }}
    button {{ padding: 10px 16px; }}
  </style>
</head>
<body>
  <div class="box">
    <h2>发票金额与采购订单金额不一致 — 说明表单</h2>
    <div class="meta">
      <div><b>Invoice ID:</b> {invoice_id}</div>
      <div><b>PO No:</b> {po_no}</div>
      <div><b>Expected Amount:</b> {expected_amount}</div>
      <div><b>Invoice Amount:</b> {invoice_amount}</div>
      <div><b>Amount Diff:</b> {amount_diff}</div>
      <div><b>Status:</b> {status}</div>
    </div>

    <form method="post">
      <label>请填写原因（必填）：</label><br/>
      <textarea name="reason" required placeholder="例如：供应商分批开票/税率差异/折扣未同步/PO金额录入错误/已获批准等"></textarea><br/><br/>
      <label>提交人（可选）：</label><br/>
      <input type="text" name="submitter" placeholder="姓名/工号/邮箱" style="width:100%; padding:8px;"/><br/><br/>

      <button type="submit">提交说明</button>
    </form>
  </div>
</body>
</html>
"""

HTML_OK = """
<!doctype html>
<html><head><meta charset="utf-8"/><title>Submitted</title></head>
<body style="font-family:Arial; margin:30px;">
  <h2>✅ 已提交</h2>
  <p>你的说明已写入系统，感谢配合。</p>
</body></html>
"""

@router.get("/explain/{token}", response_class=HTMLResponse)
def explain_get(token: str, request: Request):
    db = request.app.state.db
    row = db.fetch_one("SELECT * FROM explanations WHERE token=%s LIMIT 1", (token,))
    if not row:
        return HTMLResponse("<h3>Token 无效或已过期</h3>", status_code=404)

    return HTMLResponse(
        HTML_FORM.format(
            invoice_id=row.get("invoice_id"),
            po_no=row.get("po_no"),
            expected_amount=row.get("expected_amount"),
            invoice_amount=row.get("invoice_amount"),
            amount_diff=row.get("amount_diff"),
            status=row.get("status"),
        )
    )

@router.post("/explain/{token}", response_class=HTMLResponse)
def explain_post(
    token: str,
    request: Request,
    reason: str = Form(...),
    submitter: str = Form(""),
):
    db = request.app.state.db
    row = db.fetch_one("SELECT * FROM explanations WHERE token=%s LIMIT 1", (token,))
    if not row:
        return HTMLResponse("<h3>Token 无效或已过期</h3>", status_code=404)

    # 写回 explanations
    db.execute(
        """
        UPDATE explanations
        SET reason=%s, submitter=%s, status='SUBMITTED', submitted_at=NOW()
        WHERE token=%s
        """,
        (reason, submitter, token)
    )

    # 可选：把原因回写到 invoices（如果你 invoices 有 handler_reason/handled_at 等列）
    # 没有就删掉这一段
    try:
        invoice_id = row.get("invoice_id")
        db.execute(
            """
            UPDATE invoices
            SET handler_reason=%s, handled_at=NOW(), invoice_status='EXPLAINED'
            WHERE id=%s
            """,
            (reason, invoice_id)
        )
    except Exception as e:
        logger.warning("invoices 回写失败（可忽略）：%s", e)

    return HTMLResponse(HTML_OK)
