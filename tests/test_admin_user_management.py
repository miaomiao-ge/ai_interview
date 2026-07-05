import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.modules.setdefault(
    "pymysql",
    SimpleNamespace(
        paramstyle="pyformat",
        threadsafety=1,
        apilevel="2.0",
        connect=lambda *args, **kwargs: None,
    ),
)

aliyunsdkcore_module = sys.modules.setdefault("aliyunsdkcore", ModuleType("aliyunsdkcore"))
aliyunsdkcore_client = sys.modules.setdefault("aliyunsdkcore.client", ModuleType("aliyunsdkcore.client"))
aliyunsdkcore_request = sys.modules.setdefault("aliyunsdkcore.request", ModuleType("aliyunsdkcore.request"))
aliyunsdkcore_client.AcsClient = getattr(aliyunsdkcore_client, "AcsClient", object)
aliyunsdkcore_request.CommonRequest = getattr(aliyunsdkcore_request, "CommonRequest", object)
aliyunsdkcore_module.client = aliyunsdkcore_client
aliyunsdkcore_module.request = aliyunsdkcore_request

from core import database
from routers import admin_api


class FakeResult:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def mappings(self):
        return self

    def all(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeQuery:
    def __init__(self, session, rows):
        self.session = session
        self.rows = rows
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        self.session.filter_calls.append(dict(kwargs))
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        result = list(self.rows)
        for key, value in self.filters.items():
            result = [row for row in result if getattr(row, key, None) == value]
        return result

    def first(self):
        rows = self.all()
        return rows[0] if rows else None


class FakeSession:
    def __init__(self, table_columns=None, table_indexes=None, query_rows=None, duplicate_rows=None):
        self.table_columns = table_columns or {}
        self.table_indexes = table_indexes or {}
        self.query_rows = query_rows or []
        self.duplicate_rows = list(duplicate_rows or [])
        self.executed_sql = []
        self.commits = 0
        self.rollbacks = 0
        self.closed = False
        self.added = []
        self.deleted = []
        self.filter_calls = []

    def _extract_table_name(self, statement_text, prefix):
        return statement_text[len(prefix):].strip().split()[0]

    def execute(self, statement):
        statement_text = str(statement)
        self.executed_sql.append(statement_text)

        if statement_text.startswith("SHOW COLUMNS FROM "):
            table_name = self._extract_table_name(statement_text, "SHOW COLUMNS FROM ")
            rows = [{"Field": name} for name in self.table_columns.get(table_name, [])]
            return FakeResult(rows)

        if statement_text.startswith("SHOW INDEX FROM "):
            table_name = self._extract_table_name(statement_text, "SHOW INDEX FROM ")
            return FakeResult(self.table_indexes.get(table_name, []))

        if statement_text.startswith("SELECT ") and "FROM admin_users" in statement_text:
            return FakeResult(self.duplicate_rows)

        return FakeResult([])

    def query(self, model):
        rows = self.query_rows.get(model, []) if isinstance(self.query_rows, dict) else self.query_rows
        return FakeQuery(self, rows)

    def add(self, obj):
        self.added.append(obj)

    def delete(self, obj):
        self.deleted.append(obj)
        if isinstance(self.query_rows, dict):
            for rows in self.query_rows.values():
                if obj in rows:
                    rows.remove(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def run_async(coro):
    return asyncio.run(coro)


def make_authorization_token(admin_id=1, username="root_admin", role="super_admin", password="hashed-password"):
    payload = {
        "admin_id": admin_id,
        "username": username,
        "role": role,
        "pwd_sig": admin_api.build_admin_token_signature(password),
        "exp": datetime.utcnow() + timedelta(hours=1),
    }
    token = jwt.encode(payload, admin_api.SECRET_KEY, algorithm=admin_api.ALGORITHM)
    return f"Bearer {token}"


def test_admin_user_model_exposes_management_fields():
    admin_columns = database.AdminUser.__table__.c

    assert "status" in admin_columns
    assert "display_name" in admin_columns
    assert "email" in admin_columns
    assert "last_login_at" in admin_columns
    assert "created_by" in admin_columns
    assert admin_columns.email.unique is True


def test_admin_action_log_model_exists_with_audit_fields():
    log_columns = database.AdminActionLog.__table__.c

    assert hasattr(database, "AdminActionLog")
    assert "admin_id" in log_columns
    assert "username_snapshot" in log_columns
    assert "action" in log_columns
    assert "target_admin_id" in log_columns
    assert "target_username" in log_columns
    assert "result" in log_columns
    assert "detail" in log_columns
    assert "created_at" in log_columns


def test_mysql_url_can_be_configured_from_environment(monkeypatch):
    monkeypatch.setenv("MYSQL_URL", "mysql+pymysql://app:secret@db-host:3306/interview_db?charset=utf8mb4")

    assert database.get_mysql_url() == "mysql+pymysql://app:secret@db-host:3306/interview_db?charset=utf8mb4"


def test_ensure_admin_user_schema_adds_missing_columns_and_email_index():
    session = FakeSession(
        table_columns={"admin_users": ["id", "username", "password", "role", "created_at"]},
        table_indexes={"admin_users": []},
        duplicate_rows=[],
    )

    database.ensure_admin_user_schema(session)

    assert any("ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN display_name VARCHAR(50) DEFAULT ''" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN email VARCHAR(100) NULL" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN last_login_at DATETIME NULL" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN created_by INT NULL" in sql for sql in session.executed_sql)
    assert any("MODIFY COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'" in sql for sql in session.executed_sql)
    assert any("ADD UNIQUE INDEX uq_admin_users_email (email)" in sql for sql in session.executed_sql)
    assert session.commits >= 1


def test_ensure_admin_action_log_schema_adds_audit_columns():
    session = FakeSession(table_columns={"admin_action_logs": ["id"]}, table_indexes={"admin_action_logs": []})

    database.ensure_admin_action_log_schema(session)

    assert any("ADD COLUMN admin_id INT NULL" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN username_snapshot VARCHAR(50) DEFAULT ''" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN action VARCHAR(50) NULL DEFAULT 'legacy_action'" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN target_admin_id INT NULL" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN target_username VARCHAR(50) DEFAULT ''" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN result VARCHAR(20) DEFAULT 'success'" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN detail TEXT" in sql for sql in session.executed_sql)
    assert any("ADD COLUMN created_at DATETIME NULL" in sql for sql in session.executed_sql)
    assert any("UPDATE admin_action_logs SET action='legacy_action'" in sql for sql in session.executed_sql)
    assert any("MODIFY COLUMN action VARCHAR(50) NOT NULL DEFAULT 'legacy_action'" in sql for sql in session.executed_sql)
    assert session.commits >= 2


def test_ensure_admin_user_schema_raises_on_duplicate_emails():
    session = FakeSession(
        table_columns={"admin_users": ["id", "username", "password", "role", "email", "created_at"]},
        table_indexes={"admin_users": []},
        duplicate_rows=[{"email": "dup@example.com"}],
    )

    with pytest.raises(RuntimeError, match="Duplicate admin_users.email values"):
        database.ensure_admin_user_schema(session)


def test_init_db_surfaces_helper_failures(monkeypatch):
    session = FakeSession(query_rows=[])
    calls = []

    monkeypatch.setattr(database.Base.metadata, "create_all", lambda bind: calls.append(("create_all", bind)))
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    monkeypatch.setattr(database, "ensure_interview_record_schema", lambda db: calls.append(("ensure_interview_record_schema", db)))

    def boom(db):
        calls.append(("ensure_admin_user_schema", db))
        raise RuntimeError("schema boom")

    monkeypatch.setattr(database, "ensure_admin_user_schema", boom)
    monkeypatch.setattr(database, "ensure_admin_action_log_schema", lambda db: calls.append(("ensure_admin_action_log_schema", db)))

    with pytest.raises(RuntimeError, match="schema boom"):
        database.init_db()

    assert calls[0] == ("create_all", database.engine)
    assert session.rollbacks == 1
    assert session.closed is True


def test_init_db_bootstraps_only_super_admin_and_skips_default_admin(monkeypatch):
    session = FakeSession(query_rows=[])
    calls = []

    monkeypatch.setattr(database.Base.metadata, "create_all", lambda bind: calls.append(("create_all", bind)))
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    monkeypatch.setattr(database, "ensure_interview_record_schema", lambda db: calls.append(("ensure_interview_record_schema", db)))
    monkeypatch.setattr(database, "ensure_admin_user_schema", lambda db: calls.append(("ensure_admin_user_schema", db)))
    monkeypatch.setattr(database, "ensure_admin_action_log_schema", lambda db: calls.append(("ensure_admin_action_log_schema", db)))
    monkeypatch.setattr(database, "hash_admin_password", lambda password: "hashed:{0}".format(password))
    monkeypatch.setenv("SUPER_ADMIN_USERNAME", "root_admin")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "root_password")
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "normal_admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "normal_password")

    database.init_db()

    assert calls[0] == ("create_all", database.engine)
    assert ("ensure_interview_record_schema", session) in calls
    assert ("ensure_admin_user_schema", session) in calls
    assert ("ensure_admin_action_log_schema", session) in calls
    assert len(session.added) == 1
    bootstrap_admin = session.added[0]
    assert bootstrap_admin.username == "root_admin"
    assert bootstrap_admin.role == "super_admin"
    assert bootstrap_admin.status == "active"
    assert bootstrap_admin.display_name == "root_admin"
    assert not any(call.get("username") == "normal_admin" for call in session.filter_calls)
    assert session.closed is True


def test_init_db_promotes_existing_matching_admin_username(monkeypatch):
    existing_admin = SimpleNamespace(
        id=7,
        username="root_admin",
        password="existing_hash",
        role="admin",
        status=None,
        display_name="",
        email=None,
        last_login_at=None,
        created_by=None,
    )
    session = FakeSession(query_rows=[existing_admin])
    calls = []

    monkeypatch.setattr(database.Base.metadata, "create_all", lambda bind: calls.append(("create_all", bind)))
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    monkeypatch.setattr(database, "ensure_interview_record_schema", lambda db: calls.append(("ensure_interview_record_schema", db)))
    monkeypatch.setattr(database, "ensure_admin_user_schema", lambda db: calls.append(("ensure_admin_user_schema", db)))
    monkeypatch.setattr(database, "ensure_admin_action_log_schema", lambda db: calls.append(("ensure_admin_action_log_schema", db)))
    monkeypatch.setattr(database, "hash_admin_password", lambda password: "hashed:{0}".format(password))
    monkeypatch.setenv("SUPER_ADMIN_USERNAME", "root_admin")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "root_password")

    database.init_db()

    assert calls[0] == ("create_all", database.engine)
    assert len(session.added) == 0
    assert existing_admin.role == "super_admin"
    assert existing_admin.status == "active"
    assert existing_admin.display_name == "root_admin"
    assert existing_admin.password == "existing_hash"
    assert session.closed is True


def test_init_db_normalizes_extra_super_admins(monkeypatch):
    keeper = SimpleNamespace(
        id=1,
        username="keeper_admin",
        password="hashed",
        role="super_admin",
        status=None,
        display_name="",
        email=None,
        last_login_at=None,
        created_by=None,
    )
    extra = SimpleNamespace(
        id=2,
        username="legacy_admin",
        password="hashed",
        role="super_admin",
        status=None,
        display_name="",
        email=None,
        last_login_at=None,
        created_by=None,
    )
    session = FakeSession(query_rows=[keeper, extra])

    monkeypatch.setattr(database.Base.metadata, "create_all", lambda bind: None)
    monkeypatch.setattr(database, "SessionLocal", lambda: session)
    monkeypatch.setattr(database, "ensure_interview_record_schema", lambda db: None)
    monkeypatch.setattr(database, "ensure_admin_user_schema", lambda db: None)
    monkeypatch.setattr(database, "ensure_admin_action_log_schema", lambda db: None)
    monkeypatch.setenv("SUPER_ADMIN_USERNAME", "keeper_admin")
    monkeypatch.setenv("SUPER_ADMIN_PASSWORD", "root_password")

    database.init_db()

    assert keeper.role == "super_admin"
    assert keeper.status == "active"
    assert keeper.display_name == "keeper_admin"
    assert extra.role == "admin"
    assert extra.status == "active"
    assert extra.display_name == "legacy_admin"
    assert session.commits >= 1
    assert session.closed is True


def test_disabled_admin_cannot_login():
    admin = SimpleNamespace(
        id=1,
        username="ops01",
        password=admin_api.hash_admin_password("secret"),
        role="admin",
        status="disabled",
    )

    assert admin_api.is_admin_login_allowed(admin) is False


def test_active_admin_can_login_by_default():
    admin = SimpleNamespace(id=1, username="ops01", status="active")

    assert admin_api.is_admin_login_allowed(admin) is True


def test_has_super_admin_privilege_only_for_super_admin():
    assert admin_api.has_super_admin_privilege({"role": "super_admin"}) is True
    assert admin_api.has_super_admin_privilege({"role": "admin"}) is False


def test_cannot_disable_last_active_super_admin():
    admins = [
        SimpleNamespace(id=1, role="super_admin", status="active"),
        SimpleNamespace(id=2, role="admin", status="active"),
    ]

    assert admin_api.can_toggle_admin_status(admins, target_admin_id=1, next_status="disabled") is False


def test_can_disable_non_last_super_admin():
    admins = [
        SimpleNamespace(id=1, role="super_admin", status="active"),
        SimpleNamespace(id=2, role="super_admin", status="active"),
    ]

    assert admin_api.can_toggle_admin_status(admins, target_admin_id=1, next_status="disabled") is True


def test_verify_admin_token_rejects_disabled_admin(monkeypatch):
    disabled_admin = SimpleNamespace(
        id=7,
        username="ops01",
        role="admin",
        status="disabled",
        password=admin_api.hash_admin_password("secret"),
    )
    session = FakeSession(query_rows={admin_api.AdminUser: [disabled_admin]})

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    with pytest.raises(HTTPException) as exc_info:
        admin_api.verify_admin_token(
            make_authorization_token(
                admin_id=7,
                username="ops01",
                role="admin",
                password=disabled_admin.password,
            )
        )

    assert exc_info.value.status_code == 401


def test_verify_admin_token_rejects_nonexistent_admin(monkeypatch):
    session = FakeSession(query_rows={admin_api.AdminUser: []})

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    with pytest.raises(HTTPException) as exc_info:
        admin_api.verify_admin_token(
            make_authorization_token(admin_id=999, username="ghost", role="admin", password=admin_api.hash_admin_password("ghost"))
        )

    assert exc_info.value.status_code == 401


def test_login_success_updates_last_login_and_writes_login_record(monkeypatch):
    admin = SimpleNamespace(
        id=3,
        username="ops01",
        password=admin_api.hash_admin_password("secret"),
        role="admin",
        status="active",
        last_login_at=None,
    )
    session = FakeSession(query_rows={admin_api.AdminUser: [admin], admin_api.AdminLoginRecord: []})
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    result = run_async(admin_api.admin_login(admin_api.AdminLoginRequest(username="ops01", password="secret"), request))

    assert result["status"] == "success"
    assert result["role"] == "admin"
    assert result["username"] == "ops01"
    assert result["token"]
    assert admin.last_login_at is not None
    assert session.commits >= 1
    assert any(isinstance(item, admin_api.AdminLoginRecord) and item.login_status == "success" for item in session.added)


def test_disabled_login_returns_error_and_writes_failed_record(monkeypatch):
    admin = SimpleNamespace(
        id=8,
        username="disabled01",
        password=admin_api.hash_admin_password("secret"),
        role="admin",
        status="disabled",
        last_login_at=None,
    )
    session = FakeSession(query_rows={admin_api.AdminUser: [admin], admin_api.AdminLoginRecord: []})
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    result = run_async(
        admin_api.admin_login(admin_api.AdminLoginRequest(username="disabled01", password="secret"), request)
    )

    assert result["status"] == "error"
    assert admin.last_login_at is None
    assert any(isinstance(item, admin_api.AdminLoginRecord) and item.login_status == "failed" for item in session.added)


def test_create_admin_success_writes_action_log(monkeypatch):
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}
    session = FakeSession(query_rows={admin_api.AdminUser: [], admin_api.AdminActionLog: []})

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)

    result = run_async(
        admin_api.create_admin_user(
            admin_api.AdminCreateRequest(
                username="new_admin",
                password="secret123",
                role="admin",
                display_name="New Admin",
                email="new_admin@example.com",
            ),
            authorization="Bearer token",
        )
    )

    assert result["status"] == "success"
    assert any(isinstance(item, admin_api.AdminUser) and item.username == "new_admin" for item in session.added)
    assert any(isinstance(item, admin_api.AdminActionLog) and item.action == "create_admin" for item in session.added)


def test_delete_admin_record_removes_interview_record(monkeypatch):
    record = SimpleNamespace(id=12, session_id="abc123", user_email="candidate@example.com")
    session = FakeSession(query_rows={admin_api.InterviewRecord: [record], admin_api.AdminActionLog: []})
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}

    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)
    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    result = run_async(admin_api.delete_admin_record(12, authorization="Bearer token"))

    assert result["status"] == "success"
    assert record in session.deleted
    assert any(
        isinstance(item, admin_api.AdminActionLog)
        and item.action == "delete_interview_record"
        and "session_id=abc123" in item.detail
        for item in session.added
    )
    assert session.commits == 1
    assert session.closed is True


def test_delete_admin_record_returns_error_when_missing(monkeypatch):
    session = FakeSession(query_rows={admin_api.InterviewRecord: []})
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}

    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)
    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    result = run_async(admin_api.delete_admin_record(99, authorization="Bearer token"))

    assert result == {"status": "error", "message": "记录不存在"}
    assert session.deleted == []
    assert session.commits == 0
    assert session.closed is True


def test_delete_admin_record_requires_super_admin(monkeypatch):
    calls = []

    def fake_verify(authorization, require_super=False):
        calls.append(require_super)
        raise HTTPException(status_code=403, detail="权限不足")

    monkeypatch.setattr(admin_api, "verify_admin_token", fake_verify)

    with pytest.raises(HTTPException) as exc_info:
        run_async(admin_api.delete_admin_record(12, authorization="Bearer token"))

    assert exc_info.value.status_code == 403
    assert calls == [True]


def test_batch_delete_admin_records_removes_selected_records(monkeypatch):
    records = [
        SimpleNamespace(id=12, session_id="abc123", user_email="candidate@example.com"),
        SimpleNamespace(id=13, session_id="def456", user_email="candidate2@example.com"),
        SimpleNamespace(id=14, session_id="keep789", user_email="keep@example.com"),
    ]
    session = FakeSession(query_rows={admin_api.InterviewRecord: records, admin_api.AdminActionLog: []})
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}

    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)
    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    result = run_async(
        admin_api.batch_delete_admin_records(
            admin_api.RecordBatchDeleteRequest(ids=[12, 13, 13]),
            authorization="Bearer token",
        )
    )

    assert result["status"] == "success"
    assert set(result["deleted_ids"]) == {12, 13}
    assert [item.id for item in session.deleted] == [12, 13]
    assert records == [SimpleNamespace(id=14, session_id="keep789", user_email="keep@example.com")]
    assert any(
        isinstance(item, admin_api.AdminActionLog)
        and item.action == "batch_delete_interview_records"
        and "session_id=abc123" in item.detail
        and "session_id=def456" in item.detail
        for item in session.added
    )
    assert session.commits == 1
    assert session.closed is True


def test_batch_delete_admin_records_returns_error_when_no_selection(monkeypatch):
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}
    session = FakeSession(query_rows={admin_api.InterviewRecord: []})

    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)
    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    result = run_async(
        admin_api.batch_delete_admin_records(
            admin_api.RecordBatchDeleteRequest(ids=[]),
            authorization="Bearer token",
        )
    )

    assert result == {"status": "error", "message": "请先选择要删除的面试记录"}
    assert session.deleted == []
    assert session.commits == 0
    assert session.closed is False


def test_batch_delete_admin_records_requires_super_admin(monkeypatch):
    calls = []

    def fake_verify(authorization, require_super=False):
        calls.append(require_super)
        raise HTTPException(status_code=403, detail="权限不足")

    monkeypatch.setattr(admin_api, "verify_admin_token", fake_verify)

    with pytest.raises(HTTPException) as exc_info:
        run_async(
            admin_api.batch_delete_admin_records(
                admin_api.RecordBatchDeleteRequest(ids=[12]),
                authorization="Bearer token",
            )
        )

    assert exc_info.value.status_code == 403
    assert calls == [True]


def test_create_admin_rejects_duplicate_email(monkeypatch):
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}
    existing_admin = SimpleNamespace(
        id=5,
        username="existing",
        password="hashed",
        role="admin",
        status="active",
        display_name="Existing",
        email="dup@example.com",
        created_by=1,
    )
    session = FakeSession(query_rows={admin_api.AdminUser: [existing_admin], admin_api.AdminActionLog: []})

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)

    result = run_async(
        admin_api.create_admin_user(
            admin_api.AdminCreateRequest(
                username="new_admin",
                password="secret123",
                role="admin",
                display_name="New Admin",
                email="dup@example.com",
            ),
            authorization="Bearer token",
        )
    )

    assert result["status"] == "error"
    assert len(session.added) == 0


def test_toggle_status_rejects_disabling_last_super_admin(monkeypatch):
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}
    super_admin = SimpleNamespace(
        id=1,
        username="root_admin",
        password="hashed",
        role="super_admin",
        status="active",
        display_name="Root",
        email=None,
        created_by=None,
    )
    normal_admin = SimpleNamespace(
        id=2,
        username="ops01",
        password="hashed",
        role="admin",
        status="active",
        display_name="Ops",
        email=None,
        created_by=1,
    )
    session = FakeSession(
        query_rows={
            admin_api.AdminUser: [super_admin, normal_admin],
            admin_api.AdminActionLog: [],
        }
    )

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)

    result = run_async(
        admin_api.toggle_admin_status(
            1,
            admin_api.AdminStatusToggleRequest(status="disabled"),
            authorization="Bearer token",
        )
    )

    assert result["status"] == "error"
    assert super_admin.status == "active"


def test_toggle_status_success_writes_action_log(monkeypatch):
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}
    super_admin = SimpleNamespace(
        id=1,
        username="root_admin",
        password="hashed",
        role="super_admin",
        status="active",
        display_name="Root",
        email=None,
        created_by=None,
    )
    normal_admin = SimpleNamespace(
        id=2,
        username="ops01",
        password="hashed",
        role="admin",
        status="active",
        display_name="Ops",
        email=None,
        created_by=1,
    )
    session = FakeSession(
        query_rows={
            admin_api.AdminUser: [super_admin, normal_admin],
            admin_api.AdminActionLog: [],
        }
    )

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)

    result = run_async(
        admin_api.toggle_admin_status(
            2,
            admin_api.AdminStatusToggleRequest(status="disabled"),
            authorization="Bearer token",
        )
    )

    assert result["status"] == "success"
    assert normal_admin.status == "disabled"
    assert any(
        isinstance(item, admin_api.AdminActionLog) and item.action == "toggle_admin_status"
        for item in session.added
    )


def test_prompt_endpoints_require_super_admin(monkeypatch):
    calls = []

    def fake_verify(authorization, require_super=False):
        calls.append(require_super)
        return {"admin_id": 1, "username": "root_admin", "role": "super_admin"}

    session = FakeSession(query_rows={admin_api.PromptConfig: []})
    monkeypatch.setattr(admin_api, "verify_admin_token", fake_verify)
    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    result = run_async(admin_api.get_prompts(authorization="Bearer token"))

    assert result["status"] == "success"
    assert calls == [True]


def test_admin_management_endpoints_require_super_admin(monkeypatch):
    calls = []
    target_admin = SimpleNamespace(
        id=2,
        username="ops01",
        password="hashed",
        role="admin",
        status="active",
        display_name="Ops",
        email=None,
        created_by=1,
        last_login_at=None,
        created_at=None,
    )
    session = FakeSession(
        query_rows={
            admin_api.AdminUser: [target_admin],
            admin_api.AdminLoginRecord: [],
            admin_api.AdminActionLog: [],
        }
    )

    def fake_verify(authorization, require_super=False):
        calls.append(require_super)
        return {"admin_id": 1, "username": "root_admin", "role": "super_admin"}

    monkeypatch.setattr(admin_api, "verify_admin_token", fake_verify)
    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    run_async(admin_api.get_admin_users(authorization="Bearer token"))
    run_async(
        admin_api.create_admin_user(
            admin_api.AdminCreateRequest(
                username="new_admin",
                password="secret123",
                role="admin",
                display_name="New Admin",
                email="new_admin@example.com",
            ),
            authorization="Bearer token",
        )
    )
    run_async(
        admin_api.update_admin_user(
            2,
            admin_api.AdminUpdateRequest(role="admin", display_name="Ops Updated", email=""),
            authorization="Bearer token",
        )
    )
    run_async(
        admin_api.reset_admin_password(
            2,
            admin_api.AdminPasswordResetRequest(new_password="newsecret"),
            authorization="Bearer token",
        )
    )
    run_async(
        admin_api.toggle_admin_status(
            2,
            admin_api.AdminStatusToggleRequest(status="disabled"),
            authorization="Bearer token",
        )
    )
    run_async(admin_api.get_admin_login_records(authorization="Bearer token"))
    run_async(admin_api.get_admin_action_logs(authorization="Bearer token"))

    assert calls == [True, True, True, True, True, True, True]


def test_verify_admin_password_does_not_accept_hash_as_secret():
    stored_password = admin_api.hash_admin_password("secret123")

    assert admin_api.verify_admin_password("secret123", stored_password) is True
    assert admin_api.verify_admin_password(stored_password, stored_password) is False


def test_password_signature_invalidates_old_tokens_after_password_change(monkeypatch):
    admin_user = SimpleNamespace(
        id=9,
        username="ops01",
        role="admin",
        status="active",
        password=admin_api.hash_admin_password("new-secret"),
    )
    session = FakeSession(query_rows={admin_api.AdminUser: [admin_user]})
    old_token = make_authorization_token(
        admin_id=9,
        username="ops01",
        role="admin",
        password=admin_api.hash_admin_password("old-secret"),
    )

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    with pytest.raises(HTTPException) as exc_info:
        admin_api.verify_admin_token(old_token)

    assert exc_info.value.status_code == 401


def test_non_super_admin_token_is_rejected_by_admin_management_endpoint(monkeypatch):
    non_super_admin = SimpleNamespace(
        id=2,
        username="ops01",
        role="admin",
        status="active",
        password=admin_api.hash_admin_password("secret"),
        display_name="Ops",
        email=None,
        created_by=1,
        last_login_at=None,
        created_at=None,
    )
    session = FakeSession(query_rows={admin_api.AdminUser: [non_super_admin]})

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)

    with pytest.raises(HTTPException) as exc_info:
        run_async(
            admin_api.get_admin_users(
                authorization=make_authorization_token(
                    admin_id=2,
                    username="ops01",
                    role="admin",
                    password=non_super_admin.password,
                )
            )
        )

    assert exc_info.value.status_code == 403


def test_update_admin_rejects_demoting_last_active_super_admin(monkeypatch):
    operator = {"admin_id": 1, "username": "root_admin", "role": "super_admin"}
    target = SimpleNamespace(
        id=1,
        username="root_admin",
        password=admin_api.hash_admin_password("secret"),
        role="super_admin",
        status="active",
        display_name="Root",
        email=None,
        created_by=None,
        last_login_at=None,
        created_at=None,
    )
    session = FakeSession(query_rows={admin_api.AdminUser: [target], admin_api.AdminActionLog: []})

    monkeypatch.setattr(admin_api, "SessionLocal", lambda: session)
    monkeypatch.setattr(admin_api, "verify_admin_token", lambda authorization, require_super=False: operator)

    result = run_async(
        admin_api.update_admin_user(
            1,
            admin_api.AdminUpdateRequest(role="admin", display_name="Root", email=""),
            authorization="Bearer token",
        )
    )

    assert result["status"] == "error"
    assert target.role == "super_admin"
