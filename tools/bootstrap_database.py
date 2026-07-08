import argparse
import json
import os
import re
import secrets
import string
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class BootstrapConfig:
    admin_url: str
    mysql_url: str
    database: str
    app_user: str
    app_password: str
    app_host: str
    charset: str
    collation: str


@dataclass
class BootstrapResult:
    database: str
    app_user: str
    app_host: str
    created_or_verified: bool
    mysql_url_ready: bool


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def generate_password(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^*-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def build_mysql_url(user: str, password: str, host: str, port: str, database: str) -> str:
    return (
        f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{database}?charset=utf8mb4"
    )


def get_config() -> BootstrapConfig:
    mysql_url = env("MYSQL_URL")
    url_database = ""
    url_user = ""
    url_password = ""
    url_host = ""
    url_port = ""
    if mysql_url:
        parsed_url = make_url(mysql_url)
        url_database = (parsed_url.database or "").strip()
        url_user = (parsed_url.username or "").strip()
        url_password = (parsed_url.password or "").strip()
        url_host = (parsed_url.host or "").strip()
        url_port = str(parsed_url.port or "").strip()

    database = env("MYSQL_DATABASE") or url_database or "interview_db"
    app_user = env("MYSQL_APP_USER") or url_user or "ai_interview"
    app_password = env("MYSQL_APP_PASSWORD") or url_password
    app_host = env("MYSQL_APP_HOST", "%")
    mysql_host = env("MYSQL_HOST") or url_host or "127.0.0.1"
    mysql_port = env("MYSQL_PORT") or url_port or "3306"
    admin_url = env("MYSQL_ADMIN_URL")

    if not admin_url:
        admin_user = env("MYSQL_ADMIN_USER", "root")
        admin_password = env("MYSQL_ADMIN_PASSWORD")
        if not admin_password:
            raise RuntimeError("MYSQL_ADMIN_URL or MYSQL_ADMIN_PASSWORD is required for database bootstrap")
        admin_url = build_mysql_url(admin_user, admin_password, mysql_host, mysql_port, "mysql")

    if not app_password:
        app_password = generate_password()

    if not mysql_url:
        mysql_url = build_mysql_url(app_user, app_password, mysql_host, mysql_port, database)

    return BootstrapConfig(
        admin_url=admin_url,
        mysql_url=mysql_url,
        database=database,
        app_user=app_user,
        app_password=app_password,
        app_host=app_host,
        charset=env("MYSQL_CHARSET", "utf8mb4"),
        collation=env("MYSQL_COLLATION", "utf8mb4_unicode_ci"),
    )


def quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("Invalid MySQL identifier")
    return "`" + value.replace("`", "``") + "`"


def quote_string(value: str) -> str:
    if "\x00" in value:
        raise ValueError("Invalid MySQL string value")
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def validate_mysql_name(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", value):
        raise ValueError(f"{label} may only contain letters, numbers, and underscores")
    return value


def create_admin_engine(admin_url: str):
    return create_engine(admin_url, pool_pre_ping=True)


def create_app_engine(mysql_url: str):
    return create_engine(mysql_url, pool_pre_ping=True)


def bootstrap_database(config: BootstrapConfig) -> BootstrapResult:
    admin_engine = create_admin_engine(config.admin_url)
    database_name = quote_identifier(validate_mysql_name(config.database, "MYSQL_DATABASE"))
    charset = validate_mysql_name(config.charset, "MYSQL_CHARSET")
    collation = validate_mysql_name(config.collation, "MYSQL_COLLATION")
    account = f"{quote_string(config.app_user)}@{quote_string(config.app_host)}"
    with admin_engine.begin() as connection:
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS {database_name} "
                f"CHARACTER SET {charset} COLLATE {collation}"
            )
        )
        connection.execute(
            text(f"CREATE USER IF NOT EXISTS {account} IDENTIFIED BY {quote_string(config.app_password)}")
        )
        connection.execute(
            text(f"GRANT ALL PRIVILEGES ON {database_name}.* TO {account}")
        )

    app_engine = create_app_engine(config.mysql_url)
    with app_engine.connect() as connection:
        connection.execute(text("SELECT 1"))

    return BootstrapResult(
        database=config.database,
        app_user=config.app_user,
        app_host=config.app_host,
        created_or_verified=True,
        mysql_url_ready=True,
    )


def append_env_values(path: Path, values: dict[str, str]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    existing_keys = {
        line.split("=", 1)[0].strip()
        for line in existing.splitlines()
        if line.strip() and not line.lstrip().startswith("#") and "=" in line
    }
    lines = []
    if existing and not existing.endswith("\n"):
        lines.append("")
    for key, value in values.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}")
    if not lines:
        return
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(description="Create MySQL database and app user for AI Interview.")
    parser.add_argument("--write-env", action="store_true", help="Append generated MYSQL_URL/MYSQL_APP_PASSWORD to .env when missing.")
    parser.add_argument("--check-only", action="store_true", help="Only verify MYSQL_URL can connect.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = get_config()

    if args.write_env:
        append_env_values(
            PROJECT_ROOT / ".env",
            {
                "MYSQL_APP_PASSWORD": config.app_password,
                "MYSQL_URL": config.mysql_url,
            },
        )

    if args.check_only:
        with create_app_engine(config.mysql_url).connect() as connection:
            connection.execute(text("SELECT 1"))
        payload = {"status": "ok", "mysql_url_ready": True}
    else:
        result = bootstrap_database(config)
        payload = {"status": "completed", **asdict(result)}

    print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
