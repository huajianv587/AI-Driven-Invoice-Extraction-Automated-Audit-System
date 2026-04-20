CREATE TABLE IF NOT EXISTS app_operation_locks (
  lock_name VARCHAR(128) NOT NULL,
  owner VARCHAR(128) NOT NULL,
  expires_at DATETIME NOT NULL,
  acquired_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (lock_name),
  KEY idx_app_operation_locks_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
