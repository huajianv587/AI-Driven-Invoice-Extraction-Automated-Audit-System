CREATE TABLE IF NOT EXISTS invoice_state_transitions (
  id BIGINT NOT NULL AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  from_status VARCHAR(32) NULL,
  to_status VARCHAR(32) NOT NULL,
  actor_user_id BIGINT NULL,
  actor_email VARCHAR(255) NULL,
  actor_role VARCHAR(32) NULL,
  request_id VARCHAR(64) NULL,
  reason VARCHAR(5000) NULL,
  idempotency_key VARCHAR(128) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_invoice_state_transitions_invoice (invoice_id, created_at),
  KEY idx_invoice_state_transitions_actor (actor_email, created_at),
  KEY idx_invoice_state_transitions_idempotency (idempotency_key),
  CONSTRAINT fk_invoice_state_transitions_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
