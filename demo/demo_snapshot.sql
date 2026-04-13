SET NAMES utf8mb4;

DELETE FROM invoice_review_tasks;
DELETE FROM invoice_feishu_sync;
DELETE FROM invoice_events;
DELETE FROM invoice_items;
DELETE FROM invoices;

ALTER TABLE invoice_review_tasks AUTO_INCREMENT = 1;
ALTER TABLE invoice_feishu_sync AUTO_INCREMENT = 1;
ALTER TABLE invoice_events AUTO_INCREMENT = 1;
ALTER TABLE invoice_items AUTO_INCREMENT = 1;
ALTER TABLE invoices AUTO_INCREMENT = 1;

INSERT INTO purchase_orders(
  purchase_no,
  po_number,
  supplier,
  supplier_name,
  purchaser_name,
  purchaser_email,
  buyer_email,
  leader_email,
  total_amount_with_tax,
  expected_amount,
  purchase_order_date,
  status,
  notes
)
VALUES(
  'PO-DEMO-001',
  'PO-DEMO-001',
  'Demo Supplier Ltd',
  'Demo Supplier Ltd',
  'Demo Purchaser',
  'buyer-demo@local.test',
  'buyer-demo@local.test',
  'leader-demo@local.test',
  100000.00,
  100000.00,
  '2026-01-01',
  'Approved',
  'Seed row used by the local demo and imported git snapshot.'
)
ON DUPLICATE KEY UPDATE
  po_number=VALUES(po_number),
  supplier=VALUES(supplier),
  supplier_name=VALUES(supplier_name),
  purchaser_name=VALUES(purchaser_name),
  purchaser_email=VALUES(purchaser_email),
  buyer_email=VALUES(buyer_email),
  leader_email=VALUES(leader_email),
  total_amount_with_tax=VALUES(total_amount_with_tax),
  expected_amount=VALUES(expected_amount),
  purchase_order_date=VALUES(purchase_order_date),
  status=VALUES(status),
  notes=VALUES(notes),
  updated_at=NOW();

INSERT INTO invoices(
  id,
  invoice_type,
  invoice_code,
  invoice_number,
  invoice_date,
  invoice_status,
  is_red_invoice,
  seller_name,
  seller_tax_id,
  buyer_name,
  buyer_tax_id,
  total_amount_without_tax,
  total_tax_amount,
  total_amount_with_tax,
  amount_in_words,
  remarks,
  purchase_order_no,
  source_file_path,
  raw_ocr_json,
  llm_json,
  schema_version,
  expected_amount,
  amount_diff,
  risk_flag,
  risk_reason,
  notify_personal_status,
  notify_leader_status,
  unique_hash,
  created_at,
  updated_at
)
VALUES(
  1,
  '增值税专用发票',
  '3400232130',
  '00097000',
  '2024-01-12',
  'Pending',
  0,
  '芜湖高普化学品有限公司',
  '91340200762768569K',
  '振宜汽车有限公司',
  '91340800MA2U89AL16',
  924189.36,
  120144.62,
  1044333.98,
  '壹佰零肆万叁仟叁佰叁拾叁元玖角捌分',
  'Imported from git demo snapshot. Safe for a fresh local machine.',
  'PO-DEMO-001',
  './invoices/invoice.jpg',
  JSON_OBJECT(
    'status', 'success',
    'source', 'demo_snapshot',
    'text_preview', '安徽增值税专用发票'
  ),
  JSON_OBJECT(
    'invoice_type', '增值税专用发票',
    'invoice_code', '3400232130',
    'invoice_number', '00097000',
    'invoice_date', '2024-01-12',
    'seller_name', '芜湖高普化学品有限公司',
    'buyer_name', '振宜汽车有限公司',
    'risk_flag', TRUE,
    'risk_reason', JSON_ARRAY('AmountMismatchWithExpected', 'SellerNameMismatch', 'InvoiceDateEarlierThanPO'),
    'invoice_items', JSON_ARRAY(
      JSON_OBJECT(
        'item_name', '*其他化学制品*行李箱储物盒',
        'item_spec', '403002850AA',
        'item_unit', 'EA',
        'item_quantity', 1806,
        'item_unit_price', 70.01,
        'item_amount', 126438.06,
        'tax_rate', '13%',
        'tax_amount', 16436.95
      ),
      JSON_OBJECT(
        'item_name', '*其他化学制品*行李箱地毯总成',
        'item_spec', '403002851ABABK',
        'item_unit', 'EA',
        'item_quantity', 10658,
        'item_unit_price', 74.85,
        'item_amount', 797751.30,
        'tax_rate', '13%',
        'tax_amount', 103707.67
      )
    )
  ),
  'v1',
  100000.00,
  944333.98,
  1,
  JSON_ARRAY('AmountMismatchWithExpected', 'SellerNameMismatch', 'InvoiceDateEarlierThanPO'),
  'Sent',
  'Sent',
  '465d12fcc2d41471ace917d054a609e90cd95c8f85d53bb8f8f3a25d8e06087e',
  '2026-01-01 09:00:00',
  '2026-01-01 09:00:00'
);

INSERT INTO invoice_items(
  invoice_id,
  item_name,
  item_spec,
  item_unit,
  item_quantity,
  item_unit_price,
  item_amount,
  tax_rate,
  tax_amount,
  created_at
)
VALUES
(
  1,
  '*其他化学制品*行李箱储物盒',
  '403002850AA',
  'EA',
  1806,
  70.01,
  126438.06,
  '13%',
  16436.95,
  '2026-01-01 09:00:01'
),
(
  1,
  '*其他化学制品*行李箱地毯总成',
  '403002851ABABK',
  'EA',
  10658,
  74.85,
  797751.30,
  '13%',
  103707.67,
  '2026-01-01 09:00:01'
);

INSERT INTO invoice_events(
  invoice_id,
  event_type,
  event_status,
  payload,
  created_at
)
VALUES
(
  1,
  'INGEST',
  'OK',
  JSON_OBJECT(
    'source', './invoices/invoice.jpg',
    'mode', 'demo_snapshot'
  ),
  '2026-01-01 09:00:05'
),
(
  1,
  'EMAIL_ALERT',
  'SENT',
  JSON_OBJECT(
    'to', 'buyer-demo@local.test',
    'cc', JSON_ARRAY('leader-demo@local.test'),
    'status', 'Sent',
    'subject', '[Invoice Risk Alert] PO:PO-DEMO-001 Invoice:3400232130-00097000',
    'form_link', 'http://127.0.0.1:8517/?view=anomaly_form&invoice_id=1&purchase_order_no=PO-DEMO-001&unique_hash=465d12fcc2d41471ace917d054a609e90cd95c8f85d53bb8f8f3a25d8e06087e'
  ),
  '2026-01-01 09:00:10'
);

ALTER TABLE invoices AUTO_INCREMENT = 2;
ALTER TABLE invoice_items AUTO_INCREMENT = 3;
ALTER TABLE invoice_events AUTO_INCREMENT = 3;
