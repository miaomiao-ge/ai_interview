"""Student password hashing shared with the platform account service.

bcrypt only considers the first 72 bytes of its input, so the password is
pre-hashed into a fixed-size base64 digest before hashing. Accounts synced from
the Xidian interface (and old snapshots) still hold a bare SHA-256 hex digest;
verify_password accepts those until the caller rewrites them on a later change.
"""
import base64
import hashlib
import hmac
import re

import bcrypt

_LEGACY_SHA256 = re.compile(r'^[0-9a-f]{64}$')


def _bcrypt_input(password: str) -> bytes:
    return base64.b64encode(hashlib.sha256(password.encode('utf-8')).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode('ascii')


def is_legacy_hash(stored: str) -> bool:
    return bool(stored) and bool(_LEGACY_SHA256.fullmatch(stored))


def verify_password(password: str, stored: str) -> bool:
    if not password or not stored:
        return False
    if is_legacy_hash(stored):
        return hmac.compare_digest(hashlib.sha256(password.encode('utf-8')).hexdigest(), stored)
    try:
        return bcrypt.checkpw(_bcrypt_input(password), stored.encode('ascii'))
    except (ValueError, UnicodeEncodeError):
        return False
