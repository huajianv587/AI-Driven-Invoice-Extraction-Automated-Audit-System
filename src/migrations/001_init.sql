CREATE TABLE IF NOT EXISTS invoices (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  unique_hash VARCHAR(64) NOT NULL,
  source_file_path TEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'INGESTED',
  invoice_code VARCHAR(64) NULL,
  invoice_number VARCHAR(64) NULL,
  invoice_date VARCHAR(32) NULL,
  purchase_order_no VARCHAR(64) NULL,
  seller_name VARCHAR(255) NULL,
  buyer_name VARCHAR(255) NULL,
  currency VARCHAR(16) NULL,
  total_amount_with_tax DECIMAL(18,2) NULL,
  tax_amount DECIMAL(18,2) NULL,
  expected_amount DECIMAL(18,2) NULL,
  amount_diff DECIMAL(18,2) NULL,
  risk_flag TINYINT NOT NULL DEFAULT 0,
  risk_summary TEXT NULL,
  risk_reason TEXT NULL,
  raw_ocr_json JSON NULL,
  llm_json JSON NULL,
  normalized_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_invoices_unique_hash (unique_hash)
);

CREATE TABLE IF NOT EXISTS invoice_items (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  line_no INT NOT NULL,
  item_name VARCHAR(255) NULL,
  spec VARCHAR(255) NULL,
  qty DECIMAL(18,4) NULL,
  unit VARCHAR(32) NULL,
  unit_price DECIMAL(18,4) NULL,
  amount DECIMAL(18,2) NULL,
  tax_rate DECIMAL(10,4) NULL,
  tax_amount DECIMAL(18,2) NULL,
  remark TEXT NULL,
  raw_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_items_invoice_id (invoice_id)
);

CREATE TABLE IF NOT EXISTS invoice_events (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  message TEXT NULL,
  payload JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_events_invoice_id (invoice_id)
);

CREATE TABLE IF NOT EXISTS risk_hits (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  rule_id VARCHAR(64) NOT NULL,
  severity VARCHAR(16) NOT NULL,
  reason TEXT NOT NULL,
  evidence TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_risk_invoice_id (invoice_id)
);

CREATE TABLE IF NOT EXISTS purchase_orders (
  po_no VARCHAR(64) PRIMARY KEY,
  expected_amount DECIMAL(18,2) NOT NULL,
  currency VARCHAR(16) NULL,
  vendor_name VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS explanations (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  submitter VARCHAR(128) NULL,
  explanation TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_expl_invoice_id (invoice_id)
);

CREATE TABLE IF NOT EXISTS explanation_attachments (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  explanation_id BIGINT NOT NULL,
  filename VARCHAR(255) NOT NULL,
  content_type VARCHAR(128) NULL,
  file_path TEXT NOT NULL,
  size_bytes BIGINT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_attach_expl_id (explanation_id)
);

CREATE TABLE IF NOT EXISTS approval_tasks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING',  -- PENDING/APPROVED/REJECTED
  approver VARCHAR(128) NULL,
  decision_note TEXT NULL,
  decided_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_appr_invoice_id (invoice_id),
  INDEX idx_appr_status (status)
);

CREATE TABLE IF NOT EXISTS invoice_feishu_sync (
  invoice_id BIGINT PRIMARY KEY,
  feishu_record_id VARCHAR(64) NULL,
  synced_at DATETIME NULL,
  attempt_count INT NOT NULL DEFAULT 0,
  last_attempt_at DATETIME NULL,
  sync_error TEXT NULL
);
