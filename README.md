# Invoice AI Audit System (Plus)

A production-style invoice ingestion + risk audit pipeline:

- OCR → Dify LLM Workflow → Structured Schema (invoice_meta/seller/buyer/totals/staff/items/risk)
- Reliability: timeouts/504/invalid LLM output → **AI→Rule fallback** (OCR-only ingest) + full audit trail
- Standardization: nested JSON → flatten mapping → MySQL + optional Feishu Bitable sync
- Idempotency: SHA256 fingerprint for dedup
- Risk rules: AI + heuristic checks (tax/total consistency, PO expected vs actual, etc.)
- Closed loop: risk email → explanation form (FastAPI) → attachments → approval workflow → sync back to MySQL/Feishu

---

## 1) Open in PyCharm

Yes — **open the project root folder** (the folder that contains `src/`, `requirements.txt`, `README.md`).

Recommended interpreter: a fresh venv.

---

## 2) Install

```bash
pip install -r requirements.txt
```

---

## 3) Configure

```bash
cp .env.example .env
```

Edit `.env` for your MySQL / Dify / (optional) Feishu / (optional) email.

---

## 4) Create DB tables (migration)

```bash
python -m src.cli.migrate
```

This will create all required tables in `MYSQL_DB`.

---

## 5) Ingest invoices (batch)

Put images/PDFs under `./invoices` (create it if not exists), then run:

```bash
python -m src.cli.ingest --input ./invoices
```

Behavior:
- If Dify is configured, it uses OCR text as context and requests structured JSON from Dify workflow.
- If Dify fails (timeout/504/invalid JSON), it automatically falls back to OCR-only ingestion.
- Dedup is enforced by `unique_hash`.

---

## 6) Run the Explanation + Approval web app

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

Open:
- Invoice list: `http://127.0.0.1:8000/`
- Invoice detail + explanation form: `http://127.0.0.1:8000/invoices/{invoice_id}`
- Approvals queue: `http://127.0.0.1:8000/approvals`

Attachments are saved under `./uploads/` by default and recorded in DB.

---

## 7) Sync MySQL → Feishu (job mode)

```bash
python -m src.jobs.feishu_sync_job --limit 200
```

- Uses `FEISHU_UNIQUE_FIELD` (default `unique_hash`) to **upsert** (search then update/add) to avoid duplicates.
- Writes sync status to `invoice_feishu_sync`.

---

## Notes

### Purchase Order (PO) integration
- Table: `purchase_orders`
- If the extracted invoice contains a `purchase_order_no`, the system will look up PO to get `expected_amount`.
- You can import/seed PO data: see `src/cli/seed_po.py`.

### Status workflow
- `invoices.status`:
  - `INGESTED` → `RISK_REVIEW` (if risk) → `EXPLAINED` (after form submit) → `APPROVED` / `REJECTED`
- Approval actions are recorded in `approval_tasks` + `invoice_events`.

