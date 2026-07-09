import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.import_candidates import password_from_passport


def test_password_from_passport_uses_uppercase_passport_plus_2026():
    assert password_from_passport(" ab1234567 ") == "AB12345672026"


def test_password_from_passport_rejects_empty_passport_number():
    with pytest.raises(ValueError, match="为空"):
        password_from_passport(" ")
