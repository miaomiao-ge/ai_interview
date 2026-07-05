"""
Worker queue probe for the AI interview API.

Default mode is synthetic and does not call ASR/TTS/LLM/OSS: it submits
generated session ids to /api/user/end_interview and optionally polls
/api/user/interview_status. This validates enqueue/idempotency/status visibility.

Full-chain mode creates real interview sessions and uploads fake media before
enqueueing. It requires --allow-cloud because start_interview triggers LLM/TTS
and media upload writes to OSS.

Examples:
    python tools/worker_queue_probe.py --tasks 10 --duplicates 2 --poll-timeout 30
    python tools/worker_queue_probe.py --full-chain --allow-cloud --tasks 5 --concurrency 2 --poll-timeout 180
"""

import argparse
import asyncio
import os
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx


TERMINAL_STATUSES = {"success", "partial_success", "failed"}


@dataclass
class RequestResult:
    ok: bool
    latency_ms: float
    session_id: str
    reason: str = ""
    status: str = ""
    job_id: str = ""


@dataclass
class SetupResult:
    ok: bool
    session_id: str
    reason: str = ""
    media_url: str = ""


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
    if status and status not in {"success", "ok", "submitted", "pending", "running", "partial_success", "failed"}:
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


def _fake_media_payload(size_bytes: int) -> bytes:
    if size_bytes < 4:
        return b"\x1a\x45\xdf\xa3"[:size_bytes]
    return b"\x1a\x45\xdf\xa3" + os.urandom(size_bytes - 4)


async def _upload_media(client: httpx.AsyncClient, base_urls: list[str], session_id: str, index: int, payload: bytes, args) -> str:
    ok, reason, response_payload = await _request_json(
        client,
        "POST",
        _target(base_urls, index, f"/api/user/upload_media?session_id={quote(session_id)}&ext={args.ext}"),
        content=payload,
        headers={"Content-Type": args.content_type},
    )
    if not ok or not response_payload.get("url"):
        raise RuntimeError(f"upload_media failed: {reason or 'missing_url'}")
    return str(response_payload["url"])


async def _setup_full_chain_session(
    client: httpx.AsyncClient,
    base_urls: list[str],
    index: int,
    payload: bytes,
    args,
    sem: asyncio.Semaphore,
) -> SetupResult:
    async with sem:
        session_id = ""
        try:
            session_id = await _create_session(client, base_urls, index, args)
            media_url = await _upload_media(client, base_urls, session_id, index, payload, args)
            return SetupResult(True, session_id=session_id, media_url=media_url)
        except Exception as exc:
            return SetupResult(False, session_id=session_id, reason=str(exc))


async def _cancel_sessions(base_urls: list[str], session_ids: list[str], timeout: float) -> None:
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


async def _prepare_sessions(base_urls: list[str], args) -> tuple[list[str], list[SetupResult]]:
    provided = [item.strip() for item in args.session_id.split(",") if item.strip()]
    if provided:
        return provided, [SetupResult(True, session_id=item) for item in provided]

    if not args.full_chain:
        prefix = args.synthetic_prefix.strip() or "probe"
        timestamp = int(time.time() * 1000)
        sessions = [f"{prefix}_{timestamp}_{index}_{uuid4().hex[:6]}"[:48] for index in range(args.tasks)]
        return sessions, [SetupResult(True, session_id=item) for item in sessions]

    if not args.allow_cloud:
        raise SystemExit("--full-chain creates sessions and uploads media; confirm with --allow-cloud.")

    payload = _fake_media_payload(args.media_size_bytes)
    sem = asyncio.Semaphore(max(1, min(args.concurrency, 10)))
    limits = httpx.Limits(max_connections=max(1, min(args.concurrency, 10)))
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        setup_results = await asyncio.gather(
            *[_setup_full_chain_session(client, base_urls, index, payload, args, sem) for index in range(args.tasks)]
        )
    sessions = [item.session_id for item in setup_results if item.ok and item.session_id]
    if not sessions:
        reasons = Counter(item.reason or "unknown" for item in setup_results if not item.ok)
        raise SystemExit("No sessions prepared. setup_failure_reasons=" + ",".join(f"{k}:{v}" for k, v in reasons.items()))
    return sessions, setup_results


async def _enqueue_once(
    client: httpx.AsyncClient,
    base_urls: list[str],
    session_id: str,
    request_index: int,
    sem: asyncio.Semaphore,
    headers: dict,
) -> RequestResult:
    async with sem:
        started = time.perf_counter()
        ok, reason, payload = await _request_json(
            client,
            "POST",
            _target(base_urls, request_index, "/api/user/end_interview"),
            json={"session_id": session_id},
            headers=headers,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        if not ok:
            return RequestResult(False, latency_ms, session_id, reason=reason)
        return RequestResult(
            True,
            latency_ms,
            session_id,
            status=str(payload.get("status") or payload.get("job_status") or ""),
            job_id=str(payload.get("job_id") or ""),
        )


async def _poll_status(client: httpx.AsyncClient, base_urls: list[str], session_id: str, index: int) -> dict:
    ok, reason, payload = await _request_json(
        client,
        "GET",
        _target(base_urls, index, f"/api/user/interview_status?session_id={quote(session_id)}"),
    )
    if not ok:
        return {"status": "probe_error", "error": reason}
    return payload


async def _poll_until_done(base_urls: list[str], sessions: list[str], args) -> dict[str, dict]:
    if args.poll_timeout <= 0:
        return {}
    deadline = time.monotonic() + args.poll_timeout
    latest = {session_id: {"status": "not_polled"} for session_id in sessions}
    async with httpx.AsyncClient(timeout=args.timeout) as client:
        while True:
            latest_list = await asyncio.gather(
                *[_poll_status(client, base_urls, session_id, index) for index, session_id in enumerate(sessions)]
            )
            latest = dict(zip(sessions, latest_list))
            if all(str(item.get("status")) in TERMINAL_STATUSES for item in latest.values()):
                return latest
            if time.monotonic() >= deadline:
                return latest
            await asyncio.sleep(args.poll_interval)


def _print_setup_summary(setup_results: list[SetupResult]) -> None:
    failed = [item for item in setup_results if not item.ok]
    media_count = sum(1 for item in setup_results if item.media_url)
    print(f"setup_sessions={len(setup_results)} setup_failed={len(failed)} media_url_count={media_count}")
    if failed:
        reasons = Counter(item.reason or "unknown" for item in failed)
        print("setup_failure_reasons=" + ",".join(f"{reason}:{count}" for reason, count in reasons.items()))


def _print_enqueue_summary(args, target_count: int, elapsed: float, results: list[RequestResult]) -> None:
    ok_latencies = [item.latency_ms for item in results if item.ok]
    failed = len(results) - len(ok_latencies)
    reasons = Counter(item.reason or "unknown" for item in results if not item.ok)
    status_counts = Counter(item.status or "unknown" for item in results if item.ok)
    job_ids_by_session = defaultdict(set)
    for item in results:
        if item.ok and item.job_id:
            job_ids_by_session[item.session_id].add(item.job_id)
    duplicate_job_conflicts = sum(1 for ids in job_ids_by_session.values() if len(ids) > 1)
    if ok_latencies:
        p95 = statistics.quantiles(ok_latencies, n=20)[18] if len(ok_latencies) >= 20 else max(ok_latencies)
        avg = statistics.mean(ok_latencies)
        max_latency = max(ok_latencies)
    else:
        avg = p95 = max_latency = 0.0

    print(
        f"targets={target_count} tasks={args.tasks} duplicates={args.duplicates} "
        f"enqueue_requests={len(results)} concurrency={args.concurrency} failed={failed}"
    )
    if reasons:
        print("failure_reasons=" + ",".join(f"{reason}:{count}" for reason, count in reasons.items()))
    print("enqueue_status_counts=" + ",".join(f"{status}:{count}" for status, count in status_counts.items()))
    print(f"duplicate_job_conflicts={duplicate_job_conflicts}")
    print(f"elapsed={elapsed:.2f}s throughput={len(results) / max(elapsed, 0.001):.1f} enqueue/s")
    print(f"latency_avg={avg:.1f}ms latency_p95={p95:.1f}ms latency_max={max_latency:.1f}ms")


def _print_poll_summary(statuses: dict[str, dict]) -> None:
    if not statuses:
        print("poll_skipped=true")
        return
    counts = Counter(str(item.get("status") or "unknown") for item in statuses.values())
    print("final_status_counts=" + ",".join(f"{status}:{count}" for status, count in counts.items()))
    for session_id, payload in list(statuses.items())[:5]:
        status = payload.get("status")
        job_status = payload.get("job_status", "")
        retry_count = payload.get("retry_count", "")
        error = payload.get("error") or payload.get("archive_error") or ""
        print(f"status_sample session_id={session_id} status={status} job_status={job_status} retry_count={retry_count} error={str(error)[:100]}")


async def run(args) -> None:
    base_urls = _base_urls(args.base_url)
    sessions, setup_results = await _prepare_sessions(base_urls, args)
    _print_setup_summary(setup_results)
    selected_sessions = [sessions[index % len(sessions)] for index in range(args.tasks)]

    sem = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=max(args.concurrency, 20))
    async with httpx.AsyncClient(timeout=args.timeout, limits=limits) as client:
        headers = await _login_headers(client, base_urls, 0, args)
        requests = []
        request_index = 0
        for session_id in selected_sessions:
            for _ in range(args.duplicates):
                requests.append(_enqueue_once(client, base_urls, session_id, request_index, sem, headers))
                request_index += 1
        started = time.perf_counter()
        enqueue_results = await asyncio.gather(*requests)
        elapsed = time.perf_counter() - started

    _print_enqueue_summary(args, len(base_urls), elapsed, enqueue_results)
    statuses = await _poll_until_done(base_urls, sorted(set(selected_sessions)), args)
    _print_poll_summary(statuses)

    if args.cancel_created_sessions and args.full_chain:
        await _cancel_sessions(base_urls, sessions, args.timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe interview background worker queue behavior.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="One or more comma-separated API base URLs.")
    parser.add_argument("--session-id", default="", help="Existing session id, or comma-separated session ids.")
    parser.add_argument("--tasks", type=int, default=10)
    parser.add_argument("--duplicates", type=int, default=1, help="How many end_interview calls to send per session.")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--poll-timeout", type=float, default=30.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--synthetic-prefix", default="probe")
    parser.add_argument("--full-chain", action="store_true", help="Create sessions, upload media, then enqueue.")
    parser.add_argument("--allow-cloud", action="store_true", help="Required for --full-chain.")
    parser.add_argument("--cancel-created-sessions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--email", default="", help="Optional login email used for start/end calls.")
    parser.add_argument("--password", default="", help="Optional login password used for start/end calls.")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--ext", default="mkv")
    parser.add_argument("--content-type", default="video/x-matroska")
    parser.add_argument("--media-size-bytes", type=int, default=4096)
    args = parser.parse_args()
    if args.tasks < 1:
        parser.error("--tasks must be >= 1")
    if args.duplicates < 1:
        parser.error("--duplicates must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.media_size_bytes < 0:
        parser.error("--media-size-bytes must be >= 0")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
