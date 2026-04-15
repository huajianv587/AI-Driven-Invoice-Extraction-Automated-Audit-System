# Deployment Guide

This guide documents the Web-first deployment path for the Invoice Audit System: Next.js frontend, FastAPI API, MySQL, OCR, and optional Dify/Feishu/Mailpit integrations.

## Required Environment

Create `.env` from `.env.example` and set production-safe values before exposing the app outside localhost.

Required for the Web stack:

```text
APP_ENV=production
MYSQL_HOST=
MYSQL_PORT=
MYSQL_USER=
MYSQL_PASSWORD=
MYSQL_DB=
MYSQL_ROOT_PASSWORD=

OCR_BASE_URL=
API_PORT=8009
FRONTEND_PORT=3000
FRONTEND_ORIGIN=https://your-domain.example
CONNECTOR_HEALTH_TTL_SEC=60

AUTH_JWT_SECRET=
AUTH_JWT_OLD_SECRETS=
AUTH_ACCESS_TTL_SEC=900
AUTH_REFRESH_TTL_DAYS=14
AUTH_COOKIE_NAME=invoice_refresh_token
AUTH_COOKIE_SECURE=True
AUTH_LOGIN_RATE_LIMIT_MAX=5
AUTH_LOGIN_RATE_LIMIT_WINDOW_SEC=900
AUTH_BOOTSTRAP_ADMIN_NAME=
AUTH_BOOTSTRAP_ADMIN_EMAIL=
AUTH_BOOTSTRAP_ADMIN_PASSWORD=
```

Production requirements:

- Replace `AUTH_JWT_SECRET=change-me-local-dev-secret` with a long random secret.
- Use `AUTH_JWT_OLD_SECRETS` only during key rotation. Old secrets are decode-only and should be removed after active sessions expire.
- Replace `AUTH_BOOTSTRAP_ADMIN_PASSWORD=ChangeMe123!` before first production start.
- Set `FRONTEND_ORIGIN` to the exact public frontend origin, including scheme and port if any.
- Set `AUTH_COOKIE_SECURE=True` when serving the API over HTTPS.
- Keep Dify and Feishu credentials empty if those integrations are intentionally disabled.
- Keep `ALLOW_REAL_INTEGRATION_TESTS=0` and `WEB_DEEP_RESET_DEMO_DB=0` in production.

## Startup Order

Recommended local/self-hosted order:

```bat
docker compose up -d mysql mailpit
.\.venv\Scripts\python.exe scripts\apply_schema.py
.\.venv\Scripts\python.exe scripts\write_frontend_env.py
start_ocr.bat
start_api.bat
start_frontend.bat
```

For a demo reset:

```bat
start_demo.bat
```

For a local run that keeps data:

```bat
start_local.bat
```

## Frontend Build

The frontend reads `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_REFRESH_COOKIE_NAME`, and `NEXT_PUBLIC_BOOTSTRAP_ADMIN_EMAIL` from `frontend/.env.local`.

Regenerate it whenever root `.env` changes:

```bat
.\.venv\Scripts\python.exe scripts\write_frontend_env.py
```

Production build:

```bat
cd frontend
npm install
npm run build
npm run start -- --hostname 127.0.0.1 --port 3000
```

## API And Auth

FastAPI exposes:

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/auth/sessions
DELETE /api/auth/sessions/{id}
GET  /api/dashboard/summary
GET  /api/dashboard/activity
GET  /api/invoices
GET  /api/invoices/{id}
POST /api/invoices/{id}/review
GET  /api/ops/connectors
GET  /api/ops/connectors?refresh=true
GET  /api/ops/feishu-sync
GET  /api/ops/feishu-sync/failures
POST /api/ops/feishu-sync/retry
```

Session model:

- Login returns a short-lived access token.
- The refresh token is stored as an httpOnly cookie named by `AUTH_COOKIE_NAME`.
- Refresh sessions include device label, user agent, IP, last seen time, expiry, and revoke status.
- `AUTH_COOKIE_SECURE=True` should be used behind HTTPS. Keep it `False` only for localhost HTTP.
- `/app/*` pages are protected by Next.js middleware that checks the refresh cookie.
- API role checks enforce `admin`, `reviewer`, and `ops`.
- Login failures are rate-limited by email and IP. Responses remain generic to avoid account enumeration.
- Security events record login success/failure, logout, refresh, RBAC denial, review submit, session revoke, and Ops retry.
- Review state transitions are centralized in the API service layer. Reviewers cannot reopen terminal approved/rejected invoices; admins can reopen with an audited reason.

## Observability

Every API response includes:

```text
X-Request-ID: <request-id>
```

Error payloads include the same `request_id`, and API logs are emitted as JSON with route, status code, latency, and request id. Integration health checks include `cached_at`, `latency_ms`, and `stale`.

Dashboard reads connector summary from the last cached snapshot so slow Dify/Feishu checks do not block the main workspace. Use Ops Center or `GET /api/ops/connectors?refresh=true` for live checks.

## Reverse Proxy

Typical routing:

```text
https://invoice.example.com/      -> Next.js frontend on 127.0.0.1:3000
https://invoice.example.com/api/* -> FastAPI API on 127.0.0.1:8009
```

If the API is served on a different origin, set:

```text
FRONTEND_ORIGIN=https://invoice.example.com
NEXT_PUBLIC_API_BASE_URL=https://api.invoice.example.com
```

Then ensure CORS allows the frontend origin and cookies are sent with `SameSite=Lax` or the policy required by your domain layout.

## Validation

Backend smoke:

```bat
.\.venv\Scripts\python.exe -m compileall api_server.py ocr_server.py src scripts tests
```

Frontend build:

```bat
cd frontend
npm run build
```

Real Web regression:

```bat
cd frontend
npm run test:e2e
```

Deep Web regression for non-production demo/test environments:

```bat
cd frontend
set APP_ENV=local
set ALLOW_REAL_INTEGRATION_TESTS=1
set WEB_DEEP_RESET_DEMO_DB=1
set WEB_DEEP_CONFIRM=RESET_DEMO_DATA_AND_CALL_REAL_INTEGRATIONS
set WEB_DEEP_EXTERNAL_PREFIX=DEEP_TEST
npm run test:deep
```

Deep mode resets demo invoice tables, seeds `admin`/`reviewer`/`ops`/`inactive` users, runs ingestion closed-loop checks, and may call configured Dify/Feishu integrations. It refuses to run unless `APP_ENV=local` and the three confirmation variables are explicitly set in the process environment. Never run deep regression against production data or a production Feishu base.

Update committed screenshot baselines after intentional UI changes:

```bat
cd frontend
npm run test:e2e:update
```

Manual UI screenshots:

```bat
cd frontend
npm run test:e2e:audit
```

Lighthouse audit:

```bat
cd frontend
npm run test:lighthouse
```

Reports are written under ignored `artifacts/` folders.

## Troubleshooting

- `Session is not active`: confirm the API is running, `AUTH_COOKIE_NAME` matches frontend `.env.local`, and the browser can receive cookies from the API origin.
- `Invalid email or password`: confirm bootstrap admin values in `.env`, then restart the API so the bootstrap account can be created.
- Frontend calls the wrong API port: rerun `scripts/write_frontend_env.py` and restart Next.js.
- Playwright cannot start the stack: ensure Docker Desktop is running, `.venv` exists, Python dependencies are installed, and Node dependencies exist under `frontend/node_modules`.
- Deep regression fails before Playwright opens: inspect `artifacts/deep-regression/latest.json` and `artifacts/e2e-logs/`; the ingestion loop likely failed OCR, SMTP/Mailpit, Dify fallback, or duplicate-detection checks.
- Deep regression is blocked by safety guard: confirm `APP_ENV=local`, localhost MySQL/frontend origins, `ALLOW_REAL_INTEGRATION_TESTS=1`, `WEB_DEEP_RESET_DEMO_DB=1`, and the exact `WEB_DEEP_CONFIRM` value are explicitly set before launching the command.
- Ops connector statuses show `Not configured`: fill Dify/Feishu/SMTP settings only if those integrations should be live.
- Lighthouse dashboard audit fails at login: verify `AUTH_BOOTSTRAP_ADMIN_EMAIL` and `AUTH_BOOTSTRAP_ADMIN_PASSWORD` in `.env`.
