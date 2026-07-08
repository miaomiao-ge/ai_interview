import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / ".runtime"
WORKER_PID_FILE = RUNTIME_DIR / "worker.pid"


def load_project_env(override: bool = False) -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=override)


def run_step(command: list[str], label: str, check: bool = True) -> subprocess.CompletedProcess:
    print(f"[deploy] {label}: {' '.join(command)}", flush=True)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(command, cwd=PROJECT_ROOT, env=env, check=check)


def run_install_deps(args) -> None:
    run_step([args.python, "-m", "pip", "install", "-r", "requirements.txt"], "install Python dependencies")


def run_bootstrap_db(args) -> None:
    command = [args.python, "tools/bootstrap_database.py"]
    if args.write_env:
        command.append("--write-env")
    run_step(command, "bootstrap database")
    if args.write_env:
        load_project_env(override=True)


def run_migrations(args) -> None:
    run_step([args.python, "tools/migrate_db.py"], "migrate database")
    run_step([args.python, "tools/migrate_db.py", "--check-only"], "check database schema")


def run_import_questions(args) -> None:
    command = [args.python, "tools/import_questions.py", "--file", args.questions_file]
    run_step(command, "import questions")


def run_sync_students(args) -> None:
    command = [args.python, "sync_xidian_students.py", "--year", str(args.year)]
    if args.application_nos:
        command.extend(["--application-nos", args.application_nos])
    if args.student_limit is not None:
        command.extend(["--limit", str(args.student_limit)])
    if args.skip_photo:
        command.append("--skip-photo")
    run_step(command, "sync Xidian students")


def start_api(args) -> None:
    command = [args.python, "tools/start_multi_instance.py", "--ports", args.ports]
    if args.access_log:
        command.append("--access-log")
    run_step(command, "start API instances")


def read_pid_file(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def start_worker(args) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    existing_pid = read_pid_file(WORKER_PID_FILE)
    if existing_pid:
        print(f"[deploy] worker pid file exists: {WORKER_PID_FILE} pid={existing_pid}", flush=True)
        return

    stdout_path = RUNTIME_DIR / "worker.out.log"
    stderr_path = RUNTIME_DIR / "worker.err.log"
    stdout_file = stdout_path.open("ab")
    stderr_file = stderr_path.open("ab")
    env = os.environ.copy()
    env["WORKER_NODE_ID"] = args.worker_node_id
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    command = [args.python, "-m", "core.interview_worker", "--workers", str(args.worker_concurrency)]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)

    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        stdout=stdout_file,
        stderr=stderr_file,
        creationflags=creationflags,
    )
    stdout_file.close()
    stderr_file.close()
    WORKER_PID_FILE.write_text(str(process.pid), encoding="utf-8")
    print(
        json.dumps(
            {
                "worker": "started",
                "pid": process.pid,
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


def wait_for_ready(args) -> None:
    first_port = args.ports.split(",", 1)[0].strip()
    url = f"http://127.0.0.1:{first_port}/ready"
    deadline = time.time() + args.ready_timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                payload = response.read().decode("utf-8", errors="replace")
                if response.status == 200:
                    print(f"[deploy] ready ok: {payload}", flush=True)
                    return
                last_error = payload
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"API readiness check failed: {url}; last_error={last_error}")


def run_all(args) -> None:
    if args.install_deps:
        run_install_deps(args)
    if not args.skip_bootstrap:
        run_bootstrap_db(args)
    run_migrations(args)
    if not args.skip_questions:
        run_import_questions(args)
    if not args.skip_student_sync:
        run_sync_students(args)
    if not args.skip_api:
        start_api(args)
    if not args.skip_worker:
        start_worker(args)
    if not args.skip_ready_check and not args.skip_api:
        wait_for_ready(args)


def parse_args():
    parser = argparse.ArgumentParser(description="AI Interview deployment helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common_options(target):
        target.add_argument("--python", default=sys.executable, help="Python executable to use.")
        target.add_argument("--install-deps", action="store_true", help="Install requirements.txt before running the step.")
        target.add_argument("--write-env", action="store_true", help="Allow bootstrap to append generated MYSQL_URL to .env.")
        target.add_argument("--questions-file", default=str(PROJECT_ROOT / "questions.xlsx"), help="questions.xlsx path.")
        target.add_argument("--year", type=int, default=2026, help="Xidian application year.")
        target.add_argument("--application-nos", default="", help="Comma-separated application numbers for student sync.")
        target.add_argument("--student-limit", type=int, default=None, help="Limit student sync count.")
        target.add_argument("--skip-photo", action="store_true", help="Skip official photo upload during student sync.")
        target.add_argument("--ports", default="8001,8002,8003,8004", help="Comma-separated API ports.")
        target.add_argument("--worker-node-id", default="worker-001", help="Worker node id.")
        target.add_argument("--worker-concurrency", type=int, default=int(os.getenv("WORKER_CONCURRENCY", "1")))
        target.add_argument("--access-log", action="store_true", help="Enable API access log.")
        target.add_argument("--ready-timeout", type=float, default=60.0, help="Seconds to wait for /ready.")

    all_parser = subparsers.add_parser("all", help="Run full deployment flow.")
    add_common_options(all_parser)
    all_parser.add_argument("--skip-bootstrap", action="store_true", help="Skip database creation/user grant step.")
    all_parser.add_argument("--skip-questions", action="store_true", help="Skip questions.xlsx import.")
    all_parser.add_argument("--skip-student-sync", action="store_true", help="Skip Xidian student sync.")
    all_parser.add_argument("--skip-api", action="store_true", help="Skip API process startup.")
    all_parser.add_argument("--skip-worker", action="store_true", help="Skip worker process startup.")
    all_parser.add_argument("--skip-ready-check", action="store_true", help="Skip /ready check.")

    install_parser = subparsers.add_parser("install-deps", help="Install Python dependencies from requirements.txt.")
    add_common_options(install_parser)
    bootstrap_parser = subparsers.add_parser("bootstrap-db", help="Create database and app user.")
    add_common_options(bootstrap_parser)
    migrate_parser = subparsers.add_parser("migrate", help="Run database migrations.")
    add_common_options(migrate_parser)
    questions_parser = subparsers.add_parser("import-questions", help="Import questions.xlsx.")
    add_common_options(questions_parser)
    students_parser = subparsers.add_parser("sync-students", help="Sync Xidian students.")
    add_common_options(students_parser)
    api_parser = subparsers.add_parser("start-api", help="Start API instances.")
    add_common_options(api_parser)
    worker_parser = subparsers.add_parser("start-worker", help="Start background worker.")
    add_common_options(worker_parser)
    ready_parser = subparsers.add_parser("ready", help="Wait for API readiness.")
    add_common_options(ready_parser)
    return parser.parse_args()


def main() -> int:
    load_project_env()
    args = parse_args()
    if args.command == "all":
        run_all(args)
    elif args.command == "install-deps":
        run_install_deps(args)
    elif args.command == "bootstrap-db":
        run_bootstrap_db(args)
    elif args.command == "migrate":
        run_migrations(args)
    elif args.command == "import-questions":
        run_import_questions(args)
    elif args.command == "sync-students":
        run_sync_students(args)
    elif args.command == "start-api":
        start_api(args)
    elif args.command == "start-worker":
        start_worker(args)
    elif args.command == "ready":
        wait_for_ready(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
