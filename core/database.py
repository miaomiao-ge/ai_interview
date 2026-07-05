import hashlib
import os
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import Column, Date, DateTime, Float, Integer, String, Text, create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import (
    APP_ENV,
    DB_AUTO_MIGRATE_ON_STARTUP,
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    MYSQL_URL_ENV,
    SUPER_ADMIN_PASSWORD,
    SUPER_ADMIN_USERNAME,
)

load_dotenv()

# 声明数据库模型基类
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(100), unique=True, nullable=False, comment="用户邮箱")
    real_name = Column(String(100), default="")
    passport_no = Column(String(100), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    status = Column(String(20), default="active", nullable=False)
    face_image_oss_key = Column(String(255), default="")
    face_enrolled_at = Column(DateTime, nullable=True)
    face_image_source = Column(String(50), default="")
    xidian_application_no = Column(String(50), unique=True, nullable=True)
    xidian_application_status = Column(String(50), default="")
    family_name = Column(String(100), default="")
    given_name = Column(String(100), default="")
    gender = Column(String(30), default="")
    nationality = Column(String(100), default="")
    passport_expiry = Column(Date, nullable=True)
    birthday = Column(Date, nullable=True)
    official_photo_synced_at = Column(DateTime, nullable=True)
    remark = Column(Text)
    source = Column(String(50), default="self_register")
    imported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, comment="注册时间")


class InterviewRecord(Base):
    __tablename__ = "interview_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_email = Column(String(100), index=True, comment="候选人邮箱")
    session_id = Column(String(50), unique=True, comment="面试会话 ID")
    chat_history = Column(Text, comment="完整面试对话记录")
    evaluation_result = Column(Text, comment="大模型评价结果")
    evaluation_result_json = Column(Text, comment="结构化评价 JSON")
    audio_path = Column(String(255), comment="纯音频文件路径")
    video_path = Column(String(255), comment="纯视频文件路径")
    av_path = Column(String(255), comment="音视频文件路径")
    archive_status = Column(String(50), default="pending", index=True, comment="归档状态")
    archive_error = Column(Text, comment="归档错误")
    evaluate_status = Column(String(50), default="pending", index=True, comment="评价状态")
    evaluate_error = Column(Text, comment="评价错误")
    processing_started_at = Column(DateTime, nullable=True, comment="处理开始时间")
    processing_finished_at = Column(DateTime, nullable=True, comment="处理完成时间")
    submitted_at = Column(DateTime, nullable=True, comment="用户提交时间")
    completed_at = Column(DateTime, nullable=True, comment="任务完成时间")
    media_policy = Column(String(50), default="av_only", comment="媒体录制策略")
    worker_node_id = Column(String(100), default="", comment="处理节点")
    retry_count = Column(Integer, default=0, comment="重试次数")
    face_verify_status = Column(String(50), default="pending")
    face_verify_score = Column(Float, nullable=True)
    face_verify_at = Column(DateTime, nullable=True)
    face_verify_snapshot_oss_key = Column(String(255), default="")
    identity_doc_oss_key = Column(String(255), default="")
    proctoring_risk_level = Column(String(50), default="none")
    proctoring_flags_json = Column(Text)
    review_status = Column(String(50), default="待复核", comment="人工复核状态：待复核 / 拟录取 / 淘汰")
    review_remark = Column(Text, comment="人工复核备注")
    created_at = Column(DateTime, default=datetime.now, comment="面试创建时间")


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), index=True, nullable=False, comment="面试会话 ID")
    job_type = Column(String(50), index=True, nullable=False, comment="任务类型")
    status = Column(String(50), index=True, default="pending", comment="任务状态")
    payload_json = Column(Text, comment="任务参数 JSON")
    result_json = Column(Text, comment="任务结果 JSON")
    error_message = Column(Text, comment="错误信息")
    retry_count = Column(Integer, default=0, comment="重试次数")
    max_retries = Column(Integer, default=3, comment="最大重试次数")
    next_run_at = Column(DateTime, index=True, default=datetime.now, comment="下次执行时间")
    locked_by = Column(String(100), default="", comment="锁定节点")
    locked_at = Column(DateTime, nullable=True, comment="锁定时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, comment="更新时间")


class ProctoringEvent(Base):
    __tablename__ = "proctoring_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), index=True, nullable=False)
    user_email = Column(String(100), index=True, nullable=False)
    event_type = Column(String(80), index=True, nullable=False)
    risk_level = Column(String(50), default="low")
    image_oss_key = Column(String(255), default="")
    raw_result_json = Column(Text)
    client_captured_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


# 题库表
class QuestionBank(Base):
    __tablename__ = "question_bank"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(100), index=True, comment="考核维度，如综合素质")
    content = Column(Text, comment="题目内容")


# Prompt 系统提示词配置表
class PromptConfig(Base):
    __tablename__ = "prompt_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_key = Column(String(50), unique=True, index=True, comment="提示词配置键：base_prompt / eval_prompt")
    config_value = Column(Text, comment="提示词内容")


# 管理端用户表
class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="管理员账号")
    password = Column(String(255), nullable=False, comment="管理员密码 SHA256 哈希")
    role = Column(String(20), default="admin", comment="角色：super_admin / admin")
    status = Column(String(20), default="active", nullable=False, comment="状态：active / disabled")
    display_name = Column(String(50), default="", comment="管理员显示名")
    email = Column(String(100), unique=True, nullable=True, comment="管理员邮箱")
    last_login_at = Column(DateTime, nullable=True, comment="最近登录时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    created_by = Column(Integer, nullable=True, comment="创建人管理员 ID")


class AdminActionLog(Base):
    __tablename__ = "admin_action_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, nullable=True, comment="操作人管理员 ID")
    username_snapshot = Column(String(50), default="", comment="操作人账号快照")
    action = Column(String(50), nullable=False, comment="操作类型")
    target_admin_id = Column(Integer, nullable=True, comment="目标管理员 ID")
    target_username = Column(String(50), default="", comment="目标管理员账号")
    result = Column(String(20), default="success", comment="操作结果：success / failed")
    detail = Column(Text, comment="操作说明")
    created_at = Column(DateTime, default=datetime.now, comment="操作时间")


class AdminLoginRecord(Base):
    __tablename__ = "admin_login_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), index=True, nullable=False, comment="登录管理员账号")
    role = Column(String(20), default="", comment="登录时角色快照")
    login_status = Column(String(20), nullable=False, comment="登录结果：success / failed")
    client_ip = Column(String(64), comment="登录客户端 IP")
    message = Column(String(255), comment="登录说明")
    created_at = Column(DateTime, default=datetime.now, comment="登录时间")


def hash_admin_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def ensure_interview_record_schema(db):
    """补齐面试记录表中的新字段，并确保 user_email 使用普通索引。"""
    columns = db.execute(text("SHOW COLUMNS FROM interview_records")).mappings().all()
    column_names = {item["Field"] for item in columns}

    schema_changes = [
        ("evaluation_result_json", "ALTER TABLE interview_records ADD COLUMN evaluation_result_json TEXT"),
        ("archive_status", "ALTER TABLE interview_records ADD COLUMN archive_status VARCHAR(50) DEFAULT 'pending'"),
        ("archive_error", "ALTER TABLE interview_records ADD COLUMN archive_error TEXT"),
        ("evaluate_status", "ALTER TABLE interview_records ADD COLUMN evaluate_status VARCHAR(50) DEFAULT 'pending'"),
        ("evaluate_error", "ALTER TABLE interview_records ADD COLUMN evaluate_error TEXT"),
        ("processing_started_at", "ALTER TABLE interview_records ADD COLUMN processing_started_at DATETIME NULL"),
        ("processing_finished_at", "ALTER TABLE interview_records ADD COLUMN processing_finished_at DATETIME NULL"),
        ("submitted_at", "ALTER TABLE interview_records ADD COLUMN submitted_at DATETIME NULL"),
        ("completed_at", "ALTER TABLE interview_records ADD COLUMN completed_at DATETIME NULL"),
        ("media_policy", "ALTER TABLE interview_records ADD COLUMN media_policy VARCHAR(50) DEFAULT 'av_only'"),
        ("worker_node_id", "ALTER TABLE interview_records ADD COLUMN worker_node_id VARCHAR(100) DEFAULT ''"),
        ("retry_count", "ALTER TABLE interview_records ADD COLUMN retry_count INT DEFAULT 0"),
        ("face_verify_status", "ALTER TABLE interview_records ADD COLUMN face_verify_status VARCHAR(50) DEFAULT 'pending'"),
        ("face_verify_score", "ALTER TABLE interview_records ADD COLUMN face_verify_score FLOAT NULL"),
        ("face_verify_at", "ALTER TABLE interview_records ADD COLUMN face_verify_at DATETIME NULL"),
        ("face_verify_snapshot_oss_key", "ALTER TABLE interview_records ADD COLUMN face_verify_snapshot_oss_key VARCHAR(255) DEFAULT ''"),
        ("identity_doc_oss_key", "ALTER TABLE interview_records ADD COLUMN identity_doc_oss_key VARCHAR(255) DEFAULT ''"),
        ("proctoring_risk_level", "ALTER TABLE interview_records ADD COLUMN proctoring_risk_level VARCHAR(50) DEFAULT 'none'"),
        ("proctoring_flags_json", "ALTER TABLE interview_records ADD COLUMN proctoring_flags_json TEXT"),
    ]

    altered = False
    for column_name, sql_statement in schema_changes:
        if column_name not in column_names:
            db.execute(text(sql_statement))
            altered = True
    if altered:
        db.commit()

    indexes = db.execute(text("SHOW INDEX FROM interview_records")).mappings().all()
    has_user_email_index = False
    for item in indexes:
        if item["Column_name"] == "user_email":
            has_user_email_index = True
        if item["Column_name"] == "user_email" and int(item["Non_unique"]) == 0:
            db.execute(text(f"ALTER TABLE interview_records DROP INDEX {item['Key_name']}"))
            db.commit()
            has_user_email_index = False

    if not has_user_email_index:
        db.execute(text("ALTER TABLE interview_records ADD INDEX idx_interview_records_user_email (user_email)"))
        db.commit()

    index_names = {item["Key_name"] for item in indexes}
    if "idx_interview_records_archive_status" not in index_names:
        db.execute(text("ALTER TABLE interview_records ADD INDEX idx_interview_records_archive_status (archive_status)"))
        db.commit()
    if "idx_interview_records_evaluate_status" not in index_names:
        db.execute(text("ALTER TABLE interview_records ADD INDEX idx_interview_records_evaluate_status (evaluate_status)"))
        db.commit()


def ensure_user_face_schema(db):
    columns = _get_column_names(db, "users")
    current_columns = set(columns)
    schema_changes = [
        ("real_name", "ALTER TABLE users ADD COLUMN real_name VARCHAR(100) DEFAULT ''"),
        ("passport_no", "ALTER TABLE users ADD COLUMN passport_no VARCHAR(100) NULL"),
        ("status", "ALTER TABLE users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"),
        ("face_image_oss_key", "ALTER TABLE users ADD COLUMN face_image_oss_key VARCHAR(255) DEFAULT ''"),
        ("face_enrolled_at", "ALTER TABLE users ADD COLUMN face_enrolled_at DATETIME NULL"),
        ("face_image_source", "ALTER TABLE users ADD COLUMN face_image_source VARCHAR(50) DEFAULT ''"),
        ("xidian_application_no", "ALTER TABLE users ADD COLUMN xidian_application_no VARCHAR(50) NULL"),
        ("xidian_application_status", "ALTER TABLE users ADD COLUMN xidian_application_status VARCHAR(50) DEFAULT ''"),
        ("family_name", "ALTER TABLE users ADD COLUMN family_name VARCHAR(100) DEFAULT ''"),
        ("given_name", "ALTER TABLE users ADD COLUMN given_name VARCHAR(100) DEFAULT ''"),
        ("gender", "ALTER TABLE users ADD COLUMN gender VARCHAR(30) DEFAULT ''"),
        ("nationality", "ALTER TABLE users ADD COLUMN nationality VARCHAR(100) DEFAULT ''"),
        ("passport_expiry", "ALTER TABLE users ADD COLUMN passport_expiry DATE NULL"),
        ("birthday", "ALTER TABLE users ADD COLUMN birthday DATE NULL"),
        ("official_photo_synced_at", "ALTER TABLE users ADD COLUMN official_photo_synced_at DATETIME NULL"),
        ("remark", "ALTER TABLE users ADD COLUMN remark TEXT"),
        ("source", "ALTER TABLE users ADD COLUMN source VARCHAR(50) DEFAULT 'self_register'"),
        ("imported_at", "ALTER TABLE users ADD COLUMN imported_at DATETIME NULL"),
    ]
    altered = False
    for column_name, sql_statement in schema_changes:
        if column_name not in columns:
            db.execute(text(sql_statement))
            current_columns.add(column_name)
            altered = True
    if altered:
        db.commit()

    if "status" in current_columns:
        db.execute(text("UPDATE users SET status='active' WHERE status IS NULL OR status=''"))
        db.execute(text("ALTER TABLE users MODIFY COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"))

    if "real_name" in current_columns:
        if "username" in current_columns:
            db.execute(text("UPDATE users SET real_name=username WHERE real_name IS NULL OR real_name=''"))
    if "source" in current_columns:
        db.execute(text("UPDATE users SET source='self_register' WHERE source IS NULL OR source=''"))

    if "passport_no" in current_columns and "candidate_no" in current_columns:
        db.execute(text("UPDATE users SET passport_no=candidate_no WHERE (passport_no IS NULL OR passport_no='') AND candidate_no IS NOT NULL AND candidate_no<>''"))

    if "face_image_oss_key" in current_columns and "identity_doc_oss_key" in current_columns:
        db.execute(
            text(
                "UPDATE users SET face_image_oss_key=identity_doc_oss_key "
                "WHERE (face_image_oss_key IS NULL OR face_image_oss_key='') "
                "AND identity_doc_oss_key IS NOT NULL AND identity_doc_oss_key<>''"
            )
        )
    if "face_enrolled_at" in current_columns and "identity_doc_uploaded_at" in current_columns:
        db.execute(
            text(
                "UPDATE users SET face_enrolled_at=identity_doc_uploaded_at "
                "WHERE face_enrolled_at IS NULL AND identity_doc_uploaded_at IS NOT NULL"
            )
        )

    if "passport_no" in current_columns and not _has_unique_index(db, "users", "passport_no"):
        if _has_duplicate_values(db, "users", "passport_no"):
            raise RuntimeError("Duplicate users.passport_no values prevent unique passport records")
        db.execute(text("ALTER TABLE users ADD UNIQUE INDEX uq_users_passport_no (passport_no)"))

    if "xidian_application_no" in current_columns and not _has_unique_index(db, "users", "xidian_application_no"):
        if _has_duplicate_values(db, "users", "xidian_application_no"):
            raise RuntimeError("Duplicate users.xidian_application_no values prevent unique application records")
        db.execute(text("ALTER TABLE users ADD UNIQUE INDEX uq_users_xidian_application_no (xidian_application_no)"))

    obsolete_columns = [
        "account",
        "username",
        "candidate_no",
        "identity_doc_oss_key",
        "identity_doc_uploaded_at",
        "identity_doc_type",
        "identity_doc_consent_at",
        "face_consent_at",
        "face_consent_version",
    ]
    for column_name in obsolete_columns:
        if column_name in _get_column_names(db, "users"):
            _drop_indexes_for_column(db, "users", column_name)
            db.execute(text(f"ALTER TABLE users DROP COLUMN {column_name}"))

    db.commit()


def ensure_proctoring_event_schema(db):
    db.execute(
        text(
            "CREATE TABLE IF NOT EXISTS proctoring_events ("
            "id INT PRIMARY KEY AUTO_INCREMENT,"
            "session_id VARCHAR(50) NOT NULL,"
            "user_email VARCHAR(100) NOT NULL,"
            "event_type VARCHAR(80) NOT NULL,"
            "risk_level VARCHAR(50) DEFAULT 'low',"
            "image_oss_key VARCHAR(255) DEFAULT '',"
            "raw_result_json TEXT,"
            "client_captured_at DATETIME NULL,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_proctoring_events_session_id (session_id),"
            "INDEX idx_proctoring_events_user_email (user_email),"
            "INDEX idx_proctoring_events_event_type (event_type)"
            ")"
        )
    )
    db.commit()


def _get_column_names(db, table_name):
    columns = db.execute(text(f"SHOW COLUMNS FROM {table_name}")).mappings().all()
    return {item["Field"] for item in columns}


def _get_index_rows(db, table_name):
    return db.execute(text(f"SHOW INDEX FROM {table_name}")).mappings().all()


def _has_unique_index(db, table_name, column_name):
    for item in _get_index_rows(db, table_name):
        if item["Column_name"] == column_name and int(item["Non_unique"]) == 0:
            return True
    return False


def _has_duplicate_values(db, table_name, column_name):
    duplicate_row = db.execute(
        text(
            f"SELECT {column_name} FROM {table_name} "
            f"WHERE {column_name} IS NOT NULL AND {column_name} <> '' "
            f"GROUP BY {column_name} HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).fetchone()
    return duplicate_row is not None


def _drop_indexes_for_column(db, table_name, column_name):
    index_names = {
        item["Key_name"]
        for item in _get_index_rows(db, table_name)
        if item["Column_name"] == column_name and item["Key_name"] != "PRIMARY"
    }
    for index_name in index_names:
        db.execute(text(f"ALTER TABLE {table_name} DROP INDEX {index_name}"))


def _seed_admin_defaults(admin_user, status="active"):
    if not getattr(admin_user, "status", None):
        admin_user.status = status
    if not getattr(admin_user, "display_name", None):
        admin_user.display_name = getattr(admin_user, "username", "") or ""
    if not hasattr(admin_user, "email"):
        admin_user.email = None
    if not hasattr(admin_user, "last_login_at"):
        admin_user.last_login_at = None
    if not hasattr(admin_user, "created_by"):
        admin_user.created_by = None


def ensure_admin_user_schema(db):
    columns = _get_column_names(db, "admin_users")
    current_columns = set(columns)
    altered = False

    schema_changes = [
        ("status", "ALTER TABLE admin_users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"),
        ("display_name", "ALTER TABLE admin_users ADD COLUMN display_name VARCHAR(50) DEFAULT ''"),
        ("email", "ALTER TABLE admin_users ADD COLUMN email VARCHAR(100) NULL"),
        ("last_login_at", "ALTER TABLE admin_users ADD COLUMN last_login_at DATETIME NULL"),
        ("created_by", "ALTER TABLE admin_users ADD COLUMN created_by INT NULL"),
    ]

    for column_name, sql_statement in schema_changes:
        if column_name not in columns:
            db.execute(text(sql_statement))
            current_columns.add(column_name)
            altered = True

    if altered:
        db.commit()

    if "status" in current_columns:
        db.execute(text("UPDATE admin_users SET status='active' WHERE status IS NULL OR status=''"))
        db.execute(text("ALTER TABLE admin_users MODIFY COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"))

    if "display_name" in current_columns:
        db.execute(
            text(
                "UPDATE admin_users SET display_name = username "
                "WHERE display_name IS NULL OR display_name = ''"
            )
        )

    if "email" in current_columns and not _has_unique_index(db, "admin_users", "email"):
        if _has_duplicate_values(db, "admin_users", "email"):
            raise RuntimeError(
                "Duplicate admin_users.email values prevent the uniqueness guarantee required for admin user management"
            )
        db.execute(text("ALTER TABLE admin_users ADD UNIQUE INDEX uq_admin_users_email (email)"))

    db.commit()


def ensure_admin_action_log_schema(db):
    columns = _get_column_names(db, "admin_action_logs")
    current_columns = set(columns)
    altered = False

    schema_changes = [
        ("admin_id", "ALTER TABLE admin_action_logs ADD COLUMN admin_id INT NULL"),
        ("username_snapshot", "ALTER TABLE admin_action_logs ADD COLUMN username_snapshot VARCHAR(50) DEFAULT ''"),
        ("action", "ALTER TABLE admin_action_logs ADD COLUMN action VARCHAR(50) NULL DEFAULT 'legacy_action'"),
        ("target_admin_id", "ALTER TABLE admin_action_logs ADD COLUMN target_admin_id INT NULL"),
        ("target_username", "ALTER TABLE admin_action_logs ADD COLUMN target_username VARCHAR(50) DEFAULT ''"),
        ("result", "ALTER TABLE admin_action_logs ADD COLUMN result VARCHAR(20) DEFAULT 'success'"),
        ("detail", "ALTER TABLE admin_action_logs ADD COLUMN detail TEXT"),
        ("created_at", "ALTER TABLE admin_action_logs ADD COLUMN created_at DATETIME NULL"),
    ]

    for column_name, sql_statement in schema_changes:
        if column_name not in columns:
            db.execute(text(sql_statement))
            current_columns.add(column_name)
            altered = True

    if altered:
        db.commit()

    if "action" in current_columns:
        db.execute(text("UPDATE admin_action_logs SET action='legacy_action' WHERE action IS NULL OR action=''"))
        db.execute(text("ALTER TABLE admin_action_logs MODIFY COLUMN action VARCHAR(50) NOT NULL DEFAULT 'legacy_action'"))

    db.commit()


DEFAULT_MYSQL_URL = "mysql+pymysql://ai_interview:AiInterview_DB_2026!@127.0.0.1:3306/interview_db?charset=utf8mb4"


def get_mysql_url() -> str:
    mysql_url = os.getenv("MYSQL_URL") or MYSQL_URL_ENV
    if mysql_url:
        return mysql_url
    if APP_ENV == "production":
        raise RuntimeError("MYSQL_URL is required when APP_ENV=production")
    return DEFAULT_MYSQL_URL


MYSQL_URL = get_mysql_url()

engine = create_engine(
    MYSQL_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
)
SessionLocal = sessionmaker(bind=engine)


def _legacy_auto_migrate_init_db():
    """初始化数据库表结构，并确保超级管理员账号存在。"""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        ensure_interview_record_schema(db)
        ensure_user_face_schema(db)
        ensure_proctoring_event_schema(db)
        ensure_admin_user_schema(db)
        ensure_admin_action_log_schema(db)

        super_admin_username = os.getenv("SUPER_ADMIN_USERNAME") or "super_admin"
        super_admin_password = os.getenv("SUPER_ADMIN_PASSWORD") or "super_admin123"

        super_admins = db.query(AdminUser).filter_by(role="super_admin").order_by(AdminUser.id.asc()).all()
        if not super_admins:
            existing_super_admin = db.query(AdminUser).filter_by(username=super_admin_username).first()
            if existing_super_admin:
                existing_super_admin.role = "super_admin"
                if not getattr(existing_super_admin, "password", None):
                    existing_super_admin.password = hash_admin_password(super_admin_password)
                _seed_admin_defaults(existing_super_admin)
            else:
                new_super_admin = AdminUser(
                    username=super_admin_username,
                    password=hash_admin_password(super_admin_password),
                    role="super_admin",
                    status="active",
                    display_name=super_admin_username,
                    email=None,
                    last_login_at=None,
                    created_by=None,
                )
                db.add(new_super_admin)
        elif len(super_admins) > 1:
            keeper = next((u for u in super_admins if u.username == super_admin_username), super_admins[0])
            keeper.role = "super_admin"
            _seed_admin_defaults(keeper)
            for super_user in super_admins:
                if super_user.id != keeper.id:
                    super_user.role = "admin"
                    _seed_admin_defaults(super_user)
        else:
            _seed_admin_defaults(super_admins[0])

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"数据库初始化失败: {e}")
        raise
    finally:
        db.close()


def check_database_connection() -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def verify_schema_ready() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {table.name for table in Base.metadata.sorted_tables}
    missing_tables = sorted(required_tables - existing_tables)
    if missing_tables:
        raise RuntimeError(
            "Database schema is not initialized. Missing tables: "
            + ", ".join(missing_tables)
            + ". Run `python tools/migrate_db.py` before starting API instances."
        )

    missing_columns = []
    for table in Base.metadata.sorted_tables:
        existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
        required_columns = {column.name for column in table.columns}
        for column_name in sorted(required_columns - existing_columns):
            missing_columns.append(f"{table.name}.{column_name}")

    if missing_columns:
        preview = ", ".join(missing_columns[:20])
        suffix = "" if len(missing_columns) <= 20 else f", ... (+{len(missing_columns) - 20} more)"
        raise RuntimeError(
            "Database schema is not up to date. Missing columns: "
            + preview
            + suffix
            + ". Run `python tools/migrate_db.py` before starting API instances."
        )


def ensure_super_admin(db) -> None:
    super_admin_username = os.getenv("SUPER_ADMIN_USERNAME") or SUPER_ADMIN_USERNAME or "super_admin"
    super_admin_password = os.getenv("SUPER_ADMIN_PASSWORD") or SUPER_ADMIN_PASSWORD or "super_admin123"

    super_admins = db.query(AdminUser).filter_by(role="super_admin").order_by(AdminUser.id.asc()).all()
    if not super_admins:
        existing_super_admin = db.query(AdminUser).filter_by(username=super_admin_username).first()
        if existing_super_admin:
            existing_super_admin.role = "super_admin"
            if not getattr(existing_super_admin, "password", None):
                existing_super_admin.password = hash_admin_password(super_admin_password)
            _seed_admin_defaults(existing_super_admin)
        else:
            db.add(
                AdminUser(
                    username=super_admin_username,
                    password=hash_admin_password(super_admin_password),
                    role="super_admin",
                    status="active",
                    display_name=super_admin_username,
                    email=None,
                    last_login_at=None,
                    created_by=None,
                )
            )
    elif len(super_admins) > 1:
        keeper = next((u for u in super_admins if u.username == super_admin_username), super_admins[0])
        keeper.role = "super_admin"
        _seed_admin_defaults(keeper)
        for super_user in super_admins:
            if super_user.id != keeper.id:
                super_user.role = "admin"
                _seed_admin_defaults(super_user)
    else:
        _seed_admin_defaults(super_admins[0])

    db.commit()


def verify_super_admin_exists() -> None:
    db = SessionLocal()
    try:
        exists = (
            db.query(AdminUser.id)
            .filter(AdminUser.role == "super_admin", AdminUser.status == "active")
            .first()
            is not None
        )
        if not exists:
            raise RuntimeError("No active super_admin exists. Run `python tools/migrate_db.py` to seed it.")
    finally:
        db.close()


def migrate_db(seed_super_admin: bool = True) -> None:
    """Create or upgrade tables. Run this once during deployment, not from every API instance."""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        ensure_interview_record_schema(db)
        ensure_user_face_schema(db)
        ensure_proctoring_event_schema(db)
        ensure_admin_user_schema(db)
        ensure_admin_action_log_schema(db)
        if seed_super_admin:
            ensure_super_admin(db)
    except Exception as e:
        db.rollback()
        print(f"Database migration failed: {e}")
        raise
    finally:
        db.close()


def init_db(run_migrations: Optional[bool] = None) -> None:
    """Prepare database access for app startup."""
    should_migrate = DB_AUTO_MIGRATE_ON_STARTUP if run_migrations is None else run_migrations
    if should_migrate:
        migrate_db(seed_super_admin=True)
        return

    try:
        check_database_connection()
        verify_schema_ready()
        verify_super_admin_exists()
    except Exception as e:
        print(f"Database readiness check failed: {e}")
        raise


def database_ready() -> bool:
    try:
        check_database_connection()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    migrate_db(seed_super_admin=True)
