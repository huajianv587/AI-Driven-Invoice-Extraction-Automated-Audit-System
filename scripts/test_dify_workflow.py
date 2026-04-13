from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.services.dify_client import DifyClient
from src.services.ingestion_service import flatten_outputs
from src.services.ocr_client import OCRClient


def resolve_invoice_path(raw_arg: str) -> Path:
    path = Path(raw_arg)
    if not path.is_absolute():
        candidate = ROOT / "invoices" / raw_arg
        path = candidate if candidate.exists() else ROOT / raw_arg
    return path.resolve()


def try_read_ocr_text(cfg, file_path: Path) -> str:
    try:
        client = OCRClient(cfg["OCR_BASE_URL"])
        return client.ocr_text_only(str(file_path), timeout_sec=120)
    except Exception:
        return ""


def main() -> None:
    load_env(override=True)
    cfg = load_flat_config()

    dify_key = str(cfg["DIFY_API_KEY"] or "").strip()
    workflow_id = str(cfg["DIFY_WORKFLOW_ID"] or "").strip()
    if not dify_key or not workflow_id:
        raise RuntimeError("DIFY_API_KEY / DIFY_WORKFLOW_ID are empty in the saved .env.")

    raw_arg = sys.argv[1] if len(sys.argv) > 1 else "invoice.jpg"
    file_path = resolve_invoice_path(raw_arg)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    client = DifyClient(api_key=dify_key, base_url=str(cfg["DIFY_BASE_URL"]))
    app_info = {}
    parameters = {}
    try:
        app_info = client.get_app_info()
    except Exception:
        pass
    try:
        parameters = client.get_parameters()
    except Exception:
        pass

    variable_meta = client.extract_input_variables(parameters)
    configured_image_key = str(cfg["DIFY_IMAGE_KEY"] or "").strip() or "invoice"
    ocr_text = try_read_ocr_text(cfg, file_path)
    prepared = client.prepare_local_file_input(
        file_path=str(file_path),
        parameters=parameters,
        preferred_variable=configured_image_key,
    )

    try:
        result = client.run_workflow(
            workflow_id=workflow_id,
            inputs={prepared["variable_name"]: prepared["file_input"], "ocr_text": ocr_text},
            timeout=180,
        )
    finally:
        cleanup_path = prepared.get("cleanup_path")
        if cleanup_path and os.path.exists(cleanup_path):
            try:
                os.remove(cleanup_path)
            except Exception:
                pass

    outputs = ((result.get("data") or {}).get("outputs") or {})
    flat = flatten_outputs(outputs if isinstance(outputs, dict) else {})

    summary = {
        "file_path": str(file_path),
        "used_image_key": prepared["variable_name"],
        "file_kind": prepared.get("file_kind"),
        "upload_path": prepared.get("upload_path"),
        "allowed_file_extensions": prepared.get("allowed_file_extensions"),
        "allowed_file_types": prepared.get("allowed_file_types"),
        "attempt": result.get("_attempt"),
        "app_info_title": ((app_info.get("title") or app_info.get("name") or "") if isinstance(app_info, dict) else ""),
        "input_variables": variable_meta,
        "output_keys": sorted(outputs.keys()) if isinstance(outputs, dict) else [],
        "invoice_meta": {
            "invoice_code": flat.get("invoice_code"),
            "invoice_number": flat.get("invoice_number"),
            "invoice_date": flat.get("invoice_date"),
        },
        "seller_name": flat.get("seller_name"),
        "buyer_name": flat.get("buyer_name"),
        "total_amount_with_tax": flat.get("total_amount_with_tax"),
        "item_count": len(flat.get("invoice_items") or []),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
