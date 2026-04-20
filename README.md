# Invoice Audit System

Flagship Web workspace for invoice intake, risk review, audit traceability, and connector recovery. The primary UI is `Next.js + FastAPI + MySQL`; Streamlit is retained only as a legacy comparison/debug surface.

发票审核系统现在默认使用新的 Web 栈：`Next.js` 前端、`FastAPI` 业务 API、`MySQL` 数据库，以及 OCR、Dify、Feishu、Mailpit 集成链路。Streamlit 仅保留为旧界面对照和调试入口。

## Architecture

```text
Browser
  -> Next.js frontend (/ and /app/*)
  -> FastAPI business API (/api/*)
  -> MySQL invoice / review / auth / audit tables
  -> OCR, Dify, Feishu, Mailpit integrations
```

Main surfaces:

- Public homepage: `http://127.0.0.1:3000/`
- Protected workspace: `http://127.0.0.1:3000/app/dashboard`
- FastAPI health: `http://127.0.0.1:8009/api/health`
- Mailpit inbox: `http://127.0.0.1:8025`

Default ports come from `.env`: `FRONTEND_PORT`, `API_PORT`, `MAILPIT_WEB_PORT`, `MYSQL_PORT`, and `UI_PORT` for legacy Streamlit.

## Quick Start

First-run demo with deterministic data:

```bat
start_demo.bat
```

`start_demo.bat` creates `.env` if needed, starts MySQL and Mailpit, applies schema, resets invoice demo tables, seeds deterministic Web data, starts OCR, FastAPI, and Next.js, then opens the Web app and Mailpit.

Bootstrap admin comes from `.env`:

```text
AUTH_BOOTSTRAP_ADMIN_EMAIL=admin@invoice-audit.local
AUTH_BOOTSTRAP_ADMIN_PASSWORD=ChangeMe123!
```

Recommended day-to-day one-click startup without clearing invoice data:

```bat
start_total.cmd
```

`start_total.cmd` starts the complete local Web stack, opens the Web app and Mailpit, and prints the resolved ports after startup.
Lines starting with `[wait]` are normal readiness checks while Docker, OCR, API, and Next.js come online.

Day-to-day local development without clearing invoice data:

```bat
start_local.bat
```

Shared lower-level launcher:

```bat
start_web_stack.bat local
start_web_stack.bat demo
```

The default `start.cmd` delegates to `start_total.cmd`.

## Web Regression

Daily UI regression runs against the real local stack: MySQL, OCR, FastAPI, and production-mode Next.js. It resets and seeds deterministic demo data before running.

```bat
cd frontend
npm run test:e2e
```

Useful variants:

```bat
npm run test:e2e:update
npm run test:e2e:headed
npm run test:e2e:audit
npm run test:lighthouse
```

The standard regression covers homepage, login, authenticated routing, Dashboard, Queue, Review Desk, Ops, DB-backed review writeback, desktop screenshot baselines, mobile homepage/login/dashboard baselines, and manual screenshots under `artifacts/ui-audit/latest/`.

## Deep Regression Safety

Deep regression is heavier and may call real OCR/Dify/Feishu/Mailpit paths. It is now strict opt-in and refuses to run unless all safety switches are explicit in the process environment; values sitting only in `.env` or `.env.example` are not enough.

```bat
cd frontend
set APP_ENV=local
set ALLOW_REAL_INTEGRATION_TESTS=1
set WEB_DEEP_RESET_DEMO_DB=1
set WEB_DEEP_CONFIRM=RESET_DEMO_DATA_AND_CALL_REAL_INTEGRATIONS
set WEB_DEEP_EXTERNAL_PREFIX=DEEP_TEST
npm run test:deep
```

Useful variants:

```bat
npm run test:deep:headed
npm run test:deep:update
```

The guard blocks production-like environments, non-local database hosts, non-local frontend origins, missing confirmation, and suspicious production markers in configured database or integration identifiers. Do not run deep regression against production data or a production Feishu base.

## CI/CD

GitHub Actions is split by cost and risk:

- PR/push: compile, unit tests, frontend build, and standard `npm run test:e2e`.
- Manual/nightly: strict deep regression and Lighthouse artifacts.

Reports are uploaded from `frontend/playwright-report*`, `frontend/test-results`, `artifacts/e2e-logs`, `artifacts/deep-regression`, and `artifacts/lighthouse`.

## Data And Integrations

Schema files live in `sql/` and are applied by:

```bat
.\.venv\Scripts\python.exe scripts\apply_schema.py
```

Deterministic Web demo data is seeded by:

```bat
.\.venv\Scripts\python.exe scripts\seed_web_demo_data.py
```

The stack keeps the existing integration model:

- OCR: local `ocr_server.py` on `OCR_BASE_URL`.
- Dify: optional extraction workflow when `DIFY_API_KEY` and `DIFY_WORKFLOW_ID` are set; set `DIFY_REQUIRED=True` to block fallback on missing/failed Dify extraction.
- Feishu: optional Bitable sync when Feishu credentials are set; set `FEISHU_SYNC_REQUIRED=True` only with `FEISHU_SYNC_MODE=inline` when sync must fail loud instead of degrading.
- Mailpit: local email preview on `http://127.0.0.1:8025`.
- SMTP alerts: set `EMAIL_ALERT_REQUIRED=True` when risky invoices must fail loud if alert delivery does not complete.

## Required Smoke

Use the dedicated required-mode smoke when Dify, Feishu, and SMTP must all succeed with real sandbox credentials:

```bat
set APP_ENV=local
set ALLOW_REAL_INTEGRATION_TESTS=1
set WEB_DEEP_RESET_DEMO_DB=1
set WEB_DEEP_CONFIRM=RESET_DEMO_DATA_AND_CALL_REAL_INTEGRATIONS
set DIFY_REQUIRED=True
set FEISHU_SYNC_REQUIRED=True
set FEISHU_SYNC_MODE=inline
set EMAIL_ALERT_REQUIRED=True
.\.venv\Scripts\python.exe scripts\required_mode_smoke.py
```

For the browser-backed wrapper:

```bat
cd frontend
set APP_ENV=local
set ALLOW_REAL_INTEGRATION_TESTS=1
set WEB_DEEP_RESET_DEMO_DB=1
set WEB_DEEP_CONFIRM=RESET_DEMO_DATA_AND_CALL_REAL_INTEGRATIONS
npm run test:required
```

`scripts/required_mode_smoke.py` expects real SMTP + IMAP sandbox credentials in `TEST_IMAP_*` so it can prove the alert arrived in the mailbox, not just that the app reported send success.

## Production Notes

Set these before exposing the app beyond localhost:

- `APP_ENV=production`
- `AUTH_JWT_SECRET` to a long random secret
- `AUTH_JWT_OLD_SECRETS` only during key rotation
- `AUTH_COOKIE_SECURE=True` behind HTTPS
- `AUTH_COOKIE_DOMAIN` when frontend/API are split across subdomains
- `FRONTEND_ORIGIN` to the exact public frontend origin
- `NEXT_PUBLIC_API_BASE_URL` only when the browser must call a different public API origin
- `DIFY_REQUIRED`, `FEISHU_SYNC_REQUIRED`, and `EMAIL_ALERT_REQUIRED` only for integrations that are truly mandatory in production
- `CONNECTOR_HEALTH_TTL_SEC` to control Ops connector cache freshness

Login attempts, RBAC denials, session revocations, review submissions, and Ops retries are written to security/audit tables. API responses include `X-Request-ID` and error payloads include `request_id` for log correlation.

## Legacy Streamlit

Streamlit is no longer the default UI. Treat it as a legacy, read-only comparison/debug surface during migration:

```bat
start_ui.bat
```

The old Streamlit-oriented regression script is also legacy:

```bat
.\.venv\Scripts\python.exe scripts\demo_e2e_test.py
```

Use Playwright in `frontend/` for the main Web product regression.

## Deployment

See [docs/deployment.md](docs/deployment.md) for production environment variables, reverse proxy notes, CORS/cookie settings, startup order, validation commands, deep-regression warnings, and troubleshooting.
