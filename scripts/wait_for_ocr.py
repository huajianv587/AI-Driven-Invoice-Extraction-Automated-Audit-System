import sys
import time
import urllib.request


OCR_HEALTH_URL = "http://127.0.0.1:8000/docs"


def main():
    deadline = time.time() + 90
    last_error = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(OCR_HEALTH_URL, timeout=5) as resp:
                if 200 <= resp.status < 500:
                    print("[ok] OCR service is ready.")
                    return
        except Exception as exc:
            last_error = exc
            print(f"[wait] OCR not ready yet: {exc}")
        time.sleep(2)

    raise RuntimeError(f"OCR service not ready after timeout: {last_error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        sys.exit(1)
