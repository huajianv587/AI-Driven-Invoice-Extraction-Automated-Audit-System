export type UserRole = "admin" | "reviewer" | "ops";

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
}

export interface AuthSessionResponse {
  user: AuthUser;
  access_token: string;
  expires_at: number;
}

export interface AuthSessionDevice {
  id: number;
  user_agent?: string | null;
  ip_address?: string | null;
  device_label: string;
  last_seen_at?: string | null;
  expires_at?: string | null;
  revoked_at?: string | null;
  created_at?: string | null;
  is_current: boolean;
}

export interface DashboardTotals {
  total_count: number;
  risk_count: number;
  pending_count: number;
  today_count: number;
  total_amount: number;
  risk_amount: number;
}

export interface DashboardRatios {
  risk_ratio: number;
  reviewed_ratio: number;
  sync_ratio: number;
  alert_ratio: number;
}

export interface ConnectorSnapshot {
  ready_count: number;
  total_count: number;
  blocked_count: number;
}

export interface FeishuSyncSnapshot {
  pending_count: number;
  failed_count: number;
  synced_count: number;
}

export interface InvoiceListItem {
  id: number;
  invoice_date?: string | null;
  seller_name?: string | null;
  buyer_name?: string | null;
  invoice_code?: string | null;
  invoice_number?: string | null;
  purchase_order_no?: string | null;
  total_amount_with_tax: number;
  expected_amount: number;
  amount_diff: number;
  risk_flag: boolean;
  risk_reason_summary: string;
  invoice_status?: string | null;
  notify_personal_status?: string | null;
  notify_leader_status?: string | null;
  created_at?: string | null;
  sync_label: string;
  sync_tone: string;
  sync_error?: string | null;
}

export interface DashboardSummary {
  totals: DashboardTotals;
  ratios: DashboardRatios;
  connectors: ConnectorSnapshot;
  feishu_sync: FeishuSyncSnapshot;
  top_risk: InvoiceListItem[];
  recent_queue: InvoiceListItem[];
}

export interface DailyActivityPoint {
  activity_date?: string | null;
  day_label: string;
  total_count: number;
  risk_count: number;
}

export interface InvoiceListResponse {
  items: InvoiceListItem[];
  total_count: number;
  matched_risk_count: number;
  matched_pending_count: number;
  matched_total_amount: number;
}

export interface InvoiceLineItem {
  id?: number;
  item_name?: string | null;
  item_spec?: string | null;
  item_unit?: string | null;
  item_quantity?: number | null;
  item_unit_price?: number | null;
  item_amount?: number | null;
  tax_rate?: number | string | null;
  tax_amount?: number | null;
}

export interface InvoiceEvent {
  id: number;
  event_type: string;
  event_status: string;
  payload?: unknown;
  created_at?: string | null;
}

export interface ReviewTask {
  id: number;
  review_result: string;
  handler_user?: string | null;
  handling_note?: string | null;
  source_channel?: string | null;
  created_at?: string | null;
}

export interface InvoiceStateTransition {
  id: number;
  from_status?: string | null;
  to_status: string;
  actor_email?: string | null;
  actor_role?: string | null;
  request_id?: string | null;
  reason?: string | null;
  created_at?: string | null;
}

export interface InvoiceSyncState {
  feishu_record_id?: string | null;
  synced_at?: string | null;
  sync_error?: string | null;
  sync_label: string;
  sync_tone: string;
}

export interface PurchaseOrderSummary {
  purchase_no?: string | null;
  supplier_name?: string | null;
  purchaser_name?: string | null;
  purchaser_email?: string | null;
  buyer_email?: string | null;
  leader_email?: string | null;
  total_amount_with_tax?: number | null;
  expected_amount?: number | null;
  purchase_order_date?: string | null;
  status?: string | null;
}

export interface InvoiceRecord {
  id: number;
  invoice_status?: string | null;
  seller_name?: string | null;
  buyer_name?: string | null;
  purchase_order_no?: string | null;
  invoice_code?: string | null;
  invoice_number?: string | null;
  invoice_date?: string | null;
  total_amount_with_tax: number;
  expected_amount: number;
  amount_diff: number;
  risk_flag: boolean;
  risk_reason?: unknown;
  risk_reason_summary: string;
  handler_user?: string | null;
  handler_reason?: string | null;
  handled_at?: string | null;
  notify_personal_status?: string | null;
  notify_leader_status?: string | null;
  unique_hash?: string | null;
  source_file_path?: string | null;
  raw_ocr_json?: unknown;
  llm_json?: unknown;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface InvoiceDetail {
  invoice: InvoiceRecord;
  items: InvoiceLineItem[];
  events: InvoiceEvent[];
  review_tasks: ReviewTask[];
  state_transitions: InvoiceStateTransition[];
  sync: InvoiceSyncState;
  purchase_order?: PurchaseOrderSummary | null;
}

export interface ConnectorHealth {
  name: string;
  status: string;
  message: string;
  detail?: string | null;
  cached_at?: string | null;
  latency_ms?: number | null;
  stale: boolean;
}

export interface FeishuSyncStatusResponse {
  summary: FeishuSyncSnapshot;
  retry_worker_enabled: boolean;
  retry_interval_sec: number;
  retry_mode: string;
  retry_batch_limit: number;
}

export interface FeishuFailureItem {
  invoice_id: number;
  seller_name?: string | null;
  invoice_code?: string | null;
  invoice_number?: string | null;
  purchase_order_no?: string | null;
  sync_error?: string | null;
  updated_at?: string | null;
}

export interface FeishuReplayResult {
  ok_count: number;
  fail_count: number;
  details: Array<{
    invoice_id: number;
    ok: boolean;
    record_id?: string | null;
    error?: unknown;
  }>;
}
