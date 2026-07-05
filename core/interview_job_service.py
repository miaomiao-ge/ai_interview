import glob
import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_

from core.archive_service import cleanup_session_files
from core.config import MEDIA_RECORD_POLICY, TASK_MAX_RETRIES, TASK_QUEUE_NAME, WORKER_NODE_ID
from core.concurrency_guard import release_active_session
from core.database import BackgroundJob, InterviewRecord, SessionLocal
from core.llm_agent import (
    clear_interview_session,
    evaluate_interview,
    get_chat_history_string,
    get_session_media,
    get_session_snapshot,
    restore_session_snapshot,
    update_session_runtime,
)
from core.redis_utils import get_redis_client, json_get, json_set, redis_key

JOB_TYPE_EVALUATE_ARCHIVE = "evaluate_archive"
JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCESS = "success"
JOB_STATUS_PARTIAL_SUCCESS = "partial_success"
JOB_STATUS_FAILED = "failed"

_enqueue_local_lock = threading.RLock()
_enqueue_local_sessions: set[str] = set()


def _now() -> datetime:
    return datetime.now()


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_loads(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _queue_key() -> str:
    return redis_key("queue", TASK_QUEUE_NAME)


def _job_status_key(session_id: str) -> str:
    return redis_key("task", JOB_TYPE_EVALUATE_ARCHIVE, session_id)


def _job_lock_key(job_id: int) -> str:
    return redis_key("lock", "job", job_id)


def _enqueue_lock_key(session_id: str) -> str:
    return redis_key("lock", "enqueue", session_id)


def set_task_status(session_id: str, payload: dict) -> None:
    data = {
        "session_id": session_id,
        "job_type": JOB_TYPE_EVALUATE_ARCHIVE,
        "updated_at": _now().isoformat(timespec="seconds"),
        **payload,
    }
    json_set(_job_status_key(session_id), data, 7 * 24 * 3600)


def get_task_status_from_cache(session_id: str) -> Optional[dict]:
    return json_get(_job_status_key(session_id))


def _get_existing_record(db, session_id: str):
    return db.query(InterviewRecord).filter_by(session_id=session_id).first()


def _get_latest_job(db, session_id: str):
    return (
        db.query(BackgroundJob)
        .filter_by(session_id=session_id, job_type=JOB_TYPE_EVALUATE_ARCHIVE)
        .order_by(BackgroundJob.id.desc())
        .first()
    )


def _serialize_record_status(record: InterviewRecord) -> dict:
    return {
        "status": record.archive_status or JOB_STATUS_SUCCESS,
        "job_status": JOB_STATUS_SUCCESS,
        "archive_status": record.archive_status or "",
        "archive_error": record.archive_error or "",
        "evaluate_status": record.evaluate_status or "",
        "evaluate_error": record.evaluate_error or "",
        "message": "归档完成" if record.archive_status == "success" else "报告已保存，请在后台查看处理状态",
        "report": record.evaluation_result or "",
        "record_id": record.id,
        "av_path": record.av_path or "",
        "updated_at": (record.processing_finished_at or record.created_at or _now()).isoformat(),
    }


def _serialize_job_status(job: BackgroundJob) -> dict:
    result = _json_loads(job.result_json)
    payload = _json_loads(job.payload_json)
    return {
        "status": job.status,
        "job_status": job.status,
        "archive_status": result.get("archive_status", ""),
        "evaluate_status": result.get("evaluate_status", ""),
        "message": result.get("message") or payload.get("message") or "面试档案正在后台处理中",
        "error": job.error_message or "",
        "retry_count": job.retry_count or 0,
        "updated_at": job.updated_at.isoformat() if job.updated_at else "",
        **({"report": result["report"]} if result.get("report") else {}),
    }


def get_interview_status(session_id: str) -> dict:
    db = SessionLocal()
    try:
        record = _get_existing_record(db, session_id)
        if record:
            return _serialize_record_status(record)

        job = _get_latest_job(db, session_id)
        if job:
            return _serialize_job_status(job)

        cached = get_task_status_from_cache(session_id)
        if cached:
            return cached

        return {"status": "not_found", "message": "未找到该面试处理任务"}
    finally:
        db.close()


def get_worker_queue_snapshot() -> dict:
    """Return lightweight queue and job counts for health checks and runbooks."""
    snapshot = {
        "queue_name": TASK_QUEUE_NAME,
        "redis_queue_depth": None,
        "db_status_counts": {},
    }
    client = get_redis_client()
    if client is not None:
        try:
            snapshot["redis_queue_depth"] = int(client.llen(_queue_key()))
        except Exception:
            snapshot["redis_queue_depth"] = None

    try:
        db = SessionLocal()
    except Exception as exc:
        snapshot["db_error"] = str(exc)
        return snapshot
    try:
        rows = (
            db.query(BackgroundJob.status, func.count(BackgroundJob.id))
            .filter(BackgroundJob.job_type == JOB_TYPE_EVALUATE_ARCHIVE)
            .group_by(BackgroundJob.status)
            .all()
        )
        snapshot["db_status_counts"] = {str(status or "unknown"): int(count or 0) for status, count in rows}
    except Exception as exc:
        snapshot["db_error"] = str(exc)
    finally:
        db.close()
    return snapshot


def enqueue_interview_processing(session_id: str, user_email: str) -> dict:
    session_id = (session_id or "").strip()
    user_email = (user_email or "anonymous@unknown.com").strip() or "anonymous@unknown.com"
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}

    lock_acquired, lock_source = _acquire_enqueue_lock(session_id)
    if not lock_acquired:
        current_status = get_interview_status(session_id)
        if current_status.get("status") != "not_found":
            release_active_session(session_id)
            return current_status
        return {
            "status": "submitted",
            "job_status": JOB_STATUS_PENDING,
            "message": "面试档案已提交，正在排队处理中",
        }

    db = SessionLocal()
    try:
        record = _get_existing_record(db, session_id)
        if record:
            release_active_session(session_id)
            return _serialize_record_status(record)

        payload = {
            "session_id": session_id,
            "user_email": user_email,
            "media_policy": MEDIA_RECORD_POLICY,
            "media": get_session_media(session_id),
            "session_state": get_session_snapshot(session_id),
            "submitted_at": _now().isoformat(timespec="seconds"),
        }
        job = _get_latest_job(db, session_id)
        should_enqueue = False
        if not job or job.status in {JOB_STATUS_FAILED, JOB_STATUS_SUCCESS, JOB_STATUS_PARTIAL_SUCCESS}:
            job = BackgroundJob(
                session_id=session_id,
                job_type=JOB_TYPE_EVALUATE_ARCHIVE,
                status=JOB_STATUS_PENDING,
                payload_json=_json_dumps(payload),
                retry_count=0,
                max_retries=TASK_MAX_RETRIES,
                next_run_at=_now(),
                created_at=_now(),
                updated_at=_now(),
            )
            db.add(job)
            db.commit()
            should_enqueue = True
        elif job.status == JOB_STATUS_PENDING:
            job.payload_json = _json_dumps({**_json_loads(job.payload_json), **payload})
            job.next_run_at = _now()
            job.updated_at = _now()
            db.commit()

        set_task_status(
            session_id,
            {
                "status": JOB_STATUS_PENDING,
                "job_status": JOB_STATUS_PENDING,
                "message": "面试档案已提交，正在排队处理",
            },
        )

        client = get_redis_client()
        if should_enqueue and client is not None:
            try:
                client.lpush(_queue_key(), str(job.id))
            except Exception:
                pass

        release_active_session(session_id)

        return {
            "status": "submitted",
            "job_status": job.status,
            "job_id": job.id,
            "message": "面试档案已提交，正在后台处理",
        }
    finally:
        db.close()
        _release_enqueue_lock(session_id, lock_source)


def _build_media_paths(session_id: str) -> dict:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    av_dir = os.path.join(base_dir, "media", "records", "audio_video")
    return {
        "base_dir": base_dir,
        "audio": os.path.join(base_dir, "media", "records", "audio_only", f"{session_id}.wav"),
        "video": os.path.join(base_dir, "media", "records", "video_only", f"{session_id}.mkv"),
        "av": os.path.join(base_dir, "media", "records", "audio_video", f"{session_id}.mkv"),
        "av_webm": os.path.join(av_dir, f"{session_id}.webm"),
        "av_mp4": os.path.join(av_dir, f"{session_id}.mp4"),
        "tts_glob": os.path.join(base_dir, "media", "tts", f"tts_{session_id}_*.wav"),
    }


def _get_uploaded_av_media(payload: dict, session_id: str) -> dict:
    media = payload.get("media") or {}
    av_media = media.get("av") if isinstance(media, dict) else None
    if not isinstance(av_media, dict) or not av_media.get("url"):
        live_media = get_session_media(session_id)
        av_media = live_media.get("av") if isinstance(live_media, dict) else None
    return av_media if isinstance(av_media, dict) else {}


def _acquire_job_lock(job_id: int) -> bool:
    client = get_redis_client()
    if client is None:
        return True
    return bool(client.set(_job_lock_key(job_id), WORKER_NODE_ID, nx=True, ex=900))


def _release_job_lock(job_id: int) -> None:
    client = get_redis_client()
    if client is not None:
        client.delete(_job_lock_key(job_id))


def _acquire_enqueue_lock(session_id: str) -> tuple[bool, str]:
    client = get_redis_client()
    if client is not None:
        try:
            acquired = bool(client.set(_enqueue_lock_key(session_id), WORKER_NODE_ID, nx=True, ex=30))
            return acquired, "redis"
        except Exception:
            pass

    with _enqueue_local_lock:
        if session_id in _enqueue_local_sessions:
            return False, "local"
        _enqueue_local_sessions.add(session_id)
        return True, "local"


def _release_enqueue_lock(session_id: str, source: str) -> None:
    if source == "redis":
        client = get_redis_client()
        if client is not None:
            try:
                client.delete(_enqueue_lock_key(session_id))
            except Exception:
                pass
        return

    with _enqueue_local_lock:
        _enqueue_local_sessions.discard(session_id)


def process_interview_job(job_id: int) -> dict:
    if not _acquire_job_lock(job_id):
        return {"status": "skipped", "message": "job locked by another worker"}

    db = SessionLocal()
    try:
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if not job:
            return {"status": "not_found", "message": "job not found"}
        if job.status in {JOB_STATUS_SUCCESS, JOB_STATUS_PARTIAL_SUCCESS}:
            return _json_loads(job.result_json)
        if job.status == JOB_STATUS_RUNNING and job.locked_by and job.locked_by != WORKER_NODE_ID:
            return {"status": "skipped", "message": "job running on another worker"}

        if job.status == JOB_STATUS_PENDING:
            locked_at = _now()
            updated = (
                db.query(BackgroundJob)
                .filter(BackgroundJob.id == job_id, BackgroundJob.status == JOB_STATUS_PENDING)
                .update(
                    {
                        "status": JOB_STATUS_RUNNING,
                        "locked_by": WORKER_NODE_ID,
                        "locked_at": locked_at,
                        "updated_at": locked_at,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            if not updated:
                return {"status": "skipped", "message": "job claimed by another worker"}
            job = db.query(BackgroundJob).filter_by(id=job_id).first()

        payload = _json_loads(job.payload_json)
        session_id = job.session_id
        user_email = payload.get("user_email") or "anonymous@unknown.com"
        submitted_at = payload.get("submitted_at")
        session_runtime = (payload.get("session_state") or {}).get("runtime") or {}
        face_verify = session_runtime.get("face_verify") or {}
        proctoring = session_runtime.get("proctoring") or {}
        restore_session_snapshot(payload.get("session_state") or {})

        set_task_status(
            session_id,
            {
                "status": JOB_STATUS_RUNNING,
                "job_status": JOB_STATUS_RUNNING,
                "evaluate_status": "processing",
                "archive_status": "pending",
                "message": "正在生成面试评价",
            },
        )
        update_session_runtime(session_id, status="evaluating", worker_node_id=WORKER_NODE_ID)

        evaluation_result = evaluate_interview(session_id)
        chat_history = get_chat_history_string(session_id)
        if isinstance(evaluation_result, str):
            raise RuntimeError(evaluation_result)

        report = evaluation_result["report"]
        structured_json = _json_dumps(evaluation_result["structured"])
        media_paths = _build_media_paths(session_id)
        av_media = _get_uploaded_av_media(payload, session_id)
        oss_av_url = av_media.get("url", "")
        upload_results = {
            "av": {
                "status": "success" if oss_av_url else "error",
                "url": oss_av_url,
                "oss_key": av_media.get("oss_key", ""),
                "bytes": av_media.get("bytes", 0),
                "message": "" if oss_av_url else "media OSS url not found; upload API must write media to OSS before worker runs",
            }
        }

        set_task_status(
            session_id,
            {
                "status": JOB_STATUS_RUNNING,
                "job_status": JOB_STATUS_RUNNING,
                "evaluate_status": "success",
                "archive_status": "success" if oss_av_url else "error",
                "message": "评价已生成，正在上传面试音视频",
            },
        )

        archive_status = "success" if oss_av_url else "error"
        archive_error = "" if oss_av_url else upload_results["av"]["message"]

        finished_at = _now()
        record = _get_existing_record(db, session_id)
        if not record:
            record = InterviewRecord(session_id=session_id, created_at=finished_at)
            db.add(record)

        record.user_email = user_email
        record.chat_history = chat_history
        record.evaluation_result = report
        record.evaluation_result_json = structured_json
        record.audio_path = ""
        record.video_path = ""
        record.av_path = oss_av_url
        record.archive_status = archive_status
        record.archive_error = archive_error
        record.evaluate_status = "success"
        record.evaluate_error = ""
        record.processing_started_at = job.locked_at
        record.processing_finished_at = finished_at
        record.submitted_at = datetime.fromisoformat(submitted_at) if submitted_at else job.created_at
        record.completed_at = finished_at
        record.media_policy = MEDIA_RECORD_POLICY
        record.worker_node_id = WORKER_NODE_ID
        record.retry_count = job.retry_count or 0
        record.face_verify_status = "passed" if face_verify.get("verified") else (record.face_verify_status or "pending")
        record.face_verify_score = face_verify.get("score")
        record.face_verify_snapshot_oss_key = face_verify.get("snapshot_oss_key", "")
        record.identity_doc_oss_key = face_verify.get("identity_doc_oss_key", "")
        if face_verify.get("verified_at"):
            try:
                record.face_verify_at = datetime.fromisoformat(face_verify["verified_at"])
            except ValueError:
                record.face_verify_at = finished_at
        record.proctoring_risk_level = proctoring.get("risk_level") or record.proctoring_risk_level or "none"
        if proctoring.get("flags") and not record.proctoring_flags_json:
            record.proctoring_flags_json = _json_dumps({flag: 1 for flag in proctoring.get("flags", [])})
        record.review_status = record.review_status or "待复核"
        record.review_remark = record.review_remark or ""

        cleanup_paths = list(glob.glob(media_paths["tts_glob"]))
        cleanup_results = cleanup_session_files(cleanup_paths)

        final_status = JOB_STATUS_SUCCESS if archive_status == "success" else JOB_STATUS_PARTIAL_SUCCESS
        message = "归档完成" if archive_status == "success" else "报告已保存，但音视频归档需要补偿处理"
        result = {
            "status": final_status,
            "job_status": final_status,
            "evaluate_status": "success",
            "archive_status": archive_status,
            "archive_error": archive_error,
            "message": message,
            "report": report,
            "upload_results": upload_results,
            "cleanup_results": cleanup_results,
        }

        job.status = final_status
        job.result_json = _json_dumps(result)
        job.error_message = archive_error
        job.locked_by = ""
        job.locked_at = None
        job.updated_at = finished_at
        db.commit()

        set_task_status(session_id, result)
        clear_interview_session(session_id)
        print(f"💾 面试后台归档完成！Session: {session_id} | 归属用户: {user_email}")
        return result
    except Exception as exc:
        db.rollback()
        job = db.query(BackgroundJob).filter_by(id=job_id).first()
        if job:
            job.retry_count = (job.retry_count or 0) + 1
            can_retry = job.retry_count < (job.max_retries or TASK_MAX_RETRIES)
            job.status = JOB_STATUS_PENDING if can_retry else JOB_STATUS_FAILED
            job.error_message = str(exc)
            job.locked_by = ""
            job.locked_at = None
            job.next_run_at = _now() + timedelta(seconds=min(60, 5 * job.retry_count)) if can_retry else _now()
            job.updated_at = _now()
            job.result_json = _json_dumps(
                {
                    "status": job.status,
                    "job_status": job.status,
                    "evaluate_status": "failed",
                    "archive_status": "pending",
                    "message": "后台处理失败，等待重试" if can_retry else "后台处理失败，请管理员介入",
                    "error": str(exc),
                }
            )
            db.commit()
            set_task_status(job.session_id, _json_loads(job.result_json))
        print(f"❌ 面试后台处理失败: job_id={job_id} error={exc}")
        return {"status": JOB_STATUS_FAILED, "message": str(exc)}
    finally:
        db.close()
        _release_job_lock(job_id)


def retry_archive_for_record(record_id: int) -> dict:
    db = SessionLocal()
    try:
        record = db.query(InterviewRecord).filter_by(id=record_id).first()
        if not record:
            return {"status": "error", "message": "记录不存在"}

        record.retry_count = (record.retry_count or 0) + 1
        record.worker_node_id = WORKER_NODE_ID
        record.processing_started_at = _now()
        record.processing_finished_at = _now()
        record.completed_at = _now()
        if record.av_path:
            record.archive_status = "success"
            record.archive_error = ""
            db.commit()
            return {
                "status": "success",
                "archive_status": "success",
                "archive_error": "",
                "upload_results": {"av": {"status": "success", "url": record.av_path}},
                "cleanup_results": {},
                "message": "OSS URL already exists; no local retry needed",
            }

        record.archive_status = "error"
        record.archive_error = "media OSS url not found; upload API must write media to OSS before worker runs"
        db.commit()
        return {
            "status": "error",
            "archive_status": "error",
            "archive_error": record.archive_error,
            "upload_results": {"av": {"status": "error", "message": record.archive_error}},
            "cleanup_results": {},
            "message": "No OSS media URL to retry",
        }

    except Exception as exc:
        db.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        db.close()


def get_next_pending_job_id(timeout_seconds: int = 2) -> Optional[int]:
    client = get_redis_client()
    if client is not None:
        try:
            item = client.rpop(_queue_key())
        except Exception:
            item = None
        if item:
            try:
                return int(item)
            except (TypeError, ValueError):
                pass

    db = SessionLocal()
    try:
        job = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.job_type == JOB_TYPE_EVALUATE_ARCHIVE,
                BackgroundJob.status == JOB_STATUS_PENDING,
                or_(BackgroundJob.next_run_at == None, BackgroundJob.next_run_at <= _now()),
            )
            .order_by(BackgroundJob.next_run_at.asc(), BackgroundJob.id.asc())
            .first()
        )
        return job.id if job else None
    finally:
        db.close()


def process_pending_jobs(max_jobs: int = 1, poll_interval_seconds: float = 2) -> dict:
    processed = 0
    skipped = 0
    failed = 0
    job_ids = []
    target_jobs = max(1, int(max_jobs or 1))

    while processed + skipped < target_jobs:
        job_id = get_next_pending_job_id(timeout_seconds=max(1, int(poll_interval_seconds)))
        if job_id is None:
            break
        job_ids.append(job_id)
        result = process_interview_job(job_id)
        status = result.get("status")
        if status == "skipped":
            skipped += 1
            continue
        processed += 1
        if status == JOB_STATUS_FAILED:
            failed += 1

    return {
        "status": "success",
        "processed": processed,
        "skipped": skipped,
        "failed": failed,
        "job_ids": job_ids,
    }


def run_worker_forever(poll_interval_seconds: float = 2) -> None:
    print(f"后台任务 Worker 已启动，节点: {WORKER_NODE_ID}")
    while True:
        job_id = get_next_pending_job_id(timeout_seconds=max(1, int(poll_interval_seconds)))
        if job_id is None:
            time.sleep(poll_interval_seconds)
            continue
        process_interview_job(job_id)
