"""Password hashing (PBKDF2) and signed session tokens (HMAC). Stdlib only."""
import base64
import hashlib
import hmac
import os
import secrets
import time

from . import db

_ITERATIONS = 200_000
_TOKEN_TTL = 60 * 60 * 24 * 30  # 30 days


def _secret():
    path = os.path.join(db.DATA_DIR, "secret.key")
    env = os.environ.get("CFSTUDIO_SECRET")
    if env:
        return env.encode()
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read().strip()
    os.makedirs(db.DATA_DIR, exist_ok=True)
    key = secrets.token_hex(32).encode()
    with open(path, "wb") as f:
        f.write(key)
    return key


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return "pbkdf2$%d$%s$%s" % (_ITERATIONS, salt.hex(), dk.hex())


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except (ValueError, AttributeError):
        return False


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: int) -> str:
    payload = "%d.%d" % (user_id, int(time.time()) + _TOKEN_TTL)
    sig = hmac.new(_secret(), payload.encode(), hashlib.sha256).digest()
    return "%s.%s" % (_b64e(payload.encode()), _b64e(sig))


def verify_token(token: str):
    """Return user_id or None."""
    try:
        payload_b64, sig_b64 = token.split(".")
        payload = _b64d(payload_b64)
        expect = hmac.new(_secret(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(expect, _b64d(sig_b64)):
            return None
        user_id, exp = payload.decode().split(".")
        if int(exp) < time.time():
            return None
        return int(user_id)
    except (ValueError, AttributeError):
        return None


def get_user_by_token(token: str):
    uid = verify_token(token or "")
    if uid is None:
        return None
    with db.connect() as con:
        row = con.execute("SELECT id, email, handle, created_at FROM users WHERE id=?", (uid,)).fetchone()
    return db.row_to_dict(row)
