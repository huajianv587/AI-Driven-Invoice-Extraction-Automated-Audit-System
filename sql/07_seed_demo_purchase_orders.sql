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
  purchaser_email=IF(
    purchase_orders.purchaser_email IS NULL
    OR purchase_orders.purchaser_email = ''
    OR purchase_orders.purchaser_email LIKE '%@local.test',
    VALUES(purchaser_email),
    purchase_orders.purchaser_email
  ),
  buyer_email=IF(
    purchase_orders.buyer_email IS NULL
    OR purchase_orders.buyer_email = ''
    OR purchase_orders.buyer_email LIKE '%@local.test',
    VALUES(buyer_email),
    purchase_orders.buyer_email
  ),
  leader_email=IF(
    purchase_orders.leader_email IS NULL
    OR purchase_orders.leader_email = ''
    OR purchase_orders.leader_email LIKE '%@local.test',
    VALUES(leader_email),
    purchase_orders.leader_email
  ),
  total_amount_with_tax=VALUES(total_amount_with_tax),
  expected_amount=VALUES(expected_amount),
  purchase_order_date=VALUES(purchase_order_date),
  status=VALUES(status),
  notes=VALUES(notes),
  updated_at=NOW();
