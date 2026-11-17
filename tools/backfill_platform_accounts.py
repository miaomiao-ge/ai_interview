"""Backfill users.platform_account for historical AI interview accounts.

Only fills empty platform_account values. It never changes passwords, status
or names; matching prefers platform_user_id and falls back to passport_no when
the passport maps to exactly one platform account across all configured sources.

Run on the AI interview host (it needs the AI MySQL database):

    python tools/backfill_platform_accounts.py --dry-run
    python tools/backfill_platform_accounts.py --apply
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import PLATFORM_ACCOUNT_SOURCES
from core.database import SessionLocal, User, init_db
from core.platform_account_client import PlatformAccountError, iter_students
from core.platform_account_sync import normalize_passport_no


def _text(record: dict, key: str, limit: int) -> str:
    value = record.get(key)
    return str(value).strip()[:limit] if value is not None else ""


def collect_mappings(limit: int | None = None):
    by_id: dict[str, set[str]] = {}
    by_passport: dict[str, set[str]] = {}
    for source in PLATFORM_ACCOUNT_SOURCES:
        for _, record in iter_students(limit=limit, source=source):
            account = _text(record, "account", 100)
            if not account:
                continue
            platform_id = record.get("id")
            if platform_id is not None:
                by_id.setdefault(str(platform_id), set()).add(account)
            passport = normalize_passport_no(record.get("passport_no"))
            if passport:
                by_passport.setdefault(passport, set()).add(account)
    return by_id, by_passport


def _single(values: set[str] | None) -> tuple[str | None, bool]:
    if not values:
        return None, False
    if len(values) == 1:
        return next(iter(values)), False
    return None, True


def plan_backfill(users, by_id, by_passport):
    updates = []
    stats = {
        "users_without_account": len(users),
        "matched_by_user_id": 0,
        "matched_by_passport": 0,
        "ambiguous_passport": 0,
        "unmatched": 0,
    }
    for user in users:
        account = None
        platform_id = getattr(user, "platform_user_id", None)
        if platform_id is not None:
            account, ambiguous = _single(by_id.get(str(platform_id)))
            if ambiguous:
                stats["unmatched"] += 1
                continue
        if account:
            stats["matched_by_user_id"] += 1
        else:
            passport = normalize_passport_no(getattr(user, "passport_no", None))
            if passport:
                account, ambiguous = _single(by_passport.get(passport))
                if ambiguous:
                    stats["ambiguous_passport"] += 1
                    continue
            if account:
                stats["matched_by_passport"] += 1
        if account:
            updates.append((user, account))
        else:
            stats["unmatched"] += 1
    return updates, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="回填历史 AI 面试账号的 platform_account")
    parser.add_argument("--apply", action="store_true", help="写入数据库；默认只统计")
    parser.add_argument("--limit", type=int, default=None, help="最多读取多少条平台账号")
    args = parser.parse_args()

    if not PLATFORM_ACCOUNT_SOURCES:
        print(json.dumps({"status": "not_configured"}, ensure_ascii=False))
        return 2

    init_db()
    try:
        by_id, by_passport = collect_mappings(limit=args.limit)
    except PlatformAccountError as exc:
        print(json.dumps({"status": "failed", "message": str(exc)}, ensure_ascii=False))
        return 2

    db = SessionLocal()
    try:
        users = (
            db.query(User)
            .filter(or_(User.platform_account.is_(None), User.platform_account == ""))
            .all()
        )
        updates, stats = plan_backfill(users, by_id, by_passport)
        if args.apply:
            now = datetime.utcnow()
            for user, account in updates:
                user.platform_account = account
                user.platform_synced_at = now
            db.commit()
        else:
            db.rollback()
        print(
            json.dumps(
                {
                    "status": "applied" if args.apply else "dry_run",
                    "would_update": len(updates),
                    "updated": len(updates) if args.apply else 0,
                    "stats": stats,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
