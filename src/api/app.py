from __future__ import annotations
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from dotenv import load_dotenv

from src.db.mysql_client import MySQLClient
from src.db.repositories import InvoiceRepository, InvoiceItemRepository, EventRepository, RiskRepository

load_dotenv()

app = FastAPI(title="Invoice AI Audit System")
db = MySQLClient()
invoice_repo = InvoiceRepository(db)
item_repo = InvoiceItemRepository(db)
event_repo = EventRepository(db)
risk_repo = RiskRepository(db)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
jinja = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"])
)

UPLOAD_DIR = os.path.abspath(os.getenv("UPLOAD_DIR") or "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    invoices = invoice_repo.list_recent(200)
    tpl = jinja.get_template("index.html")
    return tpl.render(invoices=invoices)

@app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def invoice_detail(request: Request, invoice_id: int):
    inv = invoice_repo.get(invoice_id)
    if not inv:
        return HTMLResponse("Not found", status_code=404)
    items = item_repo.list_by_invoice(invoice_id)
    hits = risk_repo.list_hits(invoice_id)
    expls = db.fetch_all("SELECT * FROM explanations WHERE invoice_id=%s ORDER BY id DESC", (invoice_id,))
    approvals = db.fetch_all("SELECT * FROM approval_tasks WHERE invoice_id=%s ORDER BY id DESC", (invoice_id,))
    attaches = []
    if expls:
        attaches = db.fetch_all(
            """SELECT a.* FROM explanation_attachments a
                 JOIN explanations e ON e.id=a.explanation_id
                 WHERE e.invoice_id=%s ORDER BY a.id DESC""",
            (invoice_id,)
        )
    tpl = jinja.get_template("invoice_detail.html")
    return tpl.render(inv=inv, items=items, hits=hits, expls=expls, approvals=approvals, attaches=attaches)

@app.post("/invoices/{invoice_id}/explain")
async def submit_explanation(
    invoice_id: int,
    submitter: str = Form(default=""),
    explanation: str = Form(...),
    files: List[UploadFile] = File(default=[]),
):
    inv = invoice_repo.get(invoice_id)
    if not inv:
        return HTMLResponse("Not found", status_code=404)

    db.execute(
        "INSERT INTO explanations(invoice_id, submitter, explanation) VALUES(%s,%s,%s)",
        (invoice_id, submitter or None, explanation)
    )
    expl = db.fetch_one("SELECT id FROM explanations WHERE invoice_id=%s ORDER BY id DESC LIMIT 1", (invoice_id,))
    expl_id = int(expl["id"])

    saved = 0
    for f in files or []:
        if not f.filename:
            continue
        ext = os.path.splitext(f.filename)[1]
        token = uuid.uuid4().hex
        save_name = f"{invoice_id}_{expl_id}_{token}{ext}"
        save_path = os.path.join(UPLOAD_DIR, save_name)
        content = await f.read()
        with open(save_path, "wb") as out:
            out.write(content)
        db.execute(
            "INSERT INTO explanation_attachments(explanation_id, filename, content_type, file_path, size_bytes) VALUES(%s,%s,%s,%s,%s)",
            (expl_id, f.filename, f.content_type, save_path, len(content))
        )
        saved += 1

    # status update
    invoice_repo.update_invoice(invoice_id, {"status": "EXPLAINED"})
    event_repo.add(invoice_id, "EXPLAINED", "explanation submitted", {"submitter": submitter, "attachments": saved})

    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)

@app.get("/approvals", response_class=HTMLResponse)
def approvals_queue():
    rows = db.fetch_all("SELECT * FROM approval_tasks WHERE status='PENDING' ORDER BY id ASC LIMIT 200")
    tpl = jinja.get_template("approvals.html")
    return tpl.render(rows=rows)

@app.post("/approvals/{task_id}/decide")
def decide(task_id: int, decision: str = Form(...), approver: str = Form(default=""), note: str = Form(default="")):
    task = db.fetch_one("SELECT * FROM approval_tasks WHERE id=%s", (task_id,))
    if not task:
        return HTMLResponse("Not found", status_code=404)
    invoice_id = int(task["invoice_id"])
    decision = decision.upper().strip()
    if decision not in ("APPROVED", "REJECTED"):
        return HTMLResponse("Bad decision", status_code=400)

    db.execute(
        "UPDATE approval_tasks SET status=%s, approver=%s, decision_note=%s, decided_at=NOW() WHERE id=%s",
        (decision, approver or None, note or None, task_id)
    )
    invoice_repo.update_invoice(invoice_id, {"status": decision})
    event_repo.add(invoice_id, "APPROVAL_DECIDED", f"{decision}", {"approver": approver, "note": note})

    return RedirectResponse(url="/approvals", status_code=303)
