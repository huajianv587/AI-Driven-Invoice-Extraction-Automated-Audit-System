import subprocess
import sys
import time


def _run_docker_info():
    return subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=5,
    )


def main():
    timeout_sec = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    deadline = time.time() + timeout_sec
    last_error = None

    while time.time() < deadline:
        try:
            result = _run_docker_info()
            if result.returncode == 0:
                print("[ok] Docker is ready.")
                return
            last_error = (result.stderr or "docker info failed").strip()
        except subprocess.TimeoutExpired:
            last_error = "docker info timed out after 5s"
        except FileNotFoundError:
            last_error = "docker command not found"

        print(f"[wait] Docker not ready yet: {last_error}")
        time.sleep(3)

    raise RuntimeError(f"Docker did not become ready in time ({timeout_sec}s): {last_error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        sys.exit(1)
