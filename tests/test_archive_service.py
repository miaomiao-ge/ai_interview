import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.archive_service import archive_session_files, cleanup_session_files


def test_archive_session_files_retries_until_success(monkeypatch):
    audio_file = "E:/fake/session.wav"
    monkeypatch.setattr("core.archive_service.os.path.exists", lambda path: path == audio_file)

    attempts = []

    def flaky_upload(local_file_path, oss_file_name):
        attempts.append((local_file_path, oss_file_name))
        if len(attempts) < 3:
            raise RuntimeError("temporary upload error")
        return {"status": "success", "url": f"https://oss.example/{oss_file_name}", "attempts": len(attempts)}

    result = archive_session_files(
        session_id="abc123",
        files=[{"label": "audio", "local_path": audio_file, "oss_key": "records/audio/abc123.wav"}],
        upload_func=flaky_upload,
        max_retries=3,
    )

    assert result["archive_status"] == "success"
    assert result["upload_results"]["audio"]["attempts"] == 3


def test_archive_session_files_reports_partial_success(monkeypatch):
    audio_file = "E:/fake/session.wav"
    video_file = "E:/fake/session.mkv"
    monkeypatch.setattr("core.archive_service.os.path.exists", lambda path: path in {audio_file, video_file})

    def selective_upload(local_file_path, oss_file_name):
        if oss_file_name.endswith(".wav"):
            return {"status": "success", "url": f"https://oss.example/{oss_file_name}", "attempts": 1}
        raise RuntimeError("video upload failed")

    result = archive_session_files(
        session_id="abc123",
        files=[
            {"label": "audio", "local_path": audio_file, "oss_key": "records/audio/abc123.wav"},
            {"label": "video", "local_path": video_file, "oss_key": "records/video/abc123.mkv"},
        ],
        upload_func=selective_upload,
        max_retries=2,
    )

    assert result["archive_status"] == "partial_success"
    assert result["upload_results"]["audio"]["status"] == "success"
    assert result["upload_results"]["video"]["status"] == "error"


def test_cleanup_session_files_only_removes_session_paths(monkeypatch):
    owned_file = "E:/fake/abc123.wav"
    other_file = "E:/fake/other.wav"
    existing_paths = {owned_file, other_file}

    monkeypatch.setattr("core.archive_service.os.path.exists", lambda path: path in existing_paths)

    def fake_remove(path):
        existing_paths.remove(path)

    monkeypatch.setattr("core.archive_service.os.remove", fake_remove)

    results = cleanup_session_files([owned_file])

    assert results[owned_file]["status"] == "deleted"
    assert owned_file not in existing_paths
    assert other_file in existing_paths
