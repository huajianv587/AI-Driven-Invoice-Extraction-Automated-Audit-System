import sys
import time
import urllib.request


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/wait_for_http.py <url> [timeout_sec]")

    url = sys.argv[1]
    timeout_sec = int(sys.argv[2]) if len(sys.argv) >= 3 else 120
    deadline = time.time() + timeout_sec
    last_error = None

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if 200 <= resp.status < 400:
                    print(f"[ok] HTTP endpoint is ready: {url}")
                    return
        except Exception as exc:
            last_error = exc
            print(f"[wait] Endpoint not ready yet: {url} -> {exc}")
        time.sleep(2)

    raise RuntimeError(f"HTTP endpoint not ready after timeout: {url} -> {last_error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        sys.exit(1)
