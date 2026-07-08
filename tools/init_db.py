import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from tools.bootstrap_database import (  # noqa: E402
    append_env_values,
    build_mysql_url,
    generate_password,
    quote_identifier,
    quote_string,
    validate_mysql_name,
)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_project_env(override: bool = False) -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=override)


def resolve_mysql_url(write_env: bool = False) -> str:
    mysql_url = env("MYSQL_URL")
    if mysql_url:
        return mysql_url

    app_user = env("MYSQL_APP_USER", "ai_interview")
    app_password = env("MYSQL_APP_PASSWORD")
    if not app_password:
        if write_env:
            app_password = generate_password()
            os.environ["MYSQL_APP_PASSWORD"] = app_password
        else:
            raise RuntimeError(
                "MYSQL_URL or MYSQL_APP_PASSWORD is required. For a fresh server, set "
                "MYSQL_ADMIN_URL plus MYSQL_APP_USER/MYSQL_APP_PASSWORD, or run with "
                "--write-env to generate MYSQL_APP_PASSWORD and MYSQL_URL."
            )
    if not app_user:
        raise RuntimeError(
            "MYSQL_URL is required. Or set MYSQL_APP_USER and MYSQL_APP_PASSWORD "
            "so the script can build MYSQL_URL."
        )

    database = env("MYSQL_DATABASE", "interview_db")
    host = env("MYSQL_HOST", "127.0.0.1")
    port = env("MYSQL_PORT", "3306")
    mysql_url = build_mysql_url(app_user, app_password, host, port, database)
    os.environ["MYSQL_URL"] = mysql_url
    if write_env:
        append_env_values(
            PROJECT_ROOT / ".env",
            {
                "MYSQL_DATABASE": database,
                "MYSQL_APP_USER": app_user,
                "MYSQL_APP_PASSWORD": app_password,
                "MYSQL_URL": mysql_url,
            },
        )
    return mysql_url


def resolve_database_name(mysql_url: str) -> str:
    parsed_url = make_url(mysql_url)
    return (parsed_url.database or "").strip() or env("MYSQL_DATABASE") or "interview_db"


def resolve_admin_url(mysql_url: str) -> str:
    admin_url = env("MYSQL_ADMIN_URL")
    if admin_url:
        return admin_url

    parsed_url = make_url(mysql_url)
    host = env("MYSQL_HOST") or parsed_url.host or "127.0.0.1"
    port = env("MYSQL_PORT") or str(parsed_url.port or 3306)

    admin_password = env("MYSQL_ADMIN_PASSWORD")
    if admin_password:
        admin_user = env("MYSQL_ADMIN_USER", "root")
        return build_mysql_url(admin_user, admin_password, host, port, "mysql")

    if parsed_url.username and parsed_url.password:
        return parsed_url.set(database="mysql").render_as_string(hide_password=False)

    raise RuntimeError(
        "Cannot build a MySQL admin connection. Set MYSQL_ADMIN_URL or MYSQL_ADMIN_PASSWORD."
    )


def resolve_app_account(mysql_url: str) -> tuple[str, str, str]:
    parsed_url = make_url(mysql_url)
    app_user = env("MYSQL_APP_USER") or (parsed_url.username or "").strip()
    app_password = env("MYSQL_APP_PASSWORD") or (parsed_url.password or "").strip()
    app_host = env("MYSQL_APP_HOST", "%")
    return app_user, app_password, app_host


def should_create_app_user(mysql_url: str) -> bool:
    app_user, app_password, _ = resolve_app_account(mysql_url)
    if not app_user or not app_password:
        return False
    if app_user.lower() in {"root", "mysql.sys", "mysql.session"}:
        return False
    return True


def app_user_skip_reason(mysql_url: str) -> str:
    app_user, app_password, _ = resolve_app_account(mysql_url)
    if not app_user or not app_password:
        return "app credentials are missing"
    if app_user.lower() in {"root", "mysql.sys", "mysql.session"}:
        return "MYSQL_URL uses a privileged/system account; configure MYSQL_APP_USER and MYSQL_APP_PASSWORD to create a dedicated app user"
    return "app user creation was not required"


def create_admin_engine(mysql_url: str):
    return create_engine(resolve_admin_url(mysql_url), pool_pre_ping=True)


def create_app_engine(mysql_url: str):
    return create_engine(mysql_url, pool_pre_ping=True)


def ensure_database_exists(mysql_url: str) -> dict[str, str]:
    database = resolve_database_name(mysql_url)
    charset = validate_mysql_name(env("MYSQL_CHARSET", "utf8mb4"), "MYSQL_CHARSET")
    collation = validate_mysql_name(env("MYSQL_COLLATION", "utf8mb4_unicode_ci"), "MYSQL_COLLATION")
    database_name = quote_identifier(validate_mysql_name(database, "MYSQL_DATABASE"))

    admin_engine = create_admin_engine(mysql_url)
    with admin_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS {database_name} "
                f"CHARACTER SET {charset} COLLATE {collation}"
            )
        )

    return {"database": database, "charset": charset, "collation": collation}


def ensure_app_user(mysql_url: str) -> dict[str, object]:
    app_user, app_password, app_host = resolve_app_account(mysql_url)
    if not app_user or not app_password:
        return {"status": "skipped", "reason": "MYSQL_APP_USER/MYSQL_APP_PASSWORD or MYSQL_URL credentials missing"}

    database = resolve_database_name(mysql_url)
    account = f"{quote_string(app_user)}@{quote_string(app_host)}"
    database_name = quote_identifier(validate_mysql_name(database, "MYSQL_DATABASE"))

    admin_engine = create_admin_engine(mysql_url)
    with admin_engine.begin() as connection:
        connection.execute(
            text(f"CREATE USER IF NOT EXISTS {account} IDENTIFIED BY {quote_string(app_password)}")
        )
        connection.execute(text(f"GRANT ALL PRIVILEGES ON {database_name}.* TO {account}"))

    return {"status": "completed", "user": app_user, "host": app_host}


def verify_mysql_url(mysql_url: str) -> None:
    app_engine = create_app_engine(mysql_url)
    with app_engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def run_migrations(seed_super_admin: bool) -> None:
    from core.database import migrate_db, verify_schema_ready

    migrate_db(seed_super_admin=seed_super_admin)
    verify_schema_ready()


def verify_schema() -> None:
    from core.database import verify_schema_ready

    verify_schema_ready()


def import_questions(path: Path) -> dict[str, object]:
    from tools.import_questions import load_database_api, read_questions_from_excel, upsert_questions

    load_database_api()
    rows = read_questions_from_excel(path)
    stats = upsert_questions(rows, dry_run=False)
    return {"file": str(path), "stats": asdict(stats)}


def sync_xidian_students(
    year: int,
    application_nos: list[str] | None,
    limit: int | None,
    upload_photo: bool,
) -> dict[str, object]:
    from core.database import SessionLocal
    from core.xidian_student_sync import sync_students

    lock_db = SessionLocal()
    lock_name = "xidian_student_sync"
    try:
        acquired = lock_db.execute(text("SELECT GET_LOCK(:lock_name, 0)"), {"lock_name": lock_name}).scalar()
        if acquired != 1:
            return {"status": "skipped", "reason": "student sync is already running"}

        result = sync_students(
            year,
            application_nos,
            upload_photo=upload_photo,
            limit=limit,
        )
        payload: dict[str, object] = {"status": "completed", "year": result["year"], "stats": result["stats"]}
        if result["stats"].get("failed"):
            payload["status"] = "failed"
            payload["failed_count"] = result["stats"]["failed"]
        return payload
    finally:
        try:
            lock_db.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
        finally:
            lock_db.close()


def parse_application_nos(value: str) -> list[str] | None:
    application_nos = [item.strip() for item in value.split(",") if item.strip()]
    return application_nos or None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Initialize the AI Interview MySQL database: create database, "
            "migrate schema, import questions, and sync Xidian student users."
        )
    )
    parser.add_argument("--check-only", action="store_true", help="Verify MySQL connection and schema without changes.")
    parser.add_argument("--skip-create-db", action="store_true", help="Skip CREATE DATABASE.")
    parser.add_argument("--skip-app-user", action="store_true", help="Skip CREATE USER and GRANT.")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip table creation and schema migrations.")
    parser.add_argument("--skip-questions", action="store_true", help="Skip importing questions.xlsx.")
    parser.add_argument("--skip-student-sync", action="store_true", help="Skip synchronizing Xidian student users.")
    parser.add_argument("--questions-file", default=str(PROJECT_ROOT / "questions.xlsx"), help="Path to questions.xlsx.")
    parser.add_argument("--year", type=int, default=2026, help="Xidian application year for student sync.")
    parser.add_argument("--application-nos", default="", help="Comma-separated Xidian application numbers to sync.")
    parser.add_argument("--student-limit", type=int, default=None, help="Limit the number of Xidian student records to sync.")
    parser.add_argument("--skip-photo", action="store_true", help="Do not upload official student photos to OSS during sync.")
    parser.add_argument("--no-seed-super-admin", action="store_true", help="Do not create or normalize super_admin.")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Append generated MYSQL_APP_PASSWORD and MYSQL_URL to .env when MYSQL_URL is missing.",
    )
    parser.add_argument(
        "--override-env",
        action="store_true",
        help="Let .env override existing process environment variables.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_project_env(override=args.override_env)

    mysql_url = resolve_mysql_url(write_env=args.write_env)

    if args.check_only:
        verify_mysql_url(mysql_url)
        verify_schema()
        payload = {"status": "ok", "mysql_url": "connectable", "schema": "ready"}
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        return 0

    database_result: dict[str, object] = {"status": "skipped"}
    if not args.skip_create_db:
        database_result = {"status": "completed", **ensure_database_exists(mysql_url)}

    if args.skip_app_user:
        app_user_result: dict[str, object] = {"status": "skipped", "reason": "--skip-app-user requested"}
    elif should_create_app_user(mysql_url):
        app_user_result = ensure_app_user(mysql_url)
    else:
        app_user_result = {"status": "skipped", "reason": app_user_skip_reason(mysql_url)}

    verify_mysql_url(mysql_url)

    schema_result: dict[str, object] = {"status": "skipped"}
    if not args.skip_migrations:
        run_migrations(seed_super_admin=not args.no_seed_super_admin)
        schema_result = {"status": "ready"}

    questions_result: dict[str, object] = {"status": "skipped"}
    questions_path = Path(args.questions_file).resolve()
    if not args.skip_questions:
        if questions_path.exists():
            questions_result = {"status": "completed", **import_questions(questions_path)}
        else:
            questions_result = {"status": "skipped", "reason": f"file not found: {questions_path}"}

    student_sync_result: dict[str, object] = {"status": "skipped"}
    if not args.skip_student_sync:
        student_sync_result = sync_xidian_students(
            args.year,
            parse_application_nos(args.application_nos),
            args.student_limit,
            upload_photo=not args.skip_photo,
        )
        if student_sync_result.get("status") == "failed":
            raise RuntimeError(f"Xidian student sync failed: {student_sync_result}")

    print(
        json.dumps(
            {
                "status": "completed",
                "database": database_result,
                "app_user": app_user_result,
                "schema": schema_result,
                "questions": questions_result,
                "student_sync": student_sync_result,
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
