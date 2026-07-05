"""
Concurrent media upload probe for the AI interview API.

The upload endpoint requires a known interview session or a known processing
task. For a pure upload check, pass --session-id with one or more live sessions.
For an end-to-end smoke setup, use --create-sessions together with
--allow-cloud because start_interview triggers LLM and TTS.

Examples:
    python tools/media_upload_probe.py --session-id abc123 --requests 20 --concurrency 5
    python tools/media_upload_probe.py --allow-cloud --create-sessions --requests 5 --concurrency 1 --size-bytes 4096
"""

import argparse
import asyncio
import os
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass
class UploadResult:
    ok: bool
    latency_ms: float
    reason: str = ""
    session_id: str = ""
    url: str = ""
    bytes_sent: int = 0


def _base_urls(raw_urls: str) -> list[str]:
    urls = []
    for item in raw_urls.split(","):
        item = item.strip().rstrip("/")
        if not item:
            continue
        if item.isdigit():
            item = f"http://127.0.0.1:{item}"
        elif not item.startswith(("http://", "https://")):
            item = f"http://{item}"
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
        return False, "invalid_json", {}

    status = payload.get("status")
    if status and status not in {"success", "ok", "submitted", "pending"}:
        return False, f"app_{status}", payload
    return True, "", payload


async def _login_headers(client: httpx.AsyncClient, base_urls: list[str], index: int, args) -> dict:
    if not args.email or not args.password:
        return {}
    ok, reason, payload = await _request_json(
        client,
        "POST",
        _target(base_urls, index, "/api/user/login"),
        json={"email": args.email, "password": args.password},
    )
    if not ok:
        raise RuntimeError(f"login failed: {reason}")
    token = payload.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


async def _create_session(client: httpx.AsyncClient, base_urls: list[str], index: int, args) -> str:
    headers = await _login_headers(client, base_urls, index, args)
    ok, reason, payload = await _request_json(
        client,
        "POST",
        _target(base_urls, index, "/api/user/start_interview"),
        json={"language": args.language},
        headers=headers,
    )
    if not ok or not payload.get("session_id"):
        raise RuntimeError(f"start_interview failed: {reason or 'missing_session_id'}")
    return str(payload["session_id"])


async def _prepare_sessions(base_urls: list[str], args) -> tuple[list[str], list[str]]:
    provided = [item.strip() for item in args.session_id.split(",") if item.strip()]
    if provided:
        return provided, []
    if not args.create_sessions:
        raise SystemExit("Provide --session-id or use --create-sessions with --allow-cloud.")
    if not args.allow_cloud:
        raise SystemExit("--create-sessions calls start_interview and requires --allow-cloud.")

    count = 1 if args.reuse_created_session else args.requests
    limits = httpx.Limits(max_connections=max(1, min(args.concurrency, 10)))
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        created = []
        for index in range(count):
            created.append(await _create_session(client, base_urls, index, args))
    return created, created


async def _cancel_created_sessions(base_urls: list[str], session_ids: list[str], timeout: float) -> None:
    if not session_ids:
        return
    async with httpx.AsyncClient(timeout=timeout) as client:
        await asyncio.gather(
            *[
                _request_json(
                    client,
                    "POST",
                    _target(base_urls, index, "/api/user/cancel_interview"),
                    json={"session_id": session_id},
                )
                for index, session_id in enumerate(session_ids)
            ],
            return_exceptions=True,
        )


def _load_payload(args) -> bytes:
    if args.payload_file:
        with open(args.payload_file, "rb") as file:
            return file.read()
    if args.size_bytes < 4:
        return b"\x1a\x45\xdf\xa3"[: args.size_bytes]
    return b"\x1a\x45\xdf\xa3" + os.urandom(args.size_bytes - 4)


async def _upload_one(
    client: httpx.AsyncClient,
    base_urls: list[str],
    session_ids: list[str],
    payload: bytes,
    index: int,
    sem: asyncio.Semaphore,
    args,
) -> UploadResult:
    async with sem:
        session_id = session_ids[index % len(session_ids)]
        url = _target(base_urls, index, f"/api/user/upload_media?session_id={quote(session_id)}&ext={quote(args.ext)}")
        started = time.perf_counter()
        ok, reason, response_payload = await _request_json(
            client,
            "POST",
            url,
            content=payload,
            headers={"Content-Type": args.content_type},
        )
        latency_ms = (time.perf_counter() - started) * 1000
        if not ok:
            return UploadResult(False, latency_ms, reason, session_id, bytes_sent=len(payload))
        uploaded_url = str(response_payload.get("url") or "")
        if args.require_url and not uploaded_url:
            return UploadResult(False, latency_ms, "missing_url", session_id, bytes_sent=len(payload))
        return UploadResult(True, latency_ms, session_id=session_id, url=uploaded_url, bytes_sent=len(payload))


def _print_summary(args, target_count: int, elapsed: float, results: list[UploadResult]) -> None:
    ok_latencies = [item.latency_ms for item in results if item.ok]
    failed = len(results) - len(ok_latencies)
    reasons = Counter(item.reason or "unknown" for item in results if not item.ok)
    url_count = sum(1 for item in results if item.url)
    total_bytes = sum(item.bytes_sent for item in results)
    if ok_latencies:
        p95 = statistics.quantiles(ok_latencies, n=20)[18] if len(ok_latencies) >= 20 else max(ok_latencies)
        avg = statistics.mean(ok_latencies)
        max_latency = max(ok_latencies)
    else:
        avg = p95 = max_latency = 0.0

    print(f"targets={target_count} requests={args.requests} concurrency={args.concurrency} failed={failed}")
    if reasons:
        print("failure_reasons=" + ",".join(f"{reason}:{count}" for reason, count in reasons.items()))
    print(f"elapsed={elapsed:.2f}s throughput={args.requests / max(elapsed, 0.001):.1f} upload/s")
    print(f"latency_avg={avg:.1f}ms latency_p95={p95:.1f}ms latency_max={max_latency:.1f}ms")
    print(f"url_count={url_count} total_bytes={total_bytes}")


async def run(args) -> None:
    base_urls = _base_urls(args.base_url)
    session_ids, created_session_ids = await _prepare_sessions(base_urls, args)
    payload = _load_payload(args)
    sem = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=max(args.concurrency, 20))
    try:
        async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
            started = time.perf_counter()
            results = await asyncio.gather(
                *[
                    _upload_one(client, base_urls, session_ids, payload, index, sem, args)
                    for index in range(args.requests)
                ]
            )
            elapsed = time.perf_counter() - started
        _print_summary(args, len(base_urls), elapsed, results)
    finally:
        if args.cancel_created_sessions:
            await _cancel_created_sessions(base_urls, created_session_ids, args.timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a concurrent media upload probe.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="One or more comma-separated API base URLs.")
    parser.add_argument("--session-id", default="", help="Existing session id, or comma-separated session ids.")
    parser.add_argument("--create-sessions", action="store_true", help="Create sessions through start_interview before uploading.")
    parser.add_argument("--reuse-created-session", action="store_true", help="Create one session and reuse it for every upload.")
    parser.add_argument("--cancel-created-sessions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-cloud", action="store_true", help="Required when --create-sessions is used.")
    parser.add_argument("--email", default="", help="Optional login email used when creating sessions.")
    parser.add_argument("--password", default="", help="Optional login password used when creating sessions.")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--ext", default="mkv")
    parser.add_argument("--content-type", default="video/x-matroska")
    parser.add_argument("--size-bytes", type=int, default=4096)
    parser.add_argument("--payload-file", default="", help="Upload this file instead of generated fake Matroska bytes.")
    parser.add_argument("--require-url", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if args.requests < 1:
        parser.error("--requests must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.size_bytes < 0:
        parser.error("--size-bytes must be >= 0")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
