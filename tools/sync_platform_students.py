import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import (
    PLATFORM_ACCOUNT_SOURCES,
    PLATFORM_ACCOUNT_SYNC_ENABLED,
)
from core.database import SessionLocal, init_db
from core.platform_account_sync import sync_platform_students


def parse_args():
    parser = argparse.ArgumentParser(description="同步外事留学平台学生账号到 users 表")
    parser.add_argument("--limit", type=int, default=None, help="最多同步多少条数据")
    parser.add_argument("--dry-run", action="store_true", help="只统计将发生的变更，不写数据库")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.dry_run and not PLATFORM_ACCOUNT_SYNC_ENABLED:
        print(json.dumps({"status": "disabled", "message": "PLATFORM_ACCOUNT_SYNC_ENABLED=0"}, ensure_ascii=False))
        return 0
    if not PLATFORM_ACCOUNT_SOURCES:
        print(json.dumps({"status": "not_configured"}, ensure_ascii=False))
        return 2

    init_db()
    lock_db = SessionLocal()
    lock_name = "platform_student_sync"
    try:
        acquired = lock_db.execute(
            text("SELECT GET_LOCK(:lock_name, 0)"), {"lock_name": lock_name}
        ).scalar()
        if acquired != 1:
            print(json.dumps({"status": "skipped", "message": "同步任务已在运行"}, ensure_ascii=False))
            return 2

        result = sync_platform_students(limit=args.limit, dry_run=args.dry_run)
        print(
            json.dumps(
                {
                    "status": "completed",
                    "dry_run": result["dry_run"],
                    "stats": result["stats"],
                    "errors": result["errors"][:20],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if result["stats"]["failed"] else 0
    finally:
        try:
            lock_db.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
        finally:
            lock_db.close()


if __name__ == "__main__":
    raise SystemExit(main())
