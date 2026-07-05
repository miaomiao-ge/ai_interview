"""
Lightweight HTTP concurrency probe for local smoke testing.

Examples:
    python tools/concurrency_probe.py --url http://127.0.0.1:8000 --requests 300 --concurrency 50
    python tools/concurrency_probe.py --url http://127.0.0.1:8001/health,http://127.0.0.1:8002/health --requests 600 --concurrency 300

This script intentionally hits a lightweight endpoint. It verifies that the API process,
DB startup path, Redis health reporting, and HTTP concurrency handling are alive
without consuming LLM, ASR, TTS, or OSS quota.
"""

import argparse
import asyncio
import statistics
import time
from collections import Counter

import httpx


def _normalize_target_url(raw_url: str) -> str:
    target_url = raw_url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = f"http://127.0.0.1:8000/{target_url.lstrip('/')}"
    if target_url.rstrip("/").endswith(":8000"):
        target_url = f"{target_url.rstrip('/')}/health"
    return target_url


def _normalize_target_urls(raw_urls: str) -> list[str]:
    return [_normalize_target_url(item) for item in raw_urls.split(",") if item.strip()]


async def _request_endpoint(
    client: httpx.AsyncClient,
    target_urls: list[str],
    request_index: int,
    sem: asyncio.Semaphore,
) -> tuple[bool, float, str]:
    async with sem:
        target_url = target_urls[request_index % len(target_urls)]
        started = time.perf_counter()
        try:
            response = await client.get(target_url)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response.status_code == 200:
                return True, elapsed_ms, ""
            return False, elapsed_ms, f"status_{response.status_code}"
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            return False, elapsed_ms, type(exc).__name__


async def run_probe(base_url: str, total_requests: int, concurrency: int, timeout: float) -> None:
    sem = asyncio.Semaphore(concurrency)
    target_urls = _normalize_target_urls(base_url)
    if not target_urls:
        raise ValueError("At least one target URL is required.")
    limits = httpx.Limits(
        max_connections=max(concurrency, 1),
        max_keepalive_connections=max(concurrency, 20),
    )
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        tasks = [_request_endpoint(client, target_urls, index, sem) for index in range(total_requests)]
        started = time.perf_counter()
        results = await asyncio.gather(*tasks)
        total_elapsed = time.perf_counter() - started

    ok_latencies = [latency for ok, latency, _ in results if ok]
    failed = len(results) - len(ok_latencies)
    failure_reasons = Counter(reason for ok, _, reason in results if not ok for reason in [reason or "unknown"])
    if ok_latencies:
        p95 = statistics.quantiles(ok_latencies, n=20)[18] if len(ok_latencies) >= 20 else max(ok_latencies)
        avg = statistics.mean(ok_latencies)
        max_latency = max(ok_latencies)
    else:
        p95 = avg = max_latency = 0

    print(f"targets={len(target_urls)} requests={total_requests} concurrency={concurrency} failed={failed}")
    if failure_reasons:
        print("failure_reasons=" + ",".join(f"{reason}:{count}" for reason, count in failure_reasons.items()))
    print(f"elapsed={total_elapsed:.2f}s throughput={total_requests / max(total_elapsed, 0.001):.1f} req/s")
    print(f"latency_avg={avg:.1f}ms latency_p95={p95:.1f}ms latency_max={max_latency:.1f}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a lightweight concurrency probe.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/health", help="Target URL or path to request.")
    parser.add_argument("--requests", type=int, default=300, help="Total requests to send.")
    parser.add_argument("--concurrency", type=int, default=50, help="Maximum in-flight requests.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Per-request timeout in seconds.")
    args = parser.parse_args()
    asyncio.run(run_probe(args.url, args.requests, args.concurrency, args.timeout))


if __name__ == "__main__":
    main()
