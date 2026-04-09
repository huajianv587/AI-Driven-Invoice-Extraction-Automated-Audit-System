# Invoice Audit System

Local invoice ingestion pipeline with:

- RapidOCR for OCR extraction
- Optional Dify workflow for LLM field parsing
- MySQL 8 via Docker
- Mailpit for local SMTP inbox testing
- Optional Feishu Bitable sync
- SMTP anomaly alerts with work-order links

## What changed

The project is now standardized around `pymysql`.

- `mysql-connector-python` is no longer required
- Docker is used for MySQL and local Mailpit
- schema creation is idempotent and applied by project scripts
- local startup is driven by `start_local.bat`
- demo risk-control defaults are enabled for local testing

The previous `docker-compose.yml` was empty, so it could not bootstrap anything. It has been replaced with a working MySQL service definition.

## Quick start

1. Copy `.env.example` to `.env` if you want a fresh local config.
2. Put invoice images or PDFs into `./invoices`.
3. Run `start_local.bat`.

That script will:

1. Create `.venv` if needed
2. Install `requirements.txt`
3. Start MySQL with `docker compose`
4. Start Mailpit for local email capture
4. Apply `sql/*.sql`
5. Start the OCR service
6. Start the Streamlit dashboard
7. Run the batch ingestion entrypoint

## Demo mode

For a clean recording-ready flow, run:

```powershell
start_demo.bat
```

That script will:

1. Start MySQL and Mailpit
2. Apply schema and seed the demo purchase order
3. Clear previous demo invoices, review tasks, and email inbox messages
4. Start OCR and the Streamlit dashboard
5. Ingest only `invoices/invoice.jpg`
6. Leave you with one fresh risk email in Mailpit and one fresh invoice on the dashboard

Useful demo URLs after startup:

- Dashboard: `http://127.0.0.1:8517`
- Mailpit inbox: `http://127.0.0.1:8025`
- The risk email contains the anomaly work-order link

## Manual startup

### 1. Install dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Start MySQL and Mailpit

```powershell
docker compose up -d mysql mailpit
.\.venv\Scripts\python.exe scripts\apply_schema.py
```

### 3. Start OCR

```powershell
.\.venv\Scripts\python.exe ocr_server.py
```

### 4. Run ingestion

```powershell
.\.venv\Scripts\python.exe -m src.main
```

### 5. Run the dashboard

```powershell
start_ui.bat
```

### 6. Check alert emails

- Mailpit inbox UI: `http://127.0.0.1:8025`
- Streamlit anomaly form: `http://127.0.0.1:8517/?view=anomaly_form`

## Automated validation

Run the end-to-end self-check before recording:

```powershell
.\.venv\Scripts\python.exe scripts\demo_e2e_test.py
```

It validates:

- single-invoice ingestion
- amount-mismatch risk detection
- Mailpit email capture
- work-order link generation
- review writeback into MySQL
- audit events in `invoice_events`

## Configuration

Safe local defaults are provided in `.env.example`.

- Out of the box, the project can run in OCR-only mode
- Local demo mode defaults `PO_NO=PO-DEMO-001`, which links sample invoices to a seeded purchase order so amount mismatch alerts can trigger
- To enable LLM extraction, fill `DIFY_API_KEY` and `DIFY_WORKFLOW_ID`
- To enable Feishu sync, fill Feishu credentials and set `FEISHU_SYNC_MODE=inline` or `job`
- Local email alerts are routed to Mailpit by default
- The anomaly review link is designed for `http://127.0.0.1:8517/?view=anomaly_form`

## Schema

The schema lives in `sql/` and covers:

- `invoices`
- `invoice_items`
- `invoice_events`
- `purchase_orders`
- `invoice_feishu_sync`
- `invoice_review_tasks`

All SQL files use `CREATE TABLE IF NOT EXISTS`, so re-running `scripts/apply_schema.py` is safe.
