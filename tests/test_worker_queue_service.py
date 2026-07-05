import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_message_type = lambda name: type(name, (), {"__init__": lambda self, content: setattr(self, "content", content)})
sys.modules.setdefault(
    "langchain_openai",
    SimpleNamespace(ChatOpenAI=lambda *args, **kwargs: SimpleNamespace(invoke=lambda messages: None)),
)
sys.modules.setdefault(
    "langchain_core.messages",
    SimpleNamespace(
        HumanMessage=_message_type("HumanMessage"),
        SystemMessage=_message_type("SystemMessage"),
        AIMessage=_message_type("AIMessage"),
    ),
)
sys.modules.setdefault("aliyunsdkcore.client", SimpleNamespace(AcsClient=object))
sys.modules.setdefault("aliyunsdkcore.request", SimpleNamespace(CommonRequest=object))

from core import interview_job_service as jobs


def test_process_pending_jobs_respects_max_jobs(monkeypatch):
    pending = [101, 102, 103]
    processed = []

    def fake_next_job(timeout_seconds=2):
        return pending.pop(0) if pending else None

    def fake_process(job_id):
        processed.append(job_id)
        return {"status": jobs.JOB_STATUS_SUCCESS}

    monkeypatch.setattr(jobs, "get_next_pending_job_id", fake_next_job)
    monkeypatch.setattr(jobs, "process_interview_job", fake_process)

    result = jobs.process_pending_jobs(max_jobs=2, poll_interval_seconds=0)

    assert result["processed"] == 2
    assert result["skipped"] == 0
    assert result["job_ids"] == [101, 102]
    assert processed == [101, 102]
    assert pending == [103]


def test_process_pending_jobs_tracks_skipped_and_failed(monkeypatch):
    pending = [201, 202, 203]
    statuses = {
        201: {"status": "skipped"},
        202: {"status": jobs.JOB_STATUS_FAILED},
        203: {"status": jobs.JOB_STATUS_SUCCESS},
    }

    monkeypatch.setattr(jobs, "get_next_pending_job_id", lambda timeout_seconds=2: pending.pop(0) if pending else None)
    monkeypatch.setattr(jobs, "process_interview_job", lambda job_id: statuses[job_id])

    result = jobs.process_pending_jobs(max_jobs=3, poll_interval_seconds=0)

    assert result["processed"] == 2
    assert result["skipped"] == 1
    assert result["failed"] == 1
    assert result["job_ids"] == [201, 202, 203]
