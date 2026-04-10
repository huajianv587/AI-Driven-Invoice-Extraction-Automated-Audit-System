from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from src.product.settings import get_settings


ROOT = Path(__file__).resolve().parents[1]


def login(base_url: str, username: str, password: str) -> str:
    response = requests.post(
        f"{base_url}/v1/auth/login",
        json={"username": username, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def main() -> None:
    settings = get_settings()
    base_url = settings.api_base_url.rstrip("/")
    operator_token = login(base_url, settings.operator_username, settings.operator_password)

    invoice_path = ROOT / "invoices" / "invoice.jpg"
    with invoice_path.open("rb") as handle:
        upload = requests.post(
            f"{base_url}/v1/invoices/upload",
            headers={"Authorization": f"Bearer {operator_token}"},
            files={"file": (invoice_path.name, handle, "image/jpeg")},
            timeout=120,
        )
    upload.raise_for_status()
    upload_payload = upload.json()
    task_id = upload_payload["task_id"]

    task = None
    for _ in range(60):
        response = requests.get(
            f"{base_url}/v1/tasks/{task_id}",
            headers={"Authorization": f"Bearer {operator_token}"},
            timeout=20,
        )
        response.raise_for_status()
        task = response.json()
        if task["processing_status"] in {"COMPLETED", "FAILED"}:
            break
        time.sleep(2)

    if not task or task["processing_status"] != "COMPLETED":
        raise RuntimeError(f"Task did not complete successfully: {task}")

    invoice_id = task["invoice_id"]
    reviewer_token = login(base_url, settings.reviewer_username, settings.reviewer_password)
    invoice_detail = requests.get(
        f"{base_url}/v1/invoices/{invoice_id}",
        headers={"Authorization": f"Bearer {reviewer_token}"},
        timeout=20,
    )
    invoice_detail.raise_for_status()
    detail_payload = invoice_detail.json()

    if detail_payload["invoice"]["review_status"] == "NEEDS_REVIEW":
        review_resp = requests.post(
            f"{base_url}/v1/reviews",
            headers={"Authorization": f"Bearer {reviewer_token}"},
            json={"invoice_id": invoice_id, "review_status": "APPROVED", "note": "Approved by product_e2e_test"},
            timeout=20,
        )
        review_resp.raise_for_status()
        detail_payload = review_resp.json()

    print(
        json.dumps(
            {
                "upload": upload_payload,
                "task": task,
                "invoice": detail_payload["invoice"],
                "notifications": detail_payload["notifications"],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
