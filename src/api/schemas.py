from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


UserRole = Literal["admin", "reviewer", "ops"]


class AuthUser(BaseModel):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_public_demo: bool = False


class AuthLoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)


class AuthSessionResponse(BaseModel):
    user: AuthUser
    access_token: str
    expires_at: int


class AuthSessionDevice(BaseModel):
    id: int
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    device_label: str
    last_seen_at: Optional[str] = None
    expires_at: Optional[str] = None
    revoked_at: Optional[str] = None
    created_at: Optional[str] = None
    is_current: bool = False


class SecurityEvent(BaseModel):
    id: int
    event_type: str
    user_id: Optional[int] = None
    email: Optional[str] = None
    role: Optional[str] = None
    request_id: Optional[str] = None
    ip_address: Optional[str] = None
    outcome: str
    metadata: Any = None
    created_at: Optional[str] = None


class DashboardTotals(BaseModel):
    total_count: int
    risk_count: int
    pending_count: int
    today_count: int
    total_amount: float
    risk_amount: float


class DashboardRatios(BaseModel):
    risk_ratio: float
    reviewed_ratio: float
    sync_ratio: float
    alert_ratio: float


class ConnectorSnapshot(BaseModel):
    ready_count: int
    total_count: int
    blocked_count: int


class FeishuSyncSnapshot(BaseModel):
    pending_count: int
    failed_count: int
    synced_count: int


class InvoiceListItem(BaseModel):
    id: int
    invoice_date: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_name: Optional[str] = None
    invoice_code: Optional[str] = None
    invoice_number: Optional[str] = None
    purchase_order_no: Optional[str] = None
    total_amount_with_tax: float = 0.0
    expected_amount: float = 0.0
    amount_diff: float = 0.0
    risk_flag: bool = False
    risk_reason_summary: str = "-"
    invoice_status: Optional[str] = None
    notify_personal_status: Optional[str] = None
    notify_leader_status: Optional[str] = None
    created_at: Optional[str] = None
    sync_label: str
    sync_tone: str
    sync_error: Optional[str] = None


class DashboardSummary(BaseModel):
    totals: DashboardTotals
    ratios: DashboardRatios
    connectors: ConnectorSnapshot
    feishu_sync: FeishuSyncSnapshot
    top_risk: List[InvoiceListItem]
    recent_queue: List[InvoiceListItem]


class DailyActivityPoint(BaseModel):
    activity_date: Optional[str] = None
    day_label: str
    total_count: int
    risk_count: int


class InvoiceListResponse(BaseModel):
    items: List[InvoiceListItem]
    total_count: int
    matched_risk_count: int
    matched_pending_count: int
    matched_total_amount: float


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[int] = None
    item_name: Optional[str] = None
    item_spec: Optional[str] = None
    item_unit: Optional[str] = None
    item_quantity: Optional[float] = None
    item_unit_price: Optional[float] = None
    item_amount: Optional[float] = None
    tax_rate: Any = None
    tax_amount: Optional[float] = None


class InvoiceEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    event_type: str
    event_status: str
    payload: Any = None
    created_at: Optional[str] = None


class ReviewTask(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    review_result: str
    handler_user: Optional[str] = None
    handling_note: Optional[str] = None
    source_channel: Optional[str] = None
    created_at: Optional[str] = None


class InvoiceStateTransition(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    from_status: Optional[str] = None
    to_status: str
    actor_email: Optional[str] = None
    actor_role: Optional[str] = None
    request_id: Optional[str] = None
    reason: Optional[str] = None
    created_at: Optional[str] = None


class InvoiceSyncState(BaseModel):
    model_config = ConfigDict(extra="allow")

    feishu_record_id: Optional[str] = None
    synced_at: Optional[str] = None
    sync_error: Optional[str] = None
    sync_label: str
    sync_tone: str


class PurchaseOrderSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    purchase_no: Optional[str] = None
    supplier_name: Optional[str] = None
    purchaser_name: Optional[str] = None
    purchaser_email: Optional[str] = None
    buyer_email: Optional[str] = None
    leader_email: Optional[str] = None
    total_amount_with_tax: Optional[float] = None
    expected_amount: Optional[float] = None
    purchase_order_date: Optional[str] = None
    status: Optional[str] = None


class InvoiceRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    invoice_status: Optional[str] = None
    seller_name: Optional[str] = None
    buyer_name: Optional[str] = None
    purchase_order_no: Optional[str] = None
    invoice_code: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    total_amount_with_tax: float = 0.0
    expected_amount: float = 0.0
    amount_diff: float = 0.0
    risk_flag: bool = False
    risk_reason: Any = None
    risk_reason_summary: str = "-"
    handler_user: Optional[str] = None
    handler_reason: Optional[str] = None
    handled_at: Optional[str] = None
    notify_personal_status: Optional[str] = None
    notify_leader_status: Optional[str] = None
    unique_hash: Optional[str] = None
    source_file_path: Optional[str] = None
    raw_ocr_json: Any = None
    llm_json: Any = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class InvoiceDetail(BaseModel):
    invoice: InvoiceRecord
    items: List[InvoiceLineItem]
    events: List[InvoiceEvent]
    review_tasks: List[ReviewTask]
    state_transitions: List[InvoiceStateTransition] = Field(default_factory=list)
    sync: InvoiceSyncState
    purchase_order: Optional[PurchaseOrderSummary] = None


class ReviewSubmission(BaseModel):
    handler_user: str = Field(min_length=2, max_length=64)
    handling_note: str = Field(min_length=8, max_length=5000)
    review_result: Literal["Pending", "Approved", "Rejected", "NeedsReview"]


class ReviewResponse(BaseModel):
    ok: bool
    invoice_id: int
    invoice_status: str
    changed: bool
    message: Optional[str] = None


class ConnectorHealth(BaseModel):
    name: str
    status: str
    message: str
    detail: Optional[str] = None
    cached_at: Optional[str] = None
    latency_ms: Optional[float] = None
    stale: bool = False


class FeishuSyncStatusResponse(BaseModel):
    summary: FeishuSyncSnapshot
    retry_worker_enabled: bool
    retry_interval_sec: int
    retry_mode: str
    retry_batch_limit: int


class ReadinessCheck(BaseModel):
    ok: bool
    detail: str
    latest_file: Optional[str] = None
    applied_at: Optional[str] = None


class ReadinessReport(BaseModel):
    ok: bool
    app_env: str
    checks: dict[str, ReadinessCheck]


class IntakeFile(BaseModel):
    name: str
    extension: str
    size_bytes: int
    modified_at: Optional[str] = None


class IntakePipelineCounts(BaseModel):
    queued: int = 0
    processing: int = 0
    ingested: int = 0
    failed: int = 0
    total: int = 0


class IntakeUploadItem(BaseModel):
    id: int
    original_name: str
    staged_name: str
    extension: str
    size_bytes: int
    status: Literal["queued", "processing", "ingested", "failed"]
    error_message: Optional[str] = None
    invoice_id: Optional[int] = None
    created_by: Optional[int] = None
    created_by_email: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class IntakeSummary(BaseModel):
    directory: str
    exists: bool
    writable: bool
    upload_enabled: bool
    total_files: int
    total_bytes: int
    accepted_extensions: List[str] = Field(default_factory=list)
    extension_breakdown: dict[str, int] = Field(default_factory=dict)
    recent_files: List[IntakeFile] = Field(default_factory=list)
    pipeline_counts: IntakePipelineCounts = Field(default_factory=IntakePipelineCounts)
    recent_uploads: List[IntakeUploadItem] = Field(default_factory=list)


class IntakeUploadsResponse(BaseModel):
    items: List[IntakeUploadItem] = Field(default_factory=list)
    total_count: int = 0
    limit: int = 0
    offset: int = 0


class AlertQueueItem(BaseModel):
    invoice_id: int
    seller_name: Optional[str] = None
    purchase_order_no: Optional[str] = None
    risk_reason_summary: str = "-"
    amount_diff: float = 0.0
    notify_personal_status: Optional[str] = None
    notify_leader_status: Optional[str] = None
    alert_at: Optional[str] = None


class AlertSummary(BaseModel):
    risk_count: int
    personal_sent_count: int
    leader_sent_count: int
    queued_count: int
    recent_items: List[AlertQueueItem] = Field(default_factory=list)


class ControlRoomSummary(BaseModel):
    readiness: ReadinessReport
    intake: IntakeSummary
    alerts: AlertSummary
    feishu_sync: FeishuSyncStatusResponse
    mailpit_url: Optional[str] = None


class UploadInvoiceResponse(BaseModel):
    ok: bool
    message: str
    upload: IntakeUploadItem
    intake: IntakeSummary


class FeishuFailureItem(BaseModel):
    invoice_id: int
    seller_name: Optional[str] = None
    invoice_code: Optional[str] = None
    invoice_number: Optional[str] = None
    purchase_order_no: Optional[str] = None
    sync_error: Optional[str] = None
    updated_at: Optional[str] = None


class FeishuRetryRequest(BaseModel):
    mode: Literal["pending", "failed", "recoverable", "all"] = "failed"
    limit: int = Field(default=20, ge=1, le=100)
    invoice_ids: List[int] = Field(default_factory=list)


class FeishuRetryDetail(BaseModel):
    invoice_id: int
    ok: bool
    record_id: Optional[str] = None
    error: Any = None


class FeishuReplayResult(BaseModel):
    ok_count: int
    fail_count: int
    details: List[FeishuRetryDetail]
    run_id: Optional[str] = None
    latency_ms: Optional[float] = None
