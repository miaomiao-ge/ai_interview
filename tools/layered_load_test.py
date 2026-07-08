"""
Layered load tester for the AI interview API.

Safe stages that do not consume cloud quota:
    ready, health, home, login

Cloud-consuming stage:
    start_interview requires --allow-cloud because it triggers LLM and TTS.

Examples:
    python tools/layered_load_test.py --stage ready --requests 300 --concurrency 100
    python tools/layered_load_test.py --stage home --requests 300 --concurrency 100
    python tools/layered_load_test.py --stage login --passport-no P1234567 --password 123456 --requests 100 --concurrency 20
    python tools/layered_load_test.py --stage start_interview --allow-cloud --requests 10 --concurrency 2
"""

import argparse
import asyncio
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

import httpx


SAFE_STAGES = {"ready", "health", "home", "login"}
CLOUD_STAGES = {"start_interview"}


@dataclass
class Result:
    ok: bool
    latency_ms: float
    reason: str = ""
    session_id: str = ""


def _base_urls(raw_urls: str) -> list[str]:
    urls = []
    for item in raw_urls.split(","):
        item = item.strip().rstrip("/")
        if not item:
            continue
        if not item.startswith(("http://", "https://")):
            item = f"http://127.0.0.1:{item}"
        urls.append(item)
    if not urls:
        raise ValueError("At least one base URL is required.")
    return urls


def _target(base_urls: list[str], index: int, path: str) -> str:
    return f"{base_urls[index % len(base_urls)]}{path}"


async def _request_json(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> tuple[bool, str, dict]:
    try:
        response = await client.request(method, url, **kwargs)
    except Exception as exc:
        return False, type(exc).__name__, {}

    if response.status_code != 200:
        return False, f"status_{response.status_code}", {}

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    status = payload.get("status")
    if status and status not in {"success", "ok", "submitted", "pending"}:
        return False, f"app_{status}", payload
    return True, "", payload


async def _run_ready(client: httpx.AsyncClient, base_urls: list[str], index: int) -> Result:
    return await _run_get(client, _target(base_urls, index, "/ready"))


async def _run_health(client: httpx.AsyncClient, base_urls: list[str], index: int) -> Result:
    return await _run_get(client, _target(base_urls, index, "/health"))


async def _run_home(client: httpx.AsyncClient, base_urls: list[str], index: int) -> Result:
    return await _run_get(client, _target(base_urls, index, "/"))


async def _run_get(client: httpx.AsyncClient, url: str) -> Result:
    started = time.perf_counter()
    try:
        response = await client.get(url)
        latency_ms = (time.perf_counter() - started) * 1000
        if response.status_code == 200:
            return Result(True, latency_ms)
        return Result(False, latency_ms, f"status_{response.status_code}")
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return Result(False, latency_ms, type(exc).__name__)


async def _run_login(client: httpx.AsyncClient, base_urls: list[str], index: int, args) -> Result:
    started = time.perf_counter()
    ok, reason, payload = await _request_json(
        client,
        "POST",
        _target(base_urls, index, "/api/user/login"),
        json={"passport_no": args.passport_no, "password": args.password},
    )
    latency_ms = (time.perf_counter() - started) * 1000
    if ok and payload.get("token"):
        return Result(True, latency_ms)
    return Result(False, latency_ms, reason or "missing_token")


async def _run_start_interview(client: httpx.AsyncClient, base_urls: list[str], index: int, args) -> Result:
    started = time.perf_counter()
    headers = {}
    if args.passport_no and args.password:
        ok, reason, payload = await _request_json(
            client,
            "POST",
            _target(base_urls, index, "/api/user/login"),
            json={"passport_no": args.passport_no, "password": args.password},
        )
        if not ok:
            latency_ms = (time.perf_counter() - started) * 1000
            return Result(False, latency_ms, f"login_{reason}")
        token = payload.get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"

    ok, reason, payload = await _request_json(
        client,
        "POST",
        _target(base_urls, index, "/api/user/start_interview"),
        json={"language": args.language},
        headers=headers,
    )
    latency_ms = (time.perf_counter() - started) * 1000
    session_id = str(payload.get("session_id") or "")
    if not ok or not session_id:
        return Result(False, latency_ms, reason or "missing_session_id")

    if args.cancel_sessions:
        await _request_json(
            client,
            "POST",
            _target(base_urls, index, "/api/user/cancel_interview"),
            json={"session_id": session_id},
            headers=headers,
        )
    return Result(True, latency_ms, session_id=session_id)


async def _run_one(client: httpx.AsyncClient, base_urls: list[str], index: int, sem: asyncio.Semaphore, args) -> Result:
    async with sem:
        if args.stage == "ready":
            return await _run_ready(client, base_urls, index)
        if args.stage == "health":
            return await _run_health(client, base_urls, index)
        if args.stage == "home":
            return await _run_home(client, base_urls, index)
        if args.stage == "login":
            return await _run_login(client, base_urls, index, args)
        if args.stage == "start_interview":
            return await _run_start_interview(client, base_urls, index, args)
        raise ValueError(f"Unsupported stage: {args.stage}")


def _print_summary(args, target_count: int, elapsed: float, results: list[Result]) -> None:
    ok_latencies = [item.latency_ms for item in results if item.ok]
    failed = len(results) - len(ok_latencies)
    reasons = Counter(item.reason or "unknown" for item in results if not item.ok)
    if ok_latencies:
        p95 = statistics.quantiles(ok_latencies, n=20)[18] if len(ok_latencies) >= 20 else max(ok_latencies)
        avg = statistics.mean(ok_latencies)
        max_latency = max(ok_latencies)
    else:
        avg = p95 = max_latency = 0.0

    print(f"stage={args.stage} targets={target_count} requests={args.requests} concurrency={args.concurrency} failed={failed}")
    if reasons:
        print("failure_reasons=" + ",".join(f"{reason}:{count}" for reason, count in reasons.items()))
    print(f"elapsed={elapsed:.2f}s throughput={args.requests / max(elapsed, 0.001):.1f} req/s")
    print(f"latency_avg={avg:.1f}ms latency_p95={p95:.1f}ms latency_max={max_latency:.1f}ms")


async def run(args) -> None:
    if args.stage in CLOUD_STAGES and not args.allow_cloud:
        raise SystemExit(f"Stage {args.stage} consumes cloud quota. Re-run with --allow-cloud if you really want it.")
    if args.stage == "login" and (not args.passport_no or not args.password):
        raise SystemExit("Stage login requires --passport-no and --password.")

    base_urls = _base_urls(args.base_url)
    sem = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=max(args.concurrency, 20))
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        started = time.perf_counter()
        results = await asyncio.gather(*[_run_one(client, base_urls, index, sem, args) for index in range(args.requests)])
        elapsed = time.perf_counter() - started

    _print_summary(args, len(base_urls), elapsed, results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run layered load tests against the AI interview API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="One or more comma-separated API base URLs.")
    parser.add_argument("--stage", choices=sorted(SAFE_STAGES | CLOUD_STAGES), default="ready")
    parser.add_argument("--requests", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--passport-no",
        "--email",
        dest="passport_no",
        default="",
        help="Login passport number. --email is kept as a compatibility alias.",
    )
    parser.add_argument("--password", default="")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--allow-cloud", action="store_true", help="Allow stages that call LLM/TTS/ASR/OSS.")
    parser.add_argument("--cancel-sessions", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
