from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
DOCKER_DESKTOP_PATH = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap a brand-new Windows machine for the local demo.")
    parser.add_argument("--skip-pip", action="store_true", help="Skip `pip install -r requirements.txt`.")
    parser.add_argument("--skip-demo-sql", action="store_true", help="Skip importing the git-tracked demo SQL snapshot.")
    parser.add_argument(
        "--demo-sql",
        default="demo/demo_snapshot.sql",
        help="Path to the demo SQL file used when --skip-demo-sql is not set.",
    )
    return parser.parse_args()


def run(cmd: list[str], label: str) -> None:
    print(f"[step] {label}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def ensure_env_file() -> None:
    if ENV_FILE.exists():
        print(f"[ok] Reusing existing .env: {ENV_FILE}")
        return
    shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
    print(f"[ok] Created .env from template: {ENV_FILE}")


def ensure_venv() -> Path:
    if VENV_PY.exists():
        print(f"[ok] Reusing virtual environment: {VENV_PY}")
        return VENV_PY

    print("[step] Creating virtual environment")
    subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], cwd=ROOT, check=True)
    if not VENV_PY.exists():
        raise RuntimeError(f"Virtual environment python not found: {VENV_PY}")
    return VENV_PY


def ensure_docker(py: Path) -> None:
    probe = subprocess.run(["docker", "info"], cwd=ROOT, capture_output=True, text=True)
    if probe.returncode == 0:
        print("[ok] Docker is already running.")
        return

    if not DOCKER_DESKTOP_PATH.exists():
        raise RuntimeError(
            "Docker Desktop is not running and was not found at the default path. "
            "Install Docker Desktop first."
        )

    print("[step] Starting Docker Desktop")
    subprocess.Popen([str(DOCKER_DESKTOP_PATH)], cwd=ROOT)
    run([str(py), "scripts/wait_for_docker.py"], "Waiting for Docker Desktop")


def main() -> int:
    args = parse_args()
    if not ENV_EXAMPLE.exists():
        raise FileNotFoundError(ENV_EXAMPLE)

    ensure_env_file()
    py = ensure_venv()

    if not args.skip_pip:
        run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"], "Installing Python dependencies")

    run([str(py), "scripts/check_env.py"], "Validating .env")
    ensure_docker(py)
    run(["docker", "compose", "up", "-d", "mysql", "mailpit"], "Starting MySQL and Mailpit")
    run([str(py), "scripts/apply_schema.py"], "Applying schema")

    if not args.skip_demo_sql:
        run([str(py), "scripts/import_demo_sql.py", "--sql-file", args.demo_sql], "Importing git-tracked demo SQL")

    print("[done] Fresh machine bootstrap completed.")
    print("[next] Double-click start.cmd for the live local demo, or run start_demo.bat manually.")
    print("[note] If you want real Dify, SMTP, or Feishu behavior, fill the optional fields in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
