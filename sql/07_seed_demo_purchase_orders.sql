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
  'Local demo purchase order used to trigger invoice amount mismatch alerts.'
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
