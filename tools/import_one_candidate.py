"""Deprecated single-candidate importer.

The current production flow imports candidates from 信息.xlsx via
tools/import_candidates.py. Login account is email, and the initial password is
the last 6 characters of the passport number.
"""


if __name__ == "__main__":
    raise SystemExit(
        "tools/import_one_candidate.py is deprecated. "
        "Use: python -X utf8 tools/import_candidates.py --report tmp/info_xlsx_import_report.json"
    )
