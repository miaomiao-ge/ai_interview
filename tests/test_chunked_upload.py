import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.chunked_upload import create_upload, merge_parts, save_chunk
from core.database import Base


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr("core.chunked_upload.UPLOAD_PARTS_DIR", str(tmp_path))
    return tmp_path


def test_save_chunk_tracks_received_indices(db, storage):
    record = create_upload(db, "sess1234", 3, 1024)

    save_chunk(db, record.upload_id, 0, b"abc")
    updated = save_chunk(db, record.upload_id, 2, b"ghi")

    assert updated.received_json == "[0, 2]"


def test_merge_parts_returns_whole_file(db, storage):
    record = create_upload(db, "sess1234", 3, 4)
    save_chunk(db, record.upload_id, 0, b"aaaa")
    save_chunk(db, record.upload_id, 1, b"bbbb")
    save_chunk(db, record.upload_id, 2, b"cccc")

    path, size = merge_parts(record)

    assert size == 12
    with open(path, "rb") as handle:
        assert handle.read() == b"aaaabbbbcccc"


def test_merge_rejects_missing_parts(db, storage):
    record = create_upload(db, "sess1234", 3, 4)
    save_chunk(db, record.upload_id, 0, b"aaaa")

    with pytest.raises(ValueError):
        merge_parts(record)
