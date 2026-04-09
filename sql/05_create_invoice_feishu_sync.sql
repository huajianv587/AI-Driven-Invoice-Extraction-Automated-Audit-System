CREATE TABLE IF NOT EXISTS invoice_feishu_sync (
  id BIGINT NOT NULL AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  feishu_record_id VARCHAR(128) NULL,
  synced_at DATETIME NULL,
  sync_error TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_invoice_feishu_sync_invoice_id (invoice_id),
  CONSTRAINT fk_invoice_feishu_sync_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
