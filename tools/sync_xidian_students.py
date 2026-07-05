import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import SessionLocal, init_db
from core.xidian_student_sync import sync_students


def parse_args():
    parser = argparse.ArgumentParser(description="同步西电国际学生申请数据到 users 表")
    parser.add_argument("--year", type=int, default=2026, help="申请年度，不能早于 2026")
    parser.add_argument("--application-nos", default="", help="可选，英文逗号分隔的申请编号")
    parser.add_argument("--limit", type=int, default=None, help="最多同步多少条数据")
    parser.add_argument("--skip-photo", action="store_true", help="只同步基础字段，不上传照片到 OSS")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    application_nos = [item.strip() for item in args.application_nos.split(",") if item.strip()] or None
    init_db()
    lock_db = SessionLocal()
    lock_name = "xidian_student_sync"
    try:
        acquired = lock_db.execute(
            text("SELECT GET_LOCK(:lock_name, 0)"), {"lock_name": lock_name}
        ).scalar()
        if acquired != 1:
            print(json.dumps({"status": "skipped", "message": "同步任务已在运行"}, ensure_ascii=False))
            return 2

        result = sync_students(
            args.year,
            application_nos,
            upload_photo=not args.skip_photo,
            limit=args.limit,
        )
        # Do not print application numbers, emails, passport data, or photo paths.
        print(
            json.dumps(
                {"status": "completed", "year": result["year"], "stats": result["stats"]},
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
