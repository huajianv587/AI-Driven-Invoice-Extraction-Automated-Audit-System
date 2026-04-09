import subprocess
import sys
import time


def main():
    deadline = time.time() + 180
    last_error = None

    while time.time() < deadline:
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode == 0:
            print("[ok] Docker is ready.")
            return

        last_error = (result.stderr or "docker info failed").strip()
        print(f"[wait] Docker not ready yet: {last_error}")
        time.sleep(3)

    raise RuntimeError(f"Docker did not become ready in time: {last_error}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[error] {exc}")
        sys.exit(1)
