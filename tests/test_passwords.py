import hashlib

from core.passwords import hash_password, is_legacy_hash, verify_password


def test_legacy_sha256_is_accepted():
    stored = hashlib.sha256(b"pass123").hexdigest()
    assert is_legacy_hash(stored)
    assert verify_password("pass123", stored)
    assert not verify_password("wrong", stored)


def test_bcrypt_hash_roundtrip():
    stored = hash_password("pass123")
    assert stored.startswith("$2")
    assert not is_legacy_hash(stored)
    assert verify_password("pass123", stored)
    assert not verify_password("wrong", stored)


def test_empty_values_are_rejected():
    assert not verify_password("", "x")
    assert not verify_password("x", "")
