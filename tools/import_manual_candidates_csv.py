import argparse
import csv
import json
import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.import_manual_candidate import upsert_manual_candidate


DEFAULT_CSV_FILE = PROJECT_ROOT / "data" / "manual_candidates.csv"


FIELD_DEFAULTS = {
    "name": "",
    "passport_no": "",
    "email": "",
    "photo": "",
    "password": "",
    "application_no": "",
    "application_id": "",
    "family_name": "",
    "given_name": "",
    "gender": "",
    "nationality": "",
    "passport_expiry": "",
    "birthday": "",
    "recommend_flag": "",
    "application_status": "",
    "status": "active",
    "remark": "",
    "source": "manual_csv_import",
}


def clean_row(row: dict) -> dict:
    cleaned = {}
    for key, default in FIELD_DEFAULTS.items():
        cleaned[key] = (row.get(key) or default).strip()
    return cleaned


def row_to_args(row: dict, dry_run: bool) -> SimpleNamespace:
    cleaned = clean_row(row)
    return SimpleNamespace(**cleaned, dry_run=dry_run, report="")


def import_csv(csv_file: Path, dry_run: bool, stop_on_error: bool) -> dict:
    if not csv_file.is_file():
        raise FileNotFoundError(str(csv_file))

    report = {
        "file": str(csv_file),
        "dry_run": dry_run,
        "total": 0,
        "created": 0,
        "updated": 0,
        "validated": 0,
        "failed": 0,
        "results": [],
        "errors": [],
    }

    with csv_file.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for index, row in enumerate(reader, start=2):
            report["total"] += 1
            try:
                result = upsert_manual_candidate(row_to_args(row, dry_run))
                result["row"] = index
                report["results"].append(result)
                action = result.get("action")
                if action == "created":
                    report["created"] += 1
                elif action == "updated":
                    report["updated"] += 1
                elif action == "validated":
                    report["validated"] += 1
            except Exception as exc:
                report["failed"] += 1
                report["errors"].append({"row": index, "error": str(exc)})
                if stop_on_error:
                    break

    return report


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import one or more manual candidates from CSV into users."
    )
    parser.add_argument("--file", default=str(DEFAULT_CSV_FILE), help="CSV file path.")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write DB or OSS.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop after first failed row.")
    parser.add_argument("--report", default="", help="Optional JSON report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = import_csv(Path(args.file).expanduser().resolve(), args.dry_run, args.stop_on_error)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
