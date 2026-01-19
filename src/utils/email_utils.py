# src/api/main.py
from __future__ import annotations

import os
from datetime import datetime
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.utils.logger import get_logger
from src.db.mysql_client import MySQLClient
from src.api.routes.explanations import router as explanations_router  # 你原来的表单路由（如果有）

logger = get_logger()

app = FastAPI(title="Invoice AI Audit API")


@app.on_event("startup")
def _startup():
    """
    只初始化一次 db，避免每个请求都 new 连接导致卡死/很慢
    """
    try:
        app.state.db = MySQLClient()
        logger.info("[API] startup: db ready")
    except Exception as e:
        # 即使 DB 挂了，health 也能回，便于排障
        app.state.db = None
        logger.exception("[API] startup: db init failed: %s", e)


def _get_db(request: Request) -> MySQLClient:
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "db not ready")
    return db


@app.get("/health")
def health():
    # 不要在 health 里查库，保证秒回
    return {"ok": True}


# ✅ 解释/补充表单（你原来的路由）
app.include_router(explanations_router)


# =========================
# Review Form: /review/{task_id}?token=xxxx
# =========================
@app.get("/review/{task_id}", response_class=HTMLResponse)
def review_form(request: Request, task_id: int, token: str):
    db = _get_db(request)
    task = db.fetch_one("SELECT * FROM approval_tasks WHERE id=%s", (task_id,))
    if not task:
        raise HTTPException(404, "task not found")

    if (task.get("token") or "") != (token or ""):
        raise HTTPException(403, "invalid token")

    invoice_id = task.get("invoice_id")
    cur_status = task.get("status") or ""
    cur_reason = task.get("reason") or ""
    cur_handled_by = task.get("handled_by") or ""

    html = f"""
    <html>
      <head>
        <meta charset="utf-8">
        <title>Invoice Review</title>
      </head>
      <body style="font-family: Arial; padding: 24px;">
        <h2>Invoice Review Task #{task_id}</h2>
        <p><b>Invoice ID:</b> {invoice_id}</p>
        <p><b>Status:</b> {cur_status}</p>

        <form method="post" action="/review/{task_id}/submit">
          <input type="hidden" name="token" value="{token}" />

          <label>处理人（邮箱/姓名）:</label><br/>
          <input name="handled_by" style="width:420px" value="{cur_handled_by}" required /><br/><br/>

          <label>原因说明（必填）:</label><br/>
          <textarea name="reason" rows="8" cols="90" required>{cur_reason}</textarea><br/><br/>

          <label>处理结果:</label><br/>
          <select name="status">
            <option value="RESOLVED">已核实/已处理</option>
            <option value="REJECTED">拒绝/需重新开票</option>
          </select><br/><br/>

          <button type="submit">提交</button>
        </form>
      </body>
    </html>
    """
    return HTMLResponse(html)


@app.post("/review/{task_id}/submit")
def submit_review(
    request: Request,
    task_id: int,
    token: str = Form(...),
    handled_by: str = Form(...),
    reason: str = Form(...),
    status: str = Form("RESOLVED"),
):
    db = _get_db(request)
    task = db.fetch_one("SELECT * FROM approval_tasks WHERE id=%s", (task_id,))
    if not task:
        raise HTTPException(404, "task not found")

    if (task.get("token") or "") != (token or ""):
        raise HTTPException(403, "invalid token")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        "UPDATE approval_tasks SET status=%s, reason=%s, handled_by=%s, handled_at=%s WHERE id=%s",
        (status, reason, handled_by, now, task_id),
    )

    # 可选：回写 invoices（没有列就忽略）
    invoice_id = task.get("invoice_id")
    try:
        db.execute(
            "UPDATE invoices SET handler_reason=%s, handler_user=%s, handled_at=%s WHERE id=%s",
            (reason, handled_by, now, invoice_id),
        )
    except Exception:
        pass

    return RedirectResponse(url=f"/review/{task_id}?token={token}", status_code=303)

