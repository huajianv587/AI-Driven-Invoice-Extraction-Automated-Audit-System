from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests

from src.utils.logger import get_logger

logger = get_logger()


class OCRClient:
    def __init__(self, ocr_url: str | None, timeout_sec: int = 40):
        self.ocr_url = (ocr_url or "").strip()
        self.timeout_sec = int(timeout_sec or 40)

    def extract(self, file_path: str) -> Dict[str, Any]:
        """
        Call OCR HTTP endpoint via multipart/form-data:
          POST {OCR_URL} with form field name = "file"

        Compatible response fields:
          - text / lines
          - extracted_text (RapidOCR demo)
          - blocks (legacy)
        """
        # If OCR_URL not set -> demo stub (pipeline still works)
        if not self.ocr_url:
            return {
                "text": f"[DEMO_OCR] {os.path.basename(file_path)}",
                "lines": [],
                "provider": "demo_stub",
            }

        t0 = time.time()

        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            resp = requests.post(self.ocr_url, files=files, timeout=self.timeout_sec)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}

        # ---- Normalize common OCR response shapes ----
        # RapidOCR demo returns: {"status":"success","extracted_text": "...", ...}
        # Our pipeline prefers: {"text":"...", "lines":[...]}
        text = (
            data.get("text")
            or data.get("extracted_text")
            or data.get("extractedText")
            or ""
        )

        # lines/blocks may be list of strings or list of dicts
        lines = data.get("lines") or data.get("blocks") or data.get("results") or []
        if isinstance(lines, str):
            # some OCR returns a string; convert to one-line list
            lines = [{"text": lines}]
        elif isinstance(lines, list):
            # normalize list items
            norm_lines = []
            for x in lines:
                if isinstance(x, str):
                    norm_lines.append({"text": x})
                elif isinstance(x, dict):
                    # keep text/score if exists
                    if "text" in x:
                        norm_lines.append({"text": x.get("text", ""), "score": x.get("score")})
                    elif "line" in x:
                        norm_lines.append({"text": x.get("line", ""), "score": x.get("score")})
                    else:
                        # unknown dict shape
                        norm_lines.append({"text": str(x)})
                else:
                    norm_lines.append({"text": str(x)})
            lines = norm_lines
        else:
            lines = []

        out = {
            "text": text,
            "lines": lines,
            "provider": data.get("provider") or "http_ocr",
            "raw": data,
            "elapsed_ms": int((time.time() - t0) * 1000),
        }
        logger.info("[OCR] ok elapsed_ms=%s chars=%s", out["elapsed_ms"], len(text or ""))
        return out
