"""
Start several local API instances on different ports.

Example:
    python tools/start_multi_instance.py --ports 8001,8002,8003,8004
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT_DIR / ".runtime" / "multi_instance"
PID_FILE = RUNTIME_DIR / "pids.json"


def parse_ports(raw_ports: str) -> list[int]:
    ports: list[int] = []
    for item in raw_ports.split(","):
        item = item.strip()
        if not item:
            continue
        ports.append(int(item))
    if not ports:
        raise ValueError("At least one port is required.")
    return ports


def wait_for_health(port: int, timeout_seconds: float) -> bool:
    url = f"http://127.0.0.1:{port}/health"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.5)
    return False


def start_instance(python_exe: str, host: str, port: int, access_log: bool) -> dict:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    stdout_path = RUNTIME_DIR / f"api-{port}.out.log"
    stderr_path = RUNTIME_DIR / f"api-{port}.err.log"
    stdout_file = stdout_path.open("ab")
    stderr_file = stderr_path.open("ab")

    env = os.environ.copy()
    env["WORKER_NODE_ID"] = f"api-{port}"
    env["UVICORN_RELOAD"] = "0"
    env["AUTO_STOP_PREVIOUS_SERVER"] = "0"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    cmd.append("--access-log" if access_log else "--no-access-log")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)

    process = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        env=env,
        stdout=stdout_file,
        stderr=stderr_file,
        creationflags=creationflags,
    )
    stdout_file.close()
    stderr_file.close()
    return {
        "port": port,
        "pid": process.pid,
        "url": f"http://127.0.0.1:{port}",
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Start multiple local API instances.")
    parser.add_argument("--ports", default="8001,8002,8003,8004", help="Comma-separated ports to start.")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host for uvicorn.")
    parser.add_argument("--python", default=sys.executable, help="Python executable to use.")
    parser.add_argument("--health-timeout", type=float, default=20.0, help="Seconds to wait for each instance.")
    parser.add_argument("--access-log", action="store_true", help="Enable per-request uvicorn access logs.")
    args = parser.parse_args()

    instances = []
    for port in parse_ports(args.ports):
        info = start_instance(args.python, args.host, port, args.access_log)
        info["healthy"] = wait_for_health(port, args.health_timeout)
        instances.append(info)
        status = "ok" if info["healthy"] else "not_ready"
        print(f"started port={port} pid={info['pid']} health={status}")

    PID_FILE.write_text(json.dumps(instances, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"pid_file={PID_FILE}")
    print("probe_url=" + ",".join(f"http://127.0.0.1:{item['port']}/health" for item in instances))


if __name__ == "__main__":
    main()
