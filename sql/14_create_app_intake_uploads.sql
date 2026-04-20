CREATE TABLE IF NOT EXISTS app_intake_uploads (
  id BIGINT NOT NULL AUTO_INCREMENT,
  original_name VARCHAR(255) NOT NULL,
  staged_name VARCHAR(255) NOT NULL,
  extension VARCHAR(16) NOT NULL,
  size_bytes BIGINT NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  error_message TEXT NULL,
  invoice_id BIGINT NULL,
  created_by BIGINT NULL,
  created_by_email VARCHAR(255) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_app_intake_uploads_staged_name (staged_name),
  KEY idx_app_intake_uploads_status_updated (status, updated_at),
  KEY idx_app_intake_uploads_invoice (invoice_id),
  KEY idx_app_intake_uploads_created_by (created_by)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
