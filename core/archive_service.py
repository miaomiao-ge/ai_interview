import os
from typing import Callable


def archive_session_files(session_id: str, files: list[dict], upload_func: Callable, max_retries: int = 3) -> dict:
    upload_results = {}
    success_count = 0
    failure_count = 0

    for file_info in files:
        label = file_info["label"]
        local_path = file_info["local_path"]
        oss_key = file_info["oss_key"]

        if not os.path.exists(local_path):
            upload_results[label] = {
                "status": "missing",
                "url": "",
                "attempts": 0,
                "message": f"local file missing: {local_path}",
            }
            failure_count += 1
            continue

        last_error = ""
        for attempt in range(1, max_retries + 1):
            try:
                result = upload_func(local_path, oss_key)
                if isinstance(result, dict):
                    result.setdefault("status", "success")
                    result.setdefault("url", "")
                    result.setdefault("attempts", attempt)
                    upload_results[label] = result
                else:
                    upload_results[label] = {"status": "success", "url": result, "attempts": attempt}
                success_count += 1
                break
            except Exception as exc:
                last_error = str(exc)
        else:
            upload_results[label] = {
                "status": "error",
                "url": "",
                "attempts": max_retries,
                "message": last_error or "upload failed",
            }
            failure_count += 1

    if failure_count == 0:
        archive_status = "success"
    elif success_count > 0:
        archive_status = "partial_success"
    else:
        archive_status = "error"

    return {
        "session_id": session_id,
        "archive_status": archive_status,
        "upload_results": upload_results,
    }


def cleanup_session_files(filepaths: list[str]) -> dict:
    cleanup_results = {}
    for filepath in filepaths:
        if not filepath:
            continue
        if not os.path.exists(filepath):
            cleanup_results[filepath] = {"status": "missing"}
            continue
        try:
            os.remove(filepath)
            cleanup_results[filepath] = {"status": "deleted"}
        except Exception as exc:
            cleanup_results[filepath] = {"status": "error", "message": str(exc)}
    return cleanup_results
