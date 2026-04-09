from __future__ import annotations
import os
import mimetypes
from typing import Dict, Any
import requests


class OCRClient:
    """
    main 通过它调用 OCR 微服务（FastAPI）
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")

    def ocr_image(self, image_path: str, timeout_sec: int = 60) -> Dict[str, Any]:
        if not os.path.exists(image_path):
            return {"status": "error", "message": f"file not found: {image_path}"}

        url = f"{self.base_url}/ocr"
        filename = os.path.basename(image_path)
        mime_type, _ = mimetypes.guess_type(image_path)
        mime_type = mime_type or "application/octet-stream"

        with open(image_path, "rb") as f:
            files = {"file": (filename, f, mime_type)}
            resp = requests.post(url, files=files, timeout=timeout_sec)
            resp.raise_for_status()
            return resp.json()

    def ocr_text_only(self, image_path: str, timeout_sec: int = 60) -> str:
        res = self.ocr_image(image_path, timeout_sec=timeout_sec)
        if res.get("status") != "success":
            raise RuntimeError(f"OCR failed: {res}")
        return res.get("extracted_text", "") or ""
