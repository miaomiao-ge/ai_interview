from __future__ import annotations

"""
Concurrent WebSocket ASR probe for the AI interview API.

This tool connects to /api/user/ws/asr, streams PCM bytes, sends a finish
signal, and reports ASR completion latency. It intentionally implements a tiny
WebSocket client with the Python standard library so the probe does not add a
runtime dependency.

Examples:
    python tools/asr_ws_probe.py --allow-cloud --session-id abc123 --connections 1 --concurrency 1
    python tools/asr_ws_probe.py --allow-cloud --create-sessions --connections 5 --concurrency 5 --fallback-text "probe answer"
    python tools/asr_ws_probe.py --allow-cloud --session-id abc123 --pcm-file sample.pcm --connections 1
"""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import ssl
import statistics
import struct
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx


WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TERMINAL_MESSAGE_TYPES = {"asr_done", "reply", "error"}


@dataclass
class ProbeResult:
    ok: bool
    latency_ms: float
    reason: str = ""
    session_id: str = ""
    recognized_text: str = ""
    message_count: int = 0


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
    query = urlencode(
        {
            "session_id": session_id,
            "language": args.language,
            "audio_device": args.audio_device,
        }
    )
    return f"{scheme}://{parsed.netloc}/api/user/ws/asr?{query}"


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


async def _create_session(client: httpx.AsyncClient, base_urls: list[str], index: int, args) -> str:
    headers = {}
    if args.email and args.password:
        ok, reason, payload = await _request_json(
            client,
            "POST",
            _target(base_urls, index, "/api/user/login"),
            json={"email": args.email, "password": args.password},
        )
        if not ok:
            raise RuntimeError(f"login failed: {reason}")
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
    if not ok or not payload.get("session_id"):
        raise RuntimeError(f"start_interview failed: {reason or 'missing_session_id'}")
    return str(payload["session_id"])


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


async def _prepare_sessions(base_urls: list[str], args) -> tuple[list[str], list[str]]:
    provided = [item.strip() for item in args.session_id.split(",") if item.strip()]
    if provided:
        return provided, []
    if not args.create_sessions:
        raise SystemExit("Provide --session-id or use --create-sessions with --allow-cloud.")
    if not args.allow_cloud:
        raise SystemExit("--create-sessions calls start_interview and requires --allow-cloud.")

    count = 1 if args.reuse_created_session else args.connections
    limits = httpx.Limits(max_connections=max(1, min(args.concurrency, 10)))
    async with httpx.AsyncClient(timeout=args.http_timeout, limits=limits) as client:
        created = []
        for index in range(count):
            created.append(await _create_session(client, base_urls, index, args))
    return created, created


def _load_pcm_payload(args) -> bytes:
    if args.pcm_file:
        with open(args.pcm_file, "rb") as file:
            return file.read()
    sample_count = max(0, int(args.sample_rate * args.pcm_seconds))
    return b"\x00\x00" * sample_count


class SimpleWebSocket:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    @classmethod
    async def connect(cls, url: str, timeout: float) -> "SimpleWebSocket":
        parsed = urlparse(url)
        if parsed.scheme not in {"ws", "wss"}:
            raise ValueError(f"Unsupported WebSocket scheme: {parsed.scheme}")

        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        ssl_context = ssl.create_default_context() if parsed.scheme == "wss" else None
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port, ssl=ssl_context, server_hostname=host if ssl_context else None),
            timeout=timeout,
        )

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        host_header = host if parsed.port is None else f"{host}:{port}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host_header}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        writer.write(request.encode("ascii"))
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=timeout)
        cls._validate_handshake(response, key)
        return cls(reader, writer)

    @staticmethod
    def _validate_handshake(response: bytes, key: str) -> None:
        text = response.decode("iso-8859-1", errors="replace")
        lines = text.split("\r\n")
        if not lines or " 101 " not in lines[0]:
            raise RuntimeError(lines[0] if lines else "invalid_handshake")
        headers = {}
        for line in lines[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        expected = base64.b64encode(hashlib.sha1((key + WS_GUID).encode("ascii")).digest()).decode("ascii")
        if headers.get("sec-websocket-accept") != expected:
            raise RuntimeError("websocket_accept_mismatch")

    async def send_text(self, text: str) -> None:
        await self._send_frame(0x1, text.encode("utf-8"))

    async def send_binary(self, payload: bytes) -> None:
        await self._send_frame(0x2, payload)

    async def send_close(self) -> None:
        await self._send_frame(0x8, b"")

    async def send_pong(self, payload: bytes) -> None:
        await self._send_frame(0xA, payload)

    async def _send_frame(self, opcode: int, payload: bytes) -> None:
        first = 0x80 | opcode
        mask_key = os.urandom(4)
        length = len(payload)
        if length < 126:
            header = struct.pack("!BB", first, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", first, 0x80 | 126, length)
        else:
            header = struct.pack("!BBQ", first, 0x80 | 127, length)
        masked = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
        self.writer.write(header + mask_key + masked)
        await self.writer.drain()

    async def receive(self) -> tuple[str, str | bytes]:
        while True:
            header = await self.reader.readexactly(2)
            first, second = header
            opcode = first & 0x0F
            masked = bool(second & 0x80)
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", await self.reader.readexactly(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", await self.reader.readexactly(8))[0]
            mask_key = await self.reader.readexactly(4) if masked else b""
            payload = await self.reader.readexactly(length) if length else b""
            if masked:
                payload = bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                return "close", payload
            if opcode == 0x9:
                await self.send_pong(payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x1:
                return "text", payload.decode("utf-8", errors="replace")
            if opcode == 0x2:
                return "binary", payload
            raise RuntimeError(f"unsupported_opcode_{opcode}")

    async def close(self) -> None:
        try:
            await self.send_close()
        except Exception:
            pass
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except Exception:
            pass


async def _receive_terminal_message(ws: SimpleWebSocket, messages: list[dict]) -> dict:
    while True:
        frame_type, payload = await ws.receive()
        if frame_type == "close":
            return {"type": "closed"}
        if frame_type != "text":
            continue
        try:
            message = json.loads(str(payload))
        except json.JSONDecodeError:
            message = {"type": "non_json_text", "raw": str(payload)}
        messages.append(message)
        if message.get("type") in TERMINAL_MESSAGE_TYPES:
            return message


async def _run_one(
    base_urls: list[str],
    session_ids: list[str],
    pcm_payload: bytes,
    index: int,
    sem: asyncio.Semaphore,
    args,
) -> ProbeResult:
    async with sem:
        session_id = session_ids[index % len(session_ids)]
        url = _ws_target(base_urls, index, session_id, args)
        fallback_text = args.fallback_text.replace("{index}", str(index)).replace("{session_id}", session_id)
        started = time.perf_counter()
        ws = None
        messages: list[dict] = []
        try:
            ws = await SimpleWebSocket.connect(url, args.connect_timeout)
            receiver = asyncio.create_task(_receive_terminal_message(ws, messages))
            for offset in range(0, len(pcm_payload), args.chunk_bytes):
                await ws.send_binary(pcm_payload[offset : offset + args.chunk_bytes])
                if args.chunk_interval > 0:
                    await asyncio.sleep(args.chunk_interval)

            await ws.send_text(
                json.dumps(
                    {
                        "action": args.action,
                        "fallback_text": fallback_text,
                    },
                    ensure_ascii=False,
                )
            )
            final_message = await asyncio.wait_for(receiver, timeout=args.response_timeout)
            latency_ms = (time.perf_counter() - started) * 1000
            if final_message.get("type") == "error":
                return ProbeResult(False, latency_ms, final_message.get("message", "asr_error"), session_id, "", len(messages))
            if final_message.get("type") == "closed":
                return ProbeResult(False, latency_ms, "closed_without_result", session_id, "", len(messages))
            recognized_text = str(final_message.get("recognized_text") or "")
            if args.require_text and not recognized_text:
                return ProbeResult(False, latency_ms, "missing_recognized_text", session_id, "", len(messages))
            return ProbeResult(True, latency_ms, session_id=session_id, recognized_text=recognized_text, message_count=len(messages))
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            return ProbeResult(False, latency_ms, type(exc).__name__, session_id, "", len(messages))
        finally:
            if ws is not None:
                await ws.close()


def _print_summary(args, target_count: int, elapsed: float, results: list[ProbeResult]) -> None:
    ok_latencies = [item.latency_ms for item in results if item.ok]
    failed = len(results) - len(ok_latencies)
    reasons = Counter(item.reason or "unknown" for item in results if not item.ok)
    texts = [item.recognized_text for item in results if item.recognized_text]
    if ok_latencies:
        p95 = statistics.quantiles(ok_latencies, n=20)[18] if len(ok_latencies) >= 20 else max(ok_latencies)
        avg = statistics.mean(ok_latencies)
        max_latency = max(ok_latencies)
    else:
        avg = p95 = max_latency = 0.0

    print(
        f"targets={target_count} connections={args.connections} concurrency={args.concurrency} "
        f"action={args.action} failed={failed}"
    )
    if reasons:
        print("failure_reasons=" + ",".join(f"{reason}:{count}" for reason, count in reasons.items()))
    print(f"elapsed={elapsed:.2f}s throughput={args.connections / max(elapsed, 0.001):.1f} conn/s")
    print(f"latency_avg={avg:.1f}ms latency_p95={p95:.1f}ms latency_max={max_latency:.1f}ms")
    print(f"recognized_count={len(texts)} message_count={sum(item.message_count for item in results)}")
    for sample in texts[:3]:
        print(f"recognized_sample={sample[:120]}")


async def run(args) -> None:
    if not args.allow_cloud:
        raise SystemExit("Realtime ASR consumes Alibaba Cloud quota. Re-run with --allow-cloud if confirmed.")
    base_urls = _base_urls(args.base_url)
    session_ids, created_session_ids = await _prepare_sessions(base_urls, args)
    pcm_payload = _load_pcm_payload(args)
    sem = asyncio.Semaphore(args.concurrency)
    try:
        started = time.perf_counter()
        results = await asyncio.gather(
            *[_run_one(base_urls, session_ids, pcm_payload, index, sem, args) for index in range(args.connections)]
        )
        elapsed = time.perf_counter() - started
        _print_summary(args, len(base_urls), elapsed, results)
    finally:
        if args.cancel_created_sessions:
            await _cancel_created_sessions(base_urls, created_session_ids, args.http_timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a concurrent WebSocket ASR probe.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="One or more comma-separated API base URLs.")
    parser.add_argument("--session-id", default="", help="Existing session id, or comma-separated session ids.")
    parser.add_argument("--create-sessions", action="store_true", help="Create sessions through start_interview before probing.")
    parser.add_argument("--reuse-created-session", action="store_true", help="Create one session and reuse it for every connection.")
    parser.add_argument("--cancel-created-sessions", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-cloud", action="store_true", help="Required because this opens realtime ASR connections.")
    parser.add_argument("--email", default="", help="Optional login email used when creating sessions.")
    parser.add_argument("--password", default="", help="Optional login password used when creating sessions.")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--audio-device", default="probe")
    parser.add_argument("--connections", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--response-timeout", type=float, default=20.0)
    parser.add_argument("--http-timeout", type=float, default=90.0)
    parser.add_argument("--pcm-file", default="", help="Raw 16 kHz 16-bit mono PCM file to stream.")
    parser.add_argument("--pcm-seconds", type=float, default=1.0, help="Silence duration when --pcm-file is omitted.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--chunk-bytes", type=int, default=3200)
    parser.add_argument("--chunk-interval", type=float, default=0.02)
    parser.add_argument("--action", choices=["finish_asr", "finish_answer"], default="finish_asr")
    parser.add_argument("--fallback-text", default="ASR probe fallback text {index}")
    parser.add_argument("--require-text", action="store_true")
    args = parser.parse_args()
    if args.connections < 1:
        parser.error("--connections must be >= 1")
    if args.concurrency < 1:
        parser.error("--concurrency must be >= 1")
    if args.chunk_bytes < 1:
        parser.error("--chunk-bytes must be >= 1")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
