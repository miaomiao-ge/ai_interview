import json
import os
import shutil
from datetime import datetime
from typing import Tuple
from uuid import uuid4

from core.database import UploadSession

UPLOAD_PARTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media", "upload_parts"
)
MAX_CHUNKS = 400


def _parts_dir(upload_id: str) -> str:
    return os.path.join(UPLOAD_PARTS_DIR, upload_id)


def create_upload(db, session_id: str, total_chunks: int, chunk_size: int) -> UploadSession:
    if total_chunks <= 0 or total_chunks > MAX_CHUNKS:
        raise ValueError("invalid total_chunks")
    record = UploadSession(
        upload_id=uuid4().hex,
        session_id=session_id or "",
        total_chunks=total_chunks,
        chunk_size=chunk_size,
        received_json="[]",
        status="uploading",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    os.makedirs(_parts_dir(record.upload_id), exist_ok=True)
    return record


def _received(record: UploadSession) -> list:
    try:
        return sorted(json.loads(record.received_json or "[]"))
    except ValueError:
        return []


def save_chunk(db, upload_id: str, index: int, data: bytes) -> UploadSession:
    record = db.query(UploadSession).filter(UploadSession.upload_id == upload_id).first()
    if not record:
        raise ValueError("upload not found")
    if index < 0 or index >= record.total_chunks:
        raise ValueError("index out of range")

    directory = _parts_dir(upload_id)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, f"{index:05d}.part"), "wb") as handle:
        handle.write(data)

    received = set(_received(record))
    already_counted = index in received
    received.add(index)
    record.received_json = json.dumps(sorted(received))
    if not already_counted:
        record.bytes_count = (record.bytes_count or 0) + len(data)
    record.updated_at = datetime.now()
    if len(received) == record.total_chunks:
        record.status = "uploaded"
    db.commit()
    db.refresh(record)
    return record


def merge_parts(record: UploadSession) -> Tuple[str, int]:
    directory = _parts_dir(record.upload_id)
    received = _received(record)
    if len(received) != record.total_chunks:
        raise ValueError(f"missing parts: {record.total_chunks - len(received)}")

    merged_path = os.path.join(directory, "merged.bin")
    total = 0
    with open(merged_path, "wb") as target:
        for index in range(record.total_chunks):
            part_path = os.path.join(directory, f"{index:05d}.part")
            with open(part_path, "rb") as source:
                chunk = source.read()
                target.write(chunk)
                total += len(chunk)
    return merged_path, total


def cleanup_parts(upload_id: str) -> None:
    shutil.rmtree(_parts_dir(upload_id), ignore_errors=True)
