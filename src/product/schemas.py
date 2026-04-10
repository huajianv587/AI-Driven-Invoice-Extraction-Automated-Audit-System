from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


PROCESSING_STATUS_PENDING = "PENDING"
PROCESSING_STATUS_RUNNING = "RUNNING"
PROCESSING_STATUS_COMPLETED = "COMPLETED"
PROCESSING_STATUS_FAILED = "FAILED"

REVIEW_STATUS_PENDING = "PENDING"
REVIEW_STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
REVIEW_STATUS_APPROVED = "APPROVED"
REVIEW_STATUS_REJECTED = "REJECTED"


class LoginRequest(BaseModel):
    username: str
    password: str


class SessionUser(BaseModel):
    id: int
    username: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: SessionUser


class UploadResponse(BaseModel):
    file_id: int
    task_id: int
    trace_id: str
    processing_status: str


class ReviewRequest(BaseModel):
    invoice_id: int
    review_status: str
    note: str = ""


class TaskResponse(BaseModel):
    id: int
    invoice_file_id: int
    invoice_id: Optional[int] = None
    task_type: str
    processing_status: str
    retry_count: int
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    trace_id: str
    worker_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class InvoiceListItem(BaseModel):
    id: int
    processing_status: str
    review_status: str
    seller_name: Optional[str] = None
    invoice_number: Optional[str] = None
    purchase_order_no: Optional[str] = None
    total_amount_with_tax: Optional[float] = None
    risk_flag: int = 0
    confidence_overall: Optional[float] = None
    created_at: datetime


class InvoiceDetail(BaseModel):
    invoice: Dict[str, Any]
    items: List[Dict[str, Any]]
    events: List[Dict[str, Any]]
    extractions: List[Dict[str, Any]]
    reviews: List[Dict[str, Any]]
    notifications: List[Dict[str, Any]]
    file: Optional[Dict[str, Any]] = None


class DashboardSummary(BaseModel):
    total_invoices: int
    pending_tasks: int
    failed_tasks: int
    review_queue: int
    risk_invoices: int


class MetricsSummary(BaseModel):
    counters: Dict[str, Union[int, float]] = Field(default_factory=dict)
