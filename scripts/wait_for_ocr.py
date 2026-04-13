import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_env


def get_ocr_base_url() -> str:
    load_env()
    return ((os.getenv("OCR_BASE_URL") or "http://127.0.0.1:8001").strip() or "http://127.0.0.1:8001").rstrip("/")


def check_ocr_ready(base_url: str) -> tuple[bool, str]:
    openapi_url = f"{base_url}/openapi.json"
    with urllib.request.urlopen(openapi_url, timeout=5) as resp:
        payload = json.load(resp)
    paths = payload.get("paths") or {}
    if "/ocr" not in paths:
        return False, f"/ocr route missing at {openapi_url}"
    return True, openapi_url


def main():
    timeout_sec = int(sys.argv[1]) if len(sys.argv) >= 2 else 90
    base_url = get_ocr_base_url()
    deadline = time.time() + timeout_sec
    last_error = None

    while time.time() < deadline:
        try:
            ok, detail = check_ocr_ready(base_url)
            if ok:
                print(f"[ok] OCR service is ready: {base_url}")
                return
            last_error = detail
            print(f"[wait] OCR endpoint not ready yet: {detail}")
        except Exception as exc:
            last_error = exc
            print(f"[wait] OCR not ready yet: {exc}")
        time.sleep(2)

    raise RuntimeError(f"OCR service not ready after timeout: {base_url} -> {last_error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        sys.exit(1)
