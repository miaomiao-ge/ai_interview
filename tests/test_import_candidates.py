import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.import_candidates import password_from_passport


def test_password_from_passport_uses_last_six_characters():
    assert password_from_passport("AB1234567") == "234567"


def test_password_from_passport_rejects_values_shorter_than_six_characters():
    with pytest.raises(ValueError, match="不足 6 位"):
        password_from_passport("A1234")
