from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, TextIO


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
ARTIFACTS = ROOT / "artifacts" / "e2e-logs"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config


processes: List[subprocess.Popen] = []
log_files: List[TextIO] = []
ready_payload: Dict[str, object] = {}


def command_name(name: str) -> str:
    return f"{name}.cmd" if os.name == "nt" else name


def run(command: List[str], *, cwd: Path = ROOT, env: Optional[Dict[str, str]] = None) -> None:
    print(f"[run] {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=str(cwd), env=env, check=True)


def check_url(url: str, timeout_sec: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as response:
            return 200 <= int(response.status) < 500
    except Exception:
        return False


def wait_url(url: str, timeout_sec: int, label: str) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if check_url(url):
            print(f"[ok] {label}: {url}", flush=True)
            return
        time.sleep(1)
    raise RuntimeError(f"{label} did not become ready: {url}")


def start_process(name: str, command: List[str], *, cwd: Path, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    log_path = ARTIFACTS / f"{name}.log"
    log_file = log_path.open("w", encoding="utf-8", errors="replace")
    log_files.append(log_file)
    print(f"[start] {name}: {' '.join(command)}", flush=True)
    print(f"[log] {name}: {log_path}", flush=True)
    proc = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )
    processes.append(proc)
    return proc


def cleanup() -> None:
    for proc in reversed(processes):
        if proc.poll() is not None:
            continue
        try:
            print(f"[stop] pid={proc.pid}", flush=True)
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
    for log_file in log_files:
        try:
            log_file.close()
        except Exception:
            pass


def start_docker(python: str) -> None:
    try:
        run(["docker", "compose", "up", "-d", "mysql", "mailpit"])
        return
    except Exception:
        docker_desktop = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
        if os.name == "nt" and docker_desktop.exists():
            print("[docker] Starting Docker Desktop...", flush=True)
            subprocess.Popen([str(docker_desktop)])
            run([python, "scripts/wait_for_docker.py"])
            run(["docker", "compose", "up", "-d", "mysql", "mailpit"])
            return
        raise


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps(ready_payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        return


def serve_health(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), HealthHandler)
    print(f"[ok] E2E stack health: http://127.0.0.1:{port}/healthz", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    signal.signal(signal.SIGTERM, lambda _sig, _frame: sys.exit(0))
    signal.signal(signal.SIGINT, lambda _sig, _frame: sys.exit(0))

    explicit_env = os.environ.copy()
    load_env(override=True)
    cfg = load_flat_config()
    python = sys.executable
    npm = command_name("npm")
    api_port = int(cfg["API_PORT"])
    frontend_port = int(cfg["FRONTEND_PORT"])
    orchestrator_port = int(os.getenv("PLAYWRIGHT_STACK_PORT", "3410"))
    stack_mode = os.getenv("WEB_E2E_MODE", "standard").strip().lower() or "standard"
    deep_mode = stack_mode == "deep"
    test_run_id = os.getenv("WEB_DEEP_TEST_RUN_ID", "").strip() or f"deep-{uuid.uuid4().hex[:10]}"
    api_health = f"http://127.0.0.1:{api_port}/api/health"
    frontend_url = f"http://127.0.0.1:{frontend_port}/"
    ocr_docs = f"{str(cfg['OCR_BASE_URL']).rstrip('/')}/docs"

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env["FRONTEND_PUBLIC_HOST"] = "localhost"
    if deep_mode:
        for key in ("APP_ENV", "ALLOW_REAL_INTEGRATION_TESTS", "WEB_DEEP_RESET_DEMO_DB", "WEB_DEEP_CONFIRM"):
            if key in explicit_env:
                env[key] = explicit_env[key]
            else:
                env.pop(key, None)
        env["WEB_DEEP_TEST_RUN_ID"] = test_run_id
        env["WEB_DEEP_EXTERNAL_PREFIX"] = os.getenv("WEB_DEEP_EXTERNAL_PREFIX", "DEEP_TEST")
        env["WEB_DEEP_REGRESSION_REPORT"] = str(ROOT / "artifacts" / "deep-regression" / "latest.json")

    try:
        if deep_mode:
            run([python, "scripts/guard_deep_regression.py"], env=env)
        start_docker(python)
        run([python, "scripts/apply_schema.py"], env=env)
        if deep_mode:
            run([python, "scripts/deep_product_regression.py"], env=env)
        run([python, "scripts/reset_demo_state.py"], env=env)
        run([python, "scripts/seed_web_demo_data.py"], env=env)
        run([python, "scripts/write_frontend_env.py"], env=env)

        if not (FRONTEND / "node_modules").exists():
            run([npm, "install"], cwd=FRONTEND, env=env)
        run([npm, "run", "build"], cwd=FRONTEND, env=env)

        if not check_url(ocr_docs):
            start_process("ocr", [python, "ocr_server.py"], cwd=ROOT, env=env)
        wait_url(ocr_docs, 120, "OCR")

        if not check_url(api_health):
            start_process("api", [python, "api_server.py"], cwd=ROOT, env=env)
        wait_url(api_health, 120, "FastAPI")

        if not check_url(frontend_url):
            start_process(
                "frontend",
                [npm, "run", "start", "--", "--hostname", "127.0.0.1", "--port", str(frontend_port)],
                cwd=FRONTEND,
                env=env,
            )
        wait_url(frontend_url, 180, "Next.js")

        ready_payload.update(
            {
                "ok": True,
                "api": api_health,
                "frontend": frontend_url,
                "ocr": ocr_docs,
                "mode": "production",
                "stack_mode": stack_mode,
                "test_run_id": test_run_id if deep_mode else None,
            }
        )
        serve_health(orchestrator_port)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
