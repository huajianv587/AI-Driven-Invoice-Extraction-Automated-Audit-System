CREATE TABLE IF NOT EXISTS invoice_events (
  id BIGINT NOT NULL AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  event_status VARCHAR(32) NOT NULL,
  payload JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_invoice_events_invoice_id (invoice_id),
  KEY idx_invoice_events_type_status (event_type, event_status),
  CONSTRAINT fk_invoice_events_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
