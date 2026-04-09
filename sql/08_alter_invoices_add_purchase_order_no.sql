SET @purchase_order_no_exists = (
  SELECT COUNT(*)
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'invoices'
    AND COLUMN_NAME = 'purchase_order_no'
);

SET @purchase_order_no_sql = IF(
  @purchase_order_no_exists = 0,
  'ALTER TABLE invoices ADD COLUMN purchase_order_no VARCHAR(64) NULL AFTER remarks',
  'SELECT 1'
);

PREPARE purchase_order_no_stmt FROM @purchase_order_no_sql;
EXECUTE purchase_order_no_stmt;
DEALLOCATE PREPARE purchase_order_no_stmt;
