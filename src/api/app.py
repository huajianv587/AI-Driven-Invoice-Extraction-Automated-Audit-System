from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from src.api.dependencies import get_cfg, get_current_or_public_demo_user, get_current_user, get_db, require_roles
from src.api.observability import RequestIdMiddleware
from src.api.schemas import (
    AuthLoginRequest,
    AuthSessionResponse,
    AuthSessionDevice,
    ConnectorHealth,
    ControlRoomSummary,
    DashboardSummary,
    DailyActivityPoint,
    FeishuFailureItem,
    FeishuReplayResult,
    FeishuRetryRequest,
    FeishuSyncStatusResponse,
    IntakeUploadsResponse,
    InvoiceDetail,
    InvoiceListResponse,
    ReviewResponse,
    ReviewSubmission,
    UploadInvoiceResponse,
)
from src.api.services import (
    InvalidStateTransition,
    RetryAlreadyRunning,
    authenticate_user,
    build_control_room_summary,
    build_dashboard_activity,
    build_dashboard_summary,
    build_intake_summary,
    build_ops_sync_summary,
    create_refresh_session,
    ensure_bootstrap_admin,
    fetch_invoice_detail,
    fetch_recent_intake_uploads,
    fetch_recent_failed_feishu_syncs,
    get_user_from_refresh_token,
    integration_status,
    issue_auth_payload,
    list_refresh_sessions,
    log_security_event,
    login_is_rate_limited,
    list_invoices,
    record_login_attempt,
    retry_feishu_sync,
    revoke_refresh_session_by_id,
    revoke_refresh_token,
    create_intake_upload_log,
    stage_intake_upload,
    update_invoice_review,
)
from src.config import load_flat_config
from src.db.mysql_client import MySQLClient
from src.runtime_preflight import build_readiness_report, ensure_runtime_preflight


def _cors_origins(cfg: dict) -> list[str]:
    frontend_origin = str(cfg.get("FRONTEND_ORIGIN") or "http://127.0.0.1:3000").strip()
    origins = [frontend_origin]
    app_env = str(cfg.get("APP_ENV") or "local").strip().lower()
    if app_env != "production":
        origins.extend(["http://127.0.0.1:3000", "http://localhost:3000"])
    deduped: list[str] = []
    for origin in origins:
        normalized = origin.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _require_ops_reader(user: dict) -> None:
    if user.get("is_public_demo"):
        return
    if str(user.get("role") or "").lower() in {"admin", "ops"}:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ops read access requires admin or ops role.")


MAX_INTAKE_UPLOAD_BYTES = 15 * 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_flat_config()
    ensure_runtime_preflight(cfg, context="FastAPI API")
    db = MySQLClient(
        host=cfg["mysql_host"],
        port=int(cfg["mysql_port"]),
        user=cfg["mysql_user"],
        password=cfg["mysql_password"],
        db=cfg["mysql_db"],
        connect_timeout=10,
        autocommit=True,
    )
    try:
        ensure_bootstrap_admin(db, cfg)
    finally:
        db.close()
    yield


app = FastAPI(title="Invoice Audit Web API", version="1.0.0", lifespan=lifespan)
app.add_middleware(RequestIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(load_flat_config()),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail if isinstance(exc.detail, str) else "Request failed.",
            "request_id": getattr(request.state, "request_id", ""),
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Validation failed.",
            "errors": exc.errors(),
            "request_id": getattr(request.state, "request_id", ""),
        },
    )


@app.get("/api/health")
def health() -> dict:
    cfg = load_flat_config()
    return {"ok": True, "app_env": str(cfg.get("APP_ENV") or "local").lower()}


@app.get("/api/readiness")
def readiness(
    cfg: dict = Depends(get_cfg),
    db: MySQLClient = Depends(get_db),
) -> JSONResponse:
    report = build_readiness_report(db, cfg)
    return JSONResponse(
        status_code=status.HTTP_200_OK if report["ok"] else status.HTTP_503_SERVICE_UNAVAILABLE,
        content=report,
    )


def _set_refresh_cookie(response: Response, cfg: dict, token: str) -> None:
    cookie_domain = str(cfg.get("AUTH_COOKIE_DOMAIN") or "").strip() or None
    response.set_cookie(
        key=str(cfg["AUTH_COOKIE_NAME"]),
        value=token,
        httponly=True,
        secure=bool(cfg.get("AUTH_COOKIE_SECURE")),
        samesite="lax",
        max_age=int(cfg["AUTH_REFRESH_TTL_DAYS"]) * 24 * 60 * 60,
        path="/",
        domain=cookie_domain,
    )


def _clear_refresh_cookie(response: Response, cfg: dict) -> None:
    cookie_domain = str(cfg.get("AUTH_COOKIE_DOMAIN") or "").strip() or None
    response.delete_cookie(key=str(cfg["AUTH_COOKIE_NAME"]), path="/", samesite="lax", domain=cookie_domain)


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    return forwarded_for or (request.client.host if request.client else "")


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


@app.post("/api/auth/login", response_model=AuthSessionResponse)
def login(
    payload: AuthLoginRequest,
    request: Request,
    response: Response,
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    email = payload.email.strip().lower()
    ip_address = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    request_id = _request_id(request)
    if login_is_rate_limited(
        db,
        email=email,
        ip_address=ip_address,
        max_attempts=int(cfg.get("AUTH_LOGIN_RATE_LIMIT_MAX") or 5),
        window_sec=int(cfg.get("AUTH_LOGIN_RATE_LIMIT_WINDOW_SEC") or 900),
    ):
        record_login_attempt(
            db,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
            failure_reason="rate_limited",
            request_id=request_id,
        )
        log_security_event(
            db,
            event_type="auth.login_rate_limited",
            email=email,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            outcome="denied",
        )
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts. Try again later.")

    user = authenticate_user(db, payload.email, payload.password)
    if not user:
        record_login_attempt(
            db,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False,
            failure_reason="invalid_credentials",
            request_id=request_id,
        )
        log_security_event(
            db,
            event_type="auth.login_failed",
            email=email,
            request_id=request_id,
            ip_address=ip_address,
            user_agent=user_agent,
            outcome="denied",
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    record_login_attempt(
        db,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True,
        request_id=request_id,
    )
    refresh_token = create_refresh_session(
        db,
        user_id=int(user["id"]),
        ttl_days=int(cfg["AUTH_REFRESH_TTL_DAYS"]),
        user_agent=request.headers.get("user-agent", ""),
        ip_address=ip_address,
    )
    log_security_event(
        db,
        event_type="auth.login_success",
        user_id=int(user["id"]),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or ""),
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        outcome="success",
    )
    _set_refresh_cookie(response, cfg, refresh_token)
    return issue_auth_payload(cfg, user)


@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    token = request.cookies.get(str(cfg["AUTH_COOKIE_NAME"])) or ""
    user = get_user_from_refresh_token(db, token)
    revoke_refresh_token(db, token, reason="logout")
    if user:
        log_security_event(
            db,
            event_type="auth.logout",
            user_id=int(user["id"]),
            email=str(user.get("email") or ""),
            role=str(user.get("role") or ""),
            request_id=_request_id(request),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            outcome="success",
        )
    _clear_refresh_cookie(response, cfg)
    return {"ok": True}


@app.get("/api/auth/me", response_model=AuthSessionResponse)
def me(
    request: Request,
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    refresh_token = request.cookies.get(str(cfg["AUTH_COOKIE_NAME"])) or ""
    user = get_user_from_refresh_token(db, refresh_token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is not active.")
    log_security_event(
        db,
        event_type="auth.refresh",
        user_id=int(user["id"]),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or ""),
        request_id=_request_id(request),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        outcome="success",
    )
    return issue_auth_payload(cfg, user)


@app.get("/api/auth/sessions", response_model=list[AuthSessionDevice])
def sessions(
    request: Request,
    user: dict = Depends(get_current_user),
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    rows = list_refresh_sessions(db, int(user["id"]))
    refresh_token = request.cookies.get(str(cfg["AUTH_COOKIE_NAME"])) or ""
    active_user = get_user_from_refresh_token(db, refresh_token)
    active_session_id = int((active_user or {}).get("refresh_token_id") or 0)
    for row in rows:
        row["is_current"] = active_session_id and int(row["id"]) == active_session_id
    return rows


@app.delete("/api/auth/sessions/{session_id}")
def revoke_session(
    session_id: int,
    request: Request,
    user: dict = Depends(get_current_user),
    db: MySQLClient = Depends(get_db),
):
    changed = revoke_refresh_session_by_id(db, user_id=int(user["id"]), session_id=session_id)
    log_security_event(
        db,
        event_type="auth.session_revoked",
        user_id=int(user["id"]),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or ""),
        request_id=_request_id(request),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        outcome="success" if changed else "noop",
        metadata={"session_id": session_id},
    )
    return {"ok": bool(changed), "session_id": session_id}


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    return build_dashboard_summary(db, cfg)


@app.get("/api/dashboard/activity", response_model=list[DailyActivityPoint])
def dashboard_activity(
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
):
    return build_dashboard_activity(db)


@app.get("/api/invoices", response_model=InvoiceListResponse)
def invoices(
    search: str = Query(default=""),
    status_filter: str = Query(default="All", alias="status"),
    risk_only: bool = Query(default=False),
    sort: str = Query(default="newest"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
):
    return list_invoices(
        db,
        search=search,
        status=status_filter,
        risk_only=risk_only,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@app.get("/api/invoices/{invoice_id}", response_model=InvoiceDetail)
def invoice_detail(
    invoice_id: int,
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
):
    detail = fetch_invoice_detail(db, invoice_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    return detail


@app.post("/api/invoices/{invoice_id}/review", response_model=ReviewResponse)
def submit_review(
    invoice_id: int,
    payload: ReviewSubmission,
    request: Request,
    user: dict = Depends(require_roles("admin", "reviewer")),
    db: MySQLClient = Depends(get_db),
):
    detail = fetch_invoice_detail(db, invoice_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found.")
    invoice = detail["invoice"]
    try:
        result = update_invoice_review(
            db,
            invoice_id=invoice_id,
            purchase_order_no=str(invoice.get("purchase_order_no") or ""),
            unique_hash=str(invoice.get("unique_hash") or ""),
            handler_user=payload.handler_user.strip(),
            handler_reason=payload.handling_note.strip(),
            invoice_status=payload.review_result,
            actor_user=user,
            request_id=_request_id(request),
            idempotency_key=request.headers.get("idempotency-key", ""),
        )
    except InvalidStateTransition as exc:
        log_security_event(
            db,
            event_type="review.transition_denied",
            user_id=int(user["id"]),
            email=str(user.get("email") or ""),
            role=str(user.get("role") or ""),
            request_id=_request_id(request),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            outcome="denied",
            metadata={"invoice_id": invoice_id, "target_status": payload.review_result, "reason": str(exc)},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    log_security_event(
        db,
        event_type="review.submitted",
        user_id=int(user["id"]),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or ""),
        request_id=_request_id(request),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        outcome="success" if result.changed else "idempotent",
        metadata={"invoice_id": invoice_id, "target_status": payload.review_result},
    )
    return {
        "ok": True,
        "invoice_id": invoice_id,
        "invoice_status": result.invoice_status,
        "changed": result.changed,
        "message": result.message,
    }


@app.get("/api/ops/connectors", response_model=list[ConnectorHealth])
def ops_connectors(
    refresh: bool = Query(default=False),
    user: dict = Depends(get_current_or_public_demo_user),
    cfg: dict = Depends(get_cfg),
):
    _require_ops_reader(user)
    if user.get("is_public_demo") and refresh:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to run live connector checks.")
    return integration_status(cfg, force_refresh=refresh)


@app.get("/api/ops/feishu-sync", response_model=FeishuSyncStatusResponse)
def ops_feishu_sync(
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    _require_ops_reader(user)
    return build_ops_sync_summary(db, cfg)


@app.get("/api/ops/control-room", response_model=ControlRoomSummary)
def ops_control_room(
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    _require_ops_reader(user)
    return build_control_room_summary(db, cfg)


@app.get("/api/ops/intake/uploads", response_model=IntakeUploadsResponse)
def ops_intake_uploads(
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
):
    _require_ops_reader(user)
    return fetch_recent_intake_uploads(db, limit=limit, offset=offset)


@app.post("/api/ops/intake/upload", response_model=UploadInvoiceResponse, status_code=status.HTTP_201_CREATED)
async def ops_intake_upload(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(require_roles("admin", "ops")),
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    file_name = str(file.filename or "").strip()
    if not file_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose an invoice file to upload.")
    content = await file.read(MAX_INTAKE_UPLOAD_BYTES + 1)
    await file.close()
    if len(content) > MAX_INTAKE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Upload exceeds the 15 MB intake limit.",
        )
    staged_file = None
    try:
        staged_file = stage_intake_upload(cfg, original_name=file_name, content=content)
        upload_item = create_intake_upload_log(db, original_name=file_name, staged_file=staged_file, user=user)
        intake_summary = build_intake_summary(cfg, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        if staged_file and staged_file.get("path"):
            try:
                Path(str(staged_file["path"])).unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except OSError as exc:
        if staged_file and staged_file.get("path"):
            try:
                Path(str(staged_file["path"])).unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload staging failed: {exc}")
    except Exception as exc:
        if staged_file and staged_file.get("path"):
            try:
                Path(str(staged_file["path"])).unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload logging failed: {exc}")

    log_security_event(
        db,
        event_type="ops.intake_upload",
        user_id=int(user["id"]),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or ""),
        request_id=_request_id(request),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        outcome="success",
        metadata={
            "original_name": file_name,
            "staged_name": staged_file["name"],
            "size_bytes": staged_file["size_bytes"],
            "upload_id": upload_item["id"],
        },
    )
    return {
        "ok": True,
        "message": "Invoice staged in the intake folder. The ingestion worker will pick it up on the next pass.",
        "upload": upload_item,
        "intake": intake_summary,
    }


@app.get("/api/ops/feishu-sync/failures", response_model=list[FeishuFailureItem])
def ops_feishu_sync_failures(
    limit: int = Query(default=12, ge=1, le=100),
    user: dict = Depends(get_current_or_public_demo_user),
    db: MySQLClient = Depends(get_db),
):
    _require_ops_reader(user)
    return fetch_recent_failed_feishu_syncs(db, limit=limit)


@app.post("/api/ops/feishu-sync/retry", response_model=FeishuReplayResult)
def ops_feishu_sync_retry(
    payload: FeishuRetryRequest,
    request: Request,
    user: dict = Depends(require_roles("admin", "ops")),
    db: MySQLClient = Depends(get_db),
    cfg: dict = Depends(get_cfg),
):
    try:
        result = retry_feishu_sync(
            db,
            cfg,
            mode=payload.mode,
            limit=payload.limit,
            invoice_ids=payload.invoice_ids,
            request_id=_request_id(request),
        )
    except RetryAlreadyRunning as exc:
        log_security_event(
            db,
            event_type="ops.feishu_retry_conflict",
            user_id=int(user["id"]),
            email=str(user.get("email") or ""),
            role=str(user.get("role") or ""),
            request_id=_request_id(request),
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
            outcome="conflict",
            metadata={"mode": payload.mode, "limit": payload.limit, "invoice_ids": payload.invoice_ids},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    log_security_event(
        db,
        event_type="ops.feishu_retry",
        user_id=int(user["id"]),
        email=str(user.get("email") or ""),
        role=str(user.get("role") or ""),
        request_id=_request_id(request),
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        outcome="success" if result.get("fail_count", 0) == 0 else "partial",
        metadata={"mode": payload.mode, "limit": payload.limit, "invoice_ids": payload.invoice_ids, **result},
    )
    return result
