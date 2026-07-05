import mimetypes
import os
import atexit
import asyncio
import signal
import subprocess
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from core.config import APP_ENV, ASR_DEBUG_LOG, DB_AUTO_MIGRATE_ON_STARTUP, WORKER_NODE_ID
from core.concurrency_guard import get_capacity_snapshot
from core.database import database_ready, init_db
from core.interview_job_service import get_worker_queue_snapshot
from core.redis_utils import ensure_redis_available, redis_available
from routers import admin_api, face_api, user_api


def register_static_mime_types():
    # Ensure ES module assets are returned with a JavaScript MIME type.
    mimetypes.add_type("text/javascript", ".mjs")


register_static_mime_types()

app = FastAPI(title="西电 AI 面试系统")
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(user_api.router, prefix="/api/user", tags=["用户端接口"])
app.include_router(admin_api.router, prefix="/api/admin", tags=["管理端接口"])
app.include_router(face_api.router, prefix="/api/face", tags=["人脸核验与监考"])

class CachedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers.setdefault("Cache-Control", "public, max-age=86400")
        return response


base_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/static/user", CachedStaticFiles(directory=os.path.join(base_dir, "frontend", "user")), name="user_static")
app.mount("/static/admin", CachedStaticFiles(directory=os.path.join(base_dir, "frontend", "admin")), name="admin_static")

media_dir = os.path.join(base_dir, "media")
os.makedirs(media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")


@app.on_event("startup")
async def startup_event():
    init_db()
    if APP_ENV == "production":
        await asyncio.to_thread(ensure_redis_available)
    print(f"系统启动成功，数据库已连接。PID={os.getpid()} ASR_DEBUG_LOG={int(ASR_DEBUG_LOG)}", flush=True)


@app.get("/", response_class=HTMLResponse, tags=["页面路由"])
async def index():
    html_path = os.path.join(base_dir, "frontend", "user", "index.html")
    with open(html_path, "r", encoding="utf-8") as file:
        return file.read()


@app.get("/admin", response_class=HTMLResponse, tags=["页面路由"])
async def admin_page():
    html_path = os.path.join(base_dir, "frontend", "admin", "admin.html")
    with open(html_path, "r", encoding="utf-8") as file:
        return Response(
            content=file.read(),
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )


@app.get("/health", tags=["系统状态"])
async def health_check():
    redis_result, db_ok, capacity_result, worker_queue_result = await asyncio.gather(
        asyncio.to_thread(redis_available),
        asyncio.to_thread(database_ready),
        asyncio.to_thread(get_capacity_snapshot),
        asyncio.to_thread(get_worker_queue_snapshot),
        return_exceptions=True,
    )
    redis_ok = redis_result is True
    capacity = capacity_result if not isinstance(capacity_result, Exception) else {"error": str(capacity_result)}
    worker_queue = worker_queue_result if not isinstance(worker_queue_result, Exception) else {"error": str(worker_queue_result)}
    return {
        "status": "ok" if redis_ok and db_ok is True else "degraded",
        "worker_node_id": WORKER_NODE_ID,
        "database": "ok" if db_ok is True else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
        "capacity": capacity,
        "worker_queue": worker_queue,
    }


@app.get("/ready", tags=["system"])
async def ready_check():
    redis_result, db_ok = await asyncio.gather(
        asyncio.to_thread(redis_available),
        asyncio.to_thread(database_ready),
        return_exceptions=True,
    )
    redis_ok = redis_result is True
    ready = redis_ok and db_ok is True
    payload = {
        "status": "ok" if ready else "unavailable",
        "worker_node_id": WORKER_NODE_ID,
        "database": "ok" if db_ok is True else "unavailable",
        "redis": "ok" if redis_ok else "unavailable",
    }
    return JSONResponse(payload, status_code=200 if ready else 503)


async def help_center_page():
    html_path = os.path.join(base_dir, "frontend", "user", "help.html")
    with open(html_path, "r", encoding="utf-8") as file:
        return Response(
            content=file.read(),
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )


app.add_api_route("/help", help_center_page, methods=["GET"], response_class=HTMLResponse, tags=["pages"])
app.add_api_route("/help-center", help_center_page, methods=["GET"], response_class=HTMLResponse, tags=["pages"])


runtime_dir = os.path.join(base_dir, ".runtime")
server_pid_file = os.path.join(runtime_dir, "server.pid")


def _env_enabled(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _read_server_pid() -> Optional[int]:
    try:
        with open(server_pid_file, "r", encoding="utf-8") as file:
            return int(file.read().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _get_windows_command_line(pid: int) -> str:
    if os.name != "nt":
        return ""
    command = (
        "Get-CimInstance Win32_Process -Filter \"ProcessId={0}\" "
        "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty CommandLine"
    ).format(pid)
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or "").strip()


def _looks_like_project_server(command_line: str) -> bool:
    normalized = command_line.replace("\\", "/").lower()
    project_path = base_dir.replace("\\", "/").lower()
    return "python" in normalized and (
        f"{project_path}/main.py" in normalized
        or normalized.endswith(" main.py")
        or ' main.py"' in normalized
    )


def _stop_previous_project_server() -> None:
    if not _env_enabled("AUTO_STOP_PREVIOUS_SERVER", "1"):
        return

    previous_pid = _read_server_pid()
    if not previous_pid or previous_pid == os.getpid():
        return

    command_line = _get_windows_command_line(previous_pid)
    if not command_line:
        return
    if not _looks_like_project_server(command_line):
        print(f"检测到旧 PID 文件，但 PID={previous_pid} 已不是本项目服务，已忽略。", flush=True)
        return

    print(f"检测到上次遗留的本项目服务 PID={previous_pid}，正在自动关闭...", flush=True)
    try:
        os.kill(previous_pid, signal.SIGTERM)
    except OSError:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(previous_pid), "/F"], capture_output=True, text=True, check=False)

    for _ in range(20):
        if not _get_windows_command_line(previous_pid):
            break
        time.sleep(0.1)


def _write_server_pid() -> None:
    os.makedirs(runtime_dir, exist_ok=True)
    with open(server_pid_file, "w", encoding="utf-8") as file:
        file.write(str(os.getpid()))


def _cleanup_server_pid() -> None:
    if _read_server_pid() != os.getpid():
        return
    try:
        os.remove(server_pid_file)
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    _stop_previous_project_server()
    _write_server_pid()
    atexit.register(_cleanup_server_pid)

    reload_enabled = os.getenv("UVICORN_RELOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
    access_log_enabled = os.getenv("UVICORN_ACCESS_LOG", "0").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("UVICORN_PORT", "8000")),
        reload=reload_enabled,
        access_log=access_log_enabled,
    )
