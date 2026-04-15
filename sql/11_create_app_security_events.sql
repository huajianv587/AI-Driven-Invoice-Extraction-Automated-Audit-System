CREATE TABLE IF NOT EXISTS app_security_events (
  id BIGINT NOT NULL AUTO_INCREMENT,
  event_type VARCHAR(64) NOT NULL,
  user_id BIGINT NULL,
  email VARCHAR(255) NULL,
  role VARCHAR(32) NULL,
  request_id VARCHAR(64) NULL,
  ip_address VARCHAR(64) NULL,
  user_agent VARCHAR(255) NULL,
  outcome VARCHAR(32) NOT NULL DEFAULT 'info',
  metadata JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_app_security_events_type_created (event_type, created_at),
  KEY idx_app_security_events_user_created (user_id, created_at),
  KEY idx_app_security_events_email_created (email, created_at),
  KEY idx_app_security_events_request_id (request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app_login_attempts (
  id BIGINT NOT NULL AUTO_INCREMENT,
  email VARCHAR(255) NOT NULL,
  ip_address VARCHAR(64) NULL,
  user_agent VARCHAR(255) NULL,
  success TINYINT(1) NOT NULL DEFAULT 0,
  failure_reason VARCHAR(64) NULL,
  request_id VARCHAR(64) NULL,
  occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_app_login_attempts_email_time (email, occurred_at),
  KEY idx_app_login_attempts_ip_time (ip_address, occurred_at),
  KEY idx_app_login_attempts_success_time (success, occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
