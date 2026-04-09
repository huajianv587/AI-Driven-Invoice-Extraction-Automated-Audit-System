CREATE TABLE IF NOT EXISTS invoice_review_tasks (
  id BIGINT NOT NULL AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  purchase_order_no VARCHAR(64) NULL,
  unique_hash CHAR(64) NULL,
  review_result VARCHAR(32) NOT NULL,
  handler_user VARCHAR(64) NULL,
  handling_note TEXT NULL,
  source_channel VARCHAR(32) NOT NULL DEFAULT 'streamlit_form',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_invoice_review_tasks_invoice_id (invoice_id),
  KEY idx_invoice_review_tasks_result (review_result),
  CONSTRAINT fk_invoice_review_tasks_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
