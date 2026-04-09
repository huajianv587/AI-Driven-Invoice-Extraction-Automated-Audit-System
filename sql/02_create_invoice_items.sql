CREATE TABLE IF NOT EXISTS invoice_items (
  id BIGINT NOT NULL AUTO_INCREMENT,
  invoice_id BIGINT NOT NULL,
  item_name VARCHAR(255) NULL,
  item_spec VARCHAR(255) NULL,
  item_unit VARCHAR(64) NULL,
  item_quantity DECIMAL(18, 4) NULL,
  item_unit_price DECIMAL(18, 6) NULL,
  item_amount DECIMAL(18, 2) NULL,
  tax_rate VARCHAR(32) NULL,
  tax_amount DECIMAL(18, 2) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_invoice_items_invoice_id (invoice_id),
  CONSTRAINT fk_invoice_items_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
