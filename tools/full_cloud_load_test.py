from __future__ import annotations

"""
Full cloud-consuming load test for the AI interview flow.

This script intentionally exercises the real cloud-backed chain:
start_interview (LLM + TTS), realtime ASR WebSocket, answer reply (LLM + TTS),
final recording upload (OSS), end_interview enqueue, and status polling.

Example:
    python tools/full_cloud_load_test.py --allow-cloud --sessions 100 --concurrency 100
"""

import argparse
import asyncio
import json
import os
import sys
import statistics
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode, urlparse

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.asr_ws_probe import SimpleWebSocket


TERMINAL_STATUSES = {"success", "partial_success", "failed"}


@dataclass
class StageResult:
    ok: bool
    latency_ms: float
    session_id: str = ""
    reason: str = ""
    payload: dict | None = None


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


def _ws_target(base_urls: list[str], index: int, session_id: str, args) -> str:
    parsed = urlparse(base_urls[index % len(base_urls)])
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = urlencode({"session_id": session_id, "language": args.language, "audio_device": "full-cloud-load"})
    return f"{scheme}://{parsed.netloc}/api/user/ws/asr?{query}"


def _fake_media_payload(size_bytes: int) -> bytes:
    if size_bytes < 4:
        return b"\x1a\x45\xdf\xa3"[:size_bytes]
    return b"\x1a\x45\xdf\xa3" + os.urandom(size_bytes - 4)


def _pcm_payload(args) -> bytes:
    sample_count = max(0, int(args.sample_rate * args.pcm_seconds))
    return b"\x00\x00" * sample_count


async def _request_json(client: httpx.AsyncClient, method: str, url: str, **kwargs: Any) -> tuple[bool, str, dict]:
    try:
        response = await client.request(method, url, **kwargs)
    except Exception as exc:
        return False, type(exc).__name__, {}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code != 200:
        return False, f"status_{response.status_code}", payload
    status = payload.get("status")
    if status and status not in {"success", "ok", "submitted", "pending", "running", "partial_success", "failed"}:
        return False, f"app_{status}", payload
    return True, "", payload


async def _health_snapshot(client: httpx.AsyncClient, base_urls: list[str]) -> list[dict]:
    results = []
    for index, _ in enumerate(base_urls):
        ok, reason, payload = await _request_json(client, "GET", _target(base_urls, index, "/health"))
        results.append(payload if ok else {"status": "error", "reason": reason})
    return results


async def _start_one(client: httpx.AsyncClient, base_urls: list[str], index: int, sem: asyncio.Semaphore, args) -> StageResult:
    async with sem:
        started = time.perf_counter()
        ok, reason, payload = await _request_json(
            client,
            "POST",
            _target(base_urls, index, "/api/user/start_interview"),
            json={"language": args.language},
        )
        latency = (time.perf_counter() - started) * 1000
        session_id = str(payload.get("session_id") or "")
        audio_url = str(payload.get("audio_url") or "")
        if not ok:
            return StageResult(False, latency, reason=reason, payload=payload)
        if not session_id:
            return StageResult(False, latency, reason="missing_session_id", payload=payload)
        if args.require_local_tts and not audio_url.startswith("/media/tts/"):
            return StageResult(False, latency, session_id=session_id, reason="tts_not_local", payload=payload)
        return StageResult(True, latency, session_id=session_id, payload=payload)


async def _receive_terminal(ws: SimpleWebSocket) -> dict:
    while True:
        frame_type, payload = await ws.receive()
        if frame_type == "close":
            return {"type": "closed"}
        if frame_type != "text":
            continue
        try:
            data = json.loads(str(payload))
        except json.JSONDecodeError:
            continue
        if data.get("type") in {"reply", "asr_done", "error"}:
            return data


async def _asr_answer_one(
    base_urls: list[str],
    session_id: str,
    pcm_payload: bytes,
    index: int,
    sem: asyncio.Semaphore,
    args,
) -> StageResult:
    async with sem:
        started = time.perf_counter()
        ws = None
        try:
            ws = await SimpleWebSocket.connect(_ws_target(base_urls, index, session_id, args), args.connect_timeout)
            receiver = asyncio.create_task(_receive_terminal(ws))
            for offset in range(0, len(pcm_payload), args.chunk_bytes):
                await ws.send_binary(pcm_payload[offset : offset + args.chunk_bytes])
                if args.chunk_interval > 0:
                    await asyncio.sleep(args.chunk_interval)
            await ws.send_text(
                json.dumps(
                    {
                        "action": "finish_answer",
                        "fallback_text": f"full cloud load answer {index}",
                    },
                    ensure_ascii=False,
                )
            )
            payload = await asyncio.wait_for(receiver, timeout=args.asr_response_timeout)
            latency = (time.perf_counter() - started) * 1000
            if payload.get("type") == "error":
                return StageResult(False, latency, session_id=session_id, reason=payload.get("message", "asr_error"), payload=payload)
            if payload.get("type") != "reply":
                return StageResult(False, latency, session_id=session_id, reason=f"unexpected_{payload.get('type')}", payload=payload)
            if payload.get("status") != "success":
                return StageResult(False, latency, session_id=session_id, reason=f"status_{payload.get('status')}", payload=payload)
            if args.require_local_tts and not str(payload.get("audio_url") or "").startswith("/media/tts/"):
                return StageResult(False, latency, session_id=session_id, reason="reply_tts_not_local", payload=payload)
            return StageResult(True, latency, session_id=session_id, payload=payload)
        except Exception as exc:
            latency = (time.perf_counter() - started) * 1000
            return StageResult(False, latency, session_id=session_id, reason=type(exc).__name__)
        finally:
            if ws is not None:
                await ws.close()


async def _upload_one(
    client: httpx.AsyncClient,
    base_urls: list[str],
    session_id: str,
    media_payload: bytes,
    index: int,
    sem: asyncio.Semaphore,
    args,
) -> StageResult:
    async with sem:
        started = time.perf_counter()
        ok, reason, payload = await _request_json(
            client,
            "POST",
            _target(base_urls, index, f"/api/user/upload_media?session_id={quote(session_id)}&ext=mkv"),
            content=media_payload,
            headers={"Content-Type": "video/x-matroska"},
        )
        latency = (time.perf_counter() - started) * 1000
        if not ok:
            return StageResult(False, latency, session_id=session_id, reason=reason, payload=payload)
        if not str(payload.get("url") or "").startswith("http"):
            return StageResult(False, latency, session_id=session_id, reason="missing_oss_url", payload=payload)
        return StageResult(True, latency, session_id=session_id, payload=payload)


async def _end_one(
    client: httpx.AsyncClient,
    base_urls: list[str],
    session_id: str,
    index: int,
    sem: asyncio.Semaphore,
) -> StageResult:
    async with sem:
        started = time.perf_counter()
        ok, reason, payload = await _request_json(
            client,
            "POST",
            _target(base_urls, index, "/api/user/end_interview"),
            json={"session_id": session_id},
        )
        latency = (time.perf_counter() - started) * 1000
        if not ok:
            return StageResult(False, latency, session_id=session_id, reason=reason, payload=payload)
        return StageResult(True, latency, session_id=session_id, payload=payload)


async def _poll_statuses(client: httpx.AsyncClient, base_urls: list[str], session_ids: list[str], args) -> dict[str, dict]:
    latest = {session_id: {"status": "not_polled"} for session_id in session_ids}
    deadline = time.monotonic() + args.poll_timeout
    while True:
        results = await asyncio.gather(
            *[
                _request_json(
                    client,
                    "GET",
                    _target(base_urls, index, f"/api/user/interview_status?session_id={quote(session_id)}"),
                )
                for index, session_id in enumerate(session_ids)
            ]
        )
        latest = {
            session_id: payload if ok else {"status": "probe_error", "reason": reason}
            for session_id, (ok, reason, payload) in zip(session_ids, results)
        }
        if all(str(item.get("status")) in TERMINAL_STATUSES for item in latest.values()):
            return latest
        if time.monotonic() >= deadline:
            return latest
        await asyncio.sleep(args.poll_interval)


def _stage_summary(name: str, results: list[StageResult]) -> dict:
    latencies = [item.latency_ms for item in results if item.ok]
    failed = len(results) - len(latencies)
    reasons = Counter(item.reason or "unknown" for item in results if not item.ok)
    if latencies:
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        avg = statistics.mean(latencies)
        max_latency = max(latencies)
    else:
        avg = p95 = max_latency = 0.0
    summary = {
        "stage": name,
        "total": len(results),
        "ok": len(latencies),
        "failed": failed,
        "failure_reasons": dict(reasons),
        "latency_avg_ms": round(avg, 1),
        "latency_p95_ms": round(p95, 1),
        "latency_max_ms": round(max_latency, 1),
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


async def run(args) -> None:
    if not args.allow_cloud:
        raise SystemExit("This test consumes ASR/TTS/LLM/OSS quota. Re-run with --allow-cloud if confirmed.")
    base_urls = _base_urls(args.base_url)
    sem = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(max_connections=max(args.concurrency, 1), max_keepalive_connections=max(args.concurrency, 20))
    media_payload = _fake_media_payload(args.media_size_bytes)
    pcm = _pcm_payload(args)

    async with httpx.AsyncClient(timeout=args.http_timeout, limits=limits) as client:
        print("health_before=" + json.dumps(await _health_snapshot(client, base_urls), ensure_ascii=False), flush=True)

        started = time.perf_counter()
        start_results = await asyncio.gather(*[_start_one(client, base_urls, index, sem, args) for index in range(args.sessions)])
        print(f"stage_elapsed start_interview {time.perf_counter() - started:.2f}s", flush=True)
        _stage_summary("start_interview", start_results)
        session_ids = [item.session_id for item in start_results if item.ok and item.session_id]
        if not session_ids:
            raise SystemExit("No sessions created; aborting remaining stages.")

        started = time.perf_counter()
        asr_results = await asyncio.gather(
            *[_asr_answer_one(base_urls, session_id, pcm, index, sem, args) for index, session_id in enumerate(session_ids)]
        )
        print(f"stage_elapsed asr_answer {time.perf_counter() - started:.2f}s", flush=True)
        _stage_summary("asr_answer", asr_results)
        ready_for_upload = [item.session_id for item in asr_results if item.ok and item.session_id]

        started = time.perf_counter()
        upload_results = await asyncio.gather(
            *[
                _upload_one(client, base_urls, session_id, media_payload, index, sem, args)
                for index, session_id in enumerate(ready_for_upload)
            ]
        )
        print(f"stage_elapsed upload_media {time.perf_counter() - started:.2f}s", flush=True)
        _stage_summary("upload_media", upload_results)
        ready_for_end = [item.session_id for item in upload_results if item.ok and item.session_id]

        started = time.perf_counter()
        end_results = await asyncio.gather(
            *[_end_one(client, base_urls, session_id, index, sem) for index, session_id in enumerate(ready_for_end)]
        )
        print(f"stage_elapsed end_interview {time.perf_counter() - started:.2f}s", flush=True)
        _stage_summary("end_interview", end_results)

        statuses = await _poll_statuses(client, base_urls, ready_for_end, args)
        status_counts = Counter(str(item.get("status") or "unknown") for item in statuses.values())
        print("final_status_counts=" + json.dumps(dict(status_counts), ensure_ascii=False), flush=True)
        for session_id, payload in list(statuses.items())[:5]:
            print(f"status_sample session_id={session_id} payload={json.dumps(payload, ensure_ascii=False)[:500]}", flush=True)
        print("health_after=" + json.dumps(await _health_snapshot(client, base_urls), ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full cloud load test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--sessions", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--allow-cloud", action="store_true")
    parser.add_argument("--require-local-tts", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--http-timeout", type=float, default=180.0)
    parser.add_argument("--connect-timeout", type=float, default=30.0)
    parser.add_argument("--asr-response-timeout", type=float, default=180.0)
    parser.add_argument("--poll-timeout", type=float, default=300.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--media-size-bytes", type=int, default=4096)
    parser.add_argument("--pcm-seconds", type=float, default=1.0)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--chunk-bytes", type=int, default=3200)
    parser.add_argument("--chunk-interval", type=float, default=0.01)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
