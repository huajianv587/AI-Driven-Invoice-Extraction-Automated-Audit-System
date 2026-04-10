from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Iterator, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.product.bootstrap import bootstrap_product_schema
from src.product.schemas import DashboardSummary, InvoiceDetail, InvoiceListItem, LoginRequest, LoginResponse, MetricsSummary, ReviewRequest, TaskResponse, UploadResponse
from src.product.services import AuthenticatedUser, ProductApplication, create_db, normalize_exception
from src.product.settings import ProductSettings, get_settings


bearer_scheme = HTTPBearer(auto_error=False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    db = create_db(settings)
    try:
        bootstrap_product_schema(db, settings)
    finally:
        db.close()
    yield


app = FastAPI(title="Invoice Audit Product API", version="1.0.0", lifespan=lifespan)


def get_settings_dep() -> ProductSettings:
    return get_settings()


def get_service(settings: ProductSettings = Depends(get_settings_dep)) -> Iterator[ProductApplication]:
    db = create_db(settings)
    try:
        yield ProductApplication(db, settings)
    finally:
        db.close()


def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    service: ProductApplication = Depends(get_service),
) -> AuthenticatedUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        return service.get_session_user(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@app.get("/healthz")
def healthz(settings: ProductSettings = Depends(get_settings_dep)) -> dict:
    return {"ok": True, "app_env": settings.app_env, "app_name": settings.app_name}


@app.post("/v1/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, service: ProductApplication = Depends(get_service)) -> dict:
    try:
        return service.authenticate(payload.username, payload.password)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@app.get("/v1/auth/me")
def me(user: AuthenticatedUser = Depends(current_user)) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post("/v1/invoices/upload", response_model=UploadResponse)
def upload_invoice(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> dict:
    try:
        task = service.upload_invoice(
            file_stream=file.file,
            filename=file.filename or "upload.bin",
            mime_type=file.content_type or "application/octet-stream",
            actor=user,
        )
        return {
            "file_id": int(task["invoice_file_id"]),
            "task_id": int(task["id"]),
            "trace_id": task["trace_id"],
            "processing_status": task["processing_status"],
        }
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        error_code, message = normalize_exception(exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{error_code}: {message}") from exc


@app.get("/v1/tasks", response_model=list[TaskResponse])
def list_tasks(
    status_filter: str = Query("", alias="status"),
    limit: int = Query(100, ge=1, le=500),
    _: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> list[dict]:
    return service.list_tasks(status=status_filter, limit=limit)


@app.get("/v1/tasks/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    _: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> dict:
    try:
        return service.get_task(task_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.post("/v1/tasks/{task_id}/retry", response_model=TaskResponse)
def retry_task(
    task_id: int,
    user: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> dict:
    try:
        return service.retry_task(task_id, user)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@app.get("/v1/invoices", response_model=list[InvoiceListItem])
def list_invoices(
    q: str = Query(""),
    review_status: str = Query(""),
    processing_status: str = Query(""),
    limit: int = Query(100, ge=1, le=500),
    _: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> list[dict]:
    return service.list_invoices(q=q, review_status=review_status, processing_status=processing_status, limit=limit)


@app.get("/v1/invoices/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(
    invoice_id: int,
    _: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> dict:
    try:
        return service.get_invoice_detail(invoice_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@app.get("/v1/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    _: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> dict:
    return service.dashboard_summary()


@app.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(service: ProductApplication = Depends(get_service)) -> dict:
    return {"counters": service.dashboard_summary()}


@app.post("/v1/reviews", response_model=InvoiceDetail)
def submit_review(
    payload: ReviewRequest,
    user: AuthenticatedUser = Depends(current_user),
    service: ProductApplication = Depends(get_service),
) -> dict:
    try:
        return service.submit_review(
            invoice_id=payload.invoice_id,
            review_status=payload.review_status,
            note=payload.note,
            actor=user,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
