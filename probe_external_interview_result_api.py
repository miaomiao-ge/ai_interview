import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_TIMEOUT_SECONDS = 15


@dataclass
class ProbeConfig:
    base_url: str
    app_key: str
    app_secret: str
    year: str
    page_num: int
    page_size: int
    application_nos: str
    ids: str
    include_incomplete: bool
    timeout: int
    output: str
    print_json: bool


def normalize_base_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def request_json(method: str, url: str, *, query: dict | None = None, form: dict | None = None, timeout: int) -> dict:
    full_url = url
    if query:
        full_url = f"{url}?{urlencode(query)}"

    data = None
    headers = {"Accept": "application/json"}
    if form is not None:
        data = urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    request = Request(full_url, data=data, headers=headers, method=method.upper())
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
            return {
                "http_status": response.status,
                "url": full_url,
                "json": json.loads(raw_body),
                "raw_body": raw_body,
            }
    except HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        return {
            "http_status": exc.code,
            "url": full_url,
            "json": try_parse_json(raw_body),
            "raw_body": raw_body,
        }
    except URLError as exc:
        raise RuntimeError(f"Request failed: {full_url}; error={exc}") from exc


def try_parse_json(value: str) -> Any:
    try:
        return json.loads(value)
    except ValueError:
        return None


def require_pdf_success(payload: dict, step_name: str) -> dict:
    body = payload.get("json")
    if not isinstance(body, dict):
        raise RuntimeError(f"{step_name} did not return JSON. body={payload.get('raw_body', '')[:500]}")
    if body.get("result") != "1" or body.get("valid") is not True:
        raise RuntimeError(f"{step_name} failed: {json.dumps(body, ensure_ascii=False, indent=2)}")
    return body


def get_token(config: ProbeConfig) -> str:
    payload = request_json(
        "GET",
        f"{config.base_url}/api/external/interviewResult/getToken",
        query={"appKey": config.app_key, "appSecret": config.app_secret},
        timeout=config.timeout,
    )
    body = require_pdf_success(payload, "getToken")
    token = body.get("dataObject") or ""
    if not token:
        raise RuntimeError("getToken returned success but dataObject token is empty")
    print(f"[ok] getToken http={payload['http_status']} token_prefix={token[:12]}...", file=sys.stderr)
    return token


def get_application_info_batch(config: ProbeConfig, token: str) -> dict:
    form = {
        "token": token,
        "year": config.year,
        "pageNum": str(config.page_num),
        "pageSize": str(config.page_size),
        "includeIncomplete": "true" if config.include_incomplete else "false",
    }
    if config.application_nos:
        form["applicationNos"] = config.application_nos
    if config.ids:
        form["ids"] = config.ids

    payload = request_json(
        "POST",
        f"{config.base_url}/api/external/interviewResult/getApplicationInfoBatch",
        form=form,
        timeout=config.timeout,
    )
    body = require_pdf_success(payload, "getApplicationInfoBatch")
    data_object = body.get("dataObject") or {}
    rows = data_object.get("data") or []
    print(
        "[ok] getApplicationInfoBatch "
        f"http={payload['http_status']} totalCount={data_object.get('totalCount')} rows={len(rows)}",
        file=sys.stderr,
    )
    return body


def summarize_result(body: dict) -> None:
    data_object = body.get("dataObject") or {}
    rows = data_object.get("data") or []
    if not rows:
        print("[warn] 接口可用，但本次查询没有返回面试结果数据。", file=sys.stderr)
        print("[hint] 如果只是想看未完成记录，加入参数：--include-incomplete", file=sys.stderr)
        return

    print("[data] first rows:", file=sys.stderr)
    for index, row in enumerate(rows[:5], start=1):
        interview = row.get("interviewResult") or {}
        print(
            f"  {index}. applicationNo={row.get('applicationNo', '')} "
            f"id={row.get('id', '')} passport={row.get('passportNumber', '')} "
            f"status={interview.get('status', '')} totalScore={interview.get('totalScore')}",
            file=sys.stderr,
        )


def write_output(path: str, body: dict) -> None:
    if not path:
        return
    with open(path, "w", encoding="utf-8") as file:
        json.dump(body, file, ensure_ascii=False, indent=2)
    print(f"[ok] full response written to {path}", file=sys.stderr)


def parse_args() -> ProbeConfig:
    parser = argparse.ArgumentParser(description="Probe external interview result API.")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--app-key", default=os.getenv("EXTERNAL_RESULT_APP_KEY", ""))
    parser.add_argument("--app-secret", default=os.getenv("EXTERNAL_RESULT_APP_SECRET", ""))
    parser.add_argument("--year", default=os.getenv("PROBE_YEAR", "2026"))
    parser.add_argument("--page-num", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--application-nos", default="", help="Comma-separated application numbers.")
    parser.add_argument("--ids", default="", help="Comma-separated application ids.")
    parser.add_argument("--include-incomplete", action="store_true")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--output", default="", help="Write full batch response JSON to this file.")
    parser.add_argument("--summary-only", action="store_true", help="Only print probe summary; do not print full JSON.")
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)
    if not base_url:
        parser.error("--base-url is required")
    if not args.app_key:
        parser.error("--app-key is required, or set EXTERNAL_RESULT_APP_KEY")
    if not args.app_secret:
        parser.error("--app-secret is required, or set EXTERNAL_RESULT_APP_SECRET")

    return ProbeConfig(
        base_url=base_url,
        app_key=args.app_key,
        app_secret=args.app_secret,
        year=str(args.year),
        page_num=args.page_num,
        page_size=args.page_size,
        application_nos=args.application_nos,
        ids=args.ids,
        include_incomplete=args.include_incomplete,
        timeout=args.timeout,
        output=args.output,
        print_json=not args.summary_only,
    )


def main() -> int:
    config = parse_args()
    print(f"[probe] base_url={config.base_url} year={config.year}", file=sys.stderr)
    token = get_token(config)
    body = get_application_info_batch(config, token)
    summarize_result(body)
    write_output(config.output, body)
    if config.print_json:
        print(json.dumps(body, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
