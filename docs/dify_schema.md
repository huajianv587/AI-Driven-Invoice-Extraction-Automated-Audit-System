# Dify Workflow: Invoice Structured Extraction Schema

## Inputs
- `ocr_text` (string): OCR extracted text (all lines concatenated)
- `source_filename` (string)

## Required Output (JSON)
Return a JSON object with keys:

- `invoice_meta`:
  - `invoice_code` (string|null)
  - `invoice_number` (string|null)
  - `invoice_date` (string|null)
  - `purchase_order_no` (string|null)
  - `currency` (string|null)

- `seller`: { `name`, `tax_no`, `address`, `phone`, `bank`, `bank_account` }
- `buyer`:  { `name`, `tax_no`, `address`, `phone`, `bank`, `bank_account` }

- `totals`:
  - `total_amount_without_tax` (number|null)
  - `tax_amount` (number|null)
  - `total_amount_with_tax` (number|null)

- `staff`:
  - `drawer` (string|null)
  - `reviewer` (string|null)
  - `payee` (string|null)

- `invoice_items` (array of objects):
  - `item_name` / `name`
  - `spec`
  - `qty`
  - `unit`
  - `unit_price`
  - `amount`
  - `tax_rate`
  - `tax_amount`
  - `remark`

- `risk`:
  - `flag` (0/1)
  - `summary` (string)
  - `reason` (string|null)

## Prompt suggestion (copy)
You are a finance invoice extraction engine. 
Given OCR text, output STRICT JSON (no markdown, no comments) following the schema exactly.
If a field is missing, return null. Numbers must be numeric (no commas).
For invoice_items, reconstruct table rows as best as possible.
