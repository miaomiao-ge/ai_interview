"""
Stop API instances started by tools/start_multi_instance.py.

Example:
    python tools/stop_multi_instance.py
"""

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
PID_FILE = ROOT_DIR / ".runtime" / "multi_instance" / "pids.json"


def stop_pid(pid: int, force: bool) -> bool:
    try:
        if os.name == "nt":
            command = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                command.append("/F")
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            return result.returncode == 0
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Stop local API instances.")
    parser.add_argument("--force", action="store_true", help="Force stop on Windows with taskkill /F.")
    args = parser.parse_args()

    if not PID_FILE.exists():
        print(f"pid_file_not_found={PID_FILE}")
        return

    instances = json.loads(PID_FILE.read_text(encoding="utf-8"))
    for item in instances:
        pid = int(item.get("pid") or 0)
        port = item.get("port")
        if not pid:
            continue
        stopped = stop_pid(pid, args.force)
        status = "stopped" if stopped else "not_running_or_failed"
        print(f"port={port} pid={pid} status={status}")


if __name__ == "__main__":
    main()
