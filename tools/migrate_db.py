import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.database import migrate_db, verify_schema_ready  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run production database migrations for AI Interview.")
    parser.add_argument("--check-only", action="store_true", help="Only verify that the schema is ready.")
    parser.add_argument("--no-seed-super-admin", action="store_true", help="Do not create or normalize super_admin.")
    args = parser.parse_args()

    if args.check_only:
        verify_schema_ready()
        print("database_schema=ready", flush=True)
        return

    migrate_db(seed_super_admin=not args.no_seed_super_admin)
    print("database_migration=ok", flush=True)


if __name__ == "__main__":
    main()
