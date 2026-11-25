"""
File-based User Authentication Service
======================================
Loads credentials from a UTF-8 `.txt` file (`users.txt` at project root by default),
supports both plain-text and PBKDF2-SHA256 / SHA256 hashed secrets, and provides
session/client lockout helpers against brute-force login attempts.
"""

from __future__ import annotations

from collections import OrderedDict
import hashlib
import hmac
import os
import threading
import time
from pathlib import Path
from typing import Any

import user_logger

_ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_USERS_FILE = _ROOT_DIR / "users.txt"

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 30
_PBKDF2_DEFAULT_ITERATIONS = 260_000
_PBKDF2_MAX_ITERATIONS = 2_000_000
_DUMMY_PBKDF2_SALT = b"nova-dummy-salt!"

_SERVER_LOCKOUT_LOCK = threading.Lock()
_SERVER_LOCKOUT_MAX = 4096
_SERVER_LOCKOUT_STORE: OrderedDict[str, dict[str, Any]] = OrderedDict()


def hash_password(password: str, iterations: int = _PBKDF2_DEFAULT_ITERATIONS) -> str:
    """Hash a plain-text password using PBKDF2-HMAC-SHA256 for storage in users.txt."""
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${dk.hex()}"


def verify_password(plain_password: str, stored_secret: str) -> bool:
    """Verify a password against plain-text or hashed secret using constant-time comparison."""
    if not isinstance(plain_password, str) or not isinstance(stored_secret, str):
        return False
    if not plain_password or not stored_secret:
        return False

    if stored_secret.startswith("pbkdf2_sha256$"):
        parts = stored_secret.split("$")
        if len(parts) != 4:
            return False
        _, iter_str, salt_hex, expected_hex = parts
        try:
            iterations = int(iter_str)
            if iterations <= 0 or iterations > _PBKDF2_MAX_ITERATIONS:
                return False
            salt = bytes.fromhex(salt_hex)
            expected_bytes = bytes.fromhex(expected_hex)
        except ValueError:
            return False
        derived = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(derived, expected_bytes)

    if stored_secret.startswith("sha256$"):
        parts = stored_secret.split("$")
        if len(parts) == 2:
            digest = hashlib.sha256(plain_password.encode("utf-8")).hexdigest()
            return hmac.compare_digest(digest, parts[1].strip().lower())
        if len(parts) == 3:
            _, salt, expected_hex = parts
            digest = hashlib.sha256(f"{salt}{plain_password}".encode("utf-8")).hexdigest()
            return hmac.compare_digest(digest, expected_hex.strip().lower())
        return False

    return hmac.compare_digest(plain_password.encode("utf-8"), stored_secret.encode("utf-8"))


def format_logger_user_name(username: str, display_name: str = "") -> str:
    """Format logged identity as 'display_name (username)' or 'username'."""
    clean_u = user_logger._sanitize_username(username)
    clean_d = user_logger._sanitize_username(display_name)
    if clean_d and clean_d.lower() != clean_u.lower():
        return user_logger._sanitize_username(f"{clean_d} ({clean_u})")
    return clean_u


def _parse_users_lines(raw_text: str) -> dict[str, dict[str, str]]:
    """Parse `username:password` or `username:password:display_name` lines."""
    users: dict[str, dict[str, str]] = {}
    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = line.split(":", 2)
        if len(parts) < 2:
            continue
        username = parts[0].strip()
        password_secret = parts[1].rstrip("\r\n")
        display_name = parts[2].strip() if len(parts) >= 3 else ""
        if not username or not password_secret:
            continue
        users[username.lower()] = {
            "username": username,
            "password": password_secret,
            "display_name": display_name,
        }
    return users


def _load_users_from_streamlit_secrets() -> dict[str, dict[str, str]]:
    """
    Optional Streamlit Cloud fallback when `users.txt` is not present on disk.
    Supports either:
      1) `st.secrets["users_txt"]` (multiline string in the exact `users.txt` format)
      2) `st.secrets["users"]` TOML table: `username = "password"` or `username = "password:Display Name"`
         (or nested table `{ password = "...", display_name = "..." }`).
    """
    try:
        import streamlit as st

        secrets_obj = getattr(st, "secrets", None)
        if secrets_obj is None:
            return {}
        try:
            has_txt = "users_txt" in secrets_obj
            has_tbl = "users" in secrets_obj
        except Exception:
            return {}

        users: dict[str, dict[str, str]] = {}
        if has_txt:
            raw_txt = secrets_obj["users_txt"]
            if isinstance(raw_txt, str) and raw_txt.strip():
                users.update(_parse_users_lines(raw_txt))

        if has_tbl:
            tbl = secrets_obj["users"]
            if isinstance(tbl, str) and tbl.strip():
                users.update(_parse_users_lines(tbl))
            elif hasattr(tbl, "items"):
                for raw_u, raw_val in tbl.items():
                    username = str(raw_u or "").strip()
                    if not username:
                        continue
                    password_secret = ""
                    display_name = ""
                    if isinstance(raw_val, str):
                        # Support "pbkdf2_sha256$...:Display Name" or "plain:Display Name" or "plain"
                        if ":" in raw_val:
                            pw_part, disp_part = raw_val.split(":", 1)
                            password_secret = pw_part.strip()
                            display_name = disp_part.strip()
                        else:
                            password_secret = raw_val.strip()
                    elif hasattr(raw_val, "get"):
                        password_secret = str(raw_val.get("password", "") or "").strip()
                        display_name = str(raw_val.get("display_name", "") or "").strip()
                    if password_secret:
                        users[username.lower()] = {
                            "username": username,
                            "password": password_secret,
                            "display_name": display_name,
                        }
        return users
    except Exception:
        return {}


def load_users(users_file: str | os.PathLike[str] | None = None) -> tuple[dict[str, dict[str, str]], str | None]:
    """
    Parse users from a `.txt` file (`username:password` or `username:password:display_name`),
    falling back to `st.secrets["users"]` / `st.secrets["users_txt"]` when running on Streamlit Cloud
    without a committed `users.txt`.
    Returns `(users_by_lower_username, error_code)`.
    """
    path = Path(users_file) if users_file is not None else DEFAULT_USERS_FILE
    if not path.exists() or not path.is_file():
        if users_file is None:
            secret_users = _load_users_from_streamlit_secrets()
            if secret_users:
                return secret_users, None
        return {}, "missing_file"

    try:
        raw_text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}, "read_error"

    users = _parse_users_lines(raw_text)
    if not users:
        if users_file is None:
            secret_users = _load_users_from_streamlit_secrets()
            if secret_users:
                return secret_users, None
        return {}, "empty_users"
    return users, None


def authenticate_user(
    username: str,
    password: str,
    users_file: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Authenticate a username/password pair against the configured `.txt` user file."""
    clean_input_user = (username or "").strip()
    if not clean_input_user or not password:
        return {
            "ok": False,
            "reason": "empty_input",
            "username": user_logger._sanitize_username(clean_input_user),
            "display_name": "",
            "logger_user_name": "",
        }

    users, err_code = load_users(users_file=users_file)
    if err_code:
        return {
            "ok": False,
            "reason": err_code,
            "username": user_logger._sanitize_username(clean_input_user),
            "display_name": "",
            "logger_user_name": "",
        }

    record = users.get(clean_input_user.lower())
    if not record:
        # Match PBKDF2 work factor of stored users to prevent timing-based username enumeration
        dummy_iters = 0
        for rec in users.values():
            sec = rec.get("password", "")
            if isinstance(sec, str) and sec.startswith("pbkdf2_sha256$"):
                parts = sec.split("$")
                if len(parts) == 4:
                    try:
                        cand_it = int(parts[1])
                        if 0 < cand_it <= _PBKDF2_MAX_ITERATIONS:
                            dummy_iters = cand_it
                            break
                    except ValueError:
                        pass
        if dummy_iters > 0:
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _DUMMY_PBKDF2_SALT, dummy_iters)
            hmac.compare_digest(dk, b"\x00" * len(dk))
        else:
            hmac.compare_digest(password.encode("utf-8"), b"__nova_dummy_secret__")
        return {
            "ok": False,
            "reason": "invalid_credentials",
            "username": user_logger._sanitize_username(clean_input_user),
            "display_name": "",
            "logger_user_name": "",
        }

    if not verify_password(password, record["password"]):
        return {
            "ok": False,
            "reason": "invalid_credentials",
            "username": user_logger._sanitize_username(record["username"]),
            "display_name": user_logger._sanitize_username(record["display_name"]),
            "logger_user_name": format_logger_user_name(record["username"], record["display_name"]),
        }

    canonical_user = user_logger._sanitize_username(record["username"])
    display_name = user_logger._sanitize_username(record["display_name"])
    return {
        "ok": True,
        "reason": "ok",
        "username": canonical_user,
        "display_name": display_name,
        "logger_user_name": format_logger_user_name(canonical_user, display_name),
    }


def check_lockout(attempt_state: dict[str, Any] | None, now: float | None = None) -> int:
    """Return remaining lockout seconds (0 if login attempts are allowed)."""
    if not attempt_state:
        return 0
    cur_now = time.time() if now is None else float(now)
    locked_until = float(attempt_state.get("locked_until", 0.0) or 0.0)
    if locked_until > cur_now:
        return max(1, int(locked_until - cur_now + 0.999))
    return 0


def record_failed_attempt(
    attempt_state: dict[str, Any] | None,
    now: float | None = None,
    max_attempts: int = MAX_FAILED_ATTEMPTS,
    lockout_seconds: int = LOCKOUT_SECONDS,
) -> tuple[dict[str, Any], int]:
    """Increment failed login counter and apply temporary lockout when threshold is reached."""
    cur_now = time.time() if now is None else float(now)
    state = dict(attempt_state or {})
    if float(state.get("locked_until", 0.0) or 0.0) <= cur_now and state.get("locked_until"):
        state["locked_until"] = 0.0
        state["count"] = 0

    count = int(state.get("count", 0) or 0) + 1
    if count >= max_attempts:
        strikes = int(state.get("strikes", 0) or 0)
        eff_lockout = min(900, int(lockout_seconds) * (2 ** min(strikes, 5)))
        state["count"] = 0
        state["strikes"] = strikes + 1
        state["locked_until"] = cur_now + eff_lockout
        return state, eff_lockout

    state["count"] = count
    state["locked_until"] = 0.0
    return state, 0


def reset_attempts() -> dict[str, Any]:
    """Return a clean login attempt tracking state."""
    return {"count": 0, "locked_until": 0.0}


def is_admin_username(username: str | None) -> bool:
    """Return True when the authenticated login username is the admin account."""
    return str(username or "").strip().lower() == "admin"


def _make_server_lock_key(scope: str, key: str) -> str:
    clean_scope = str(scope or "login").strip().lower()[:32]
    clean_key = str(key or "unknown").strip().lower()[:160]
    return f"{clean_scope}:{clean_key}"


def check_server_lockout(scope: str, key: str, now: float | None = None) -> int:
    """Check server-wide lockout (survives browser F5 / new WebSocket sessions)."""
    lk = _make_server_lock_key(scope, key)
    cur_now = time.time() if now is None else float(now)
    with _SERVER_LOCKOUT_LOCK:
        state = _SERVER_LOCKOUT_STORE.get(lk)
        if not state:
            return 0
        rem = check_lockout(state, now=cur_now)
        if rem > 0:
            _SERVER_LOCKOUT_STORE.move_to_end(lk)
        return rem


def record_server_failed_attempt(
    scope: str,
    key: str,
    now: float | None = None,
    max_attempts: int = MAX_FAILED_ATTEMPTS,
    lockout_seconds: int = LOCKOUT_SECONDS,
) -> tuple[dict[str, Any], int]:
    """Increment server-wide failed login counter for (scope, key)."""
    lk = _make_server_lock_key(scope, key)
    cur_now = time.time() if now is None else float(now)
    with _SERVER_LOCKOUT_LOCK:
        prev_state = _SERVER_LOCKOUT_STORE.get(lk)
        new_state, locked_for = record_failed_attempt(
            prev_state,
            now=cur_now,
            max_attempts=max_attempts,
            lockout_seconds=lockout_seconds,
        )
        _SERVER_LOCKOUT_STORE[lk] = new_state
        _SERVER_LOCKOUT_STORE.move_to_end(lk)
        while len(_SERVER_LOCKOUT_STORE) > _SERVER_LOCKOUT_MAX:
            _SERVER_LOCKOUT_STORE.popitem(last=False)
        return dict(new_state), locked_for


def reset_server_attempts(scope: str, key: str) -> None:
    """Clear server-wide failed login state for (scope, key) after successful login."""
    lk = _make_server_lock_key(scope, key)
    with _SERVER_LOCKOUT_LOCK:
        _SERVER_LOCKOUT_STORE.pop(lk, None)


def clear_all_server_lockouts() -> None:
    """Clear all server-side lockout entries (intended for tests)."""
    with _SERVER_LOCKOUT_LOCK:
        _SERVER_LOCKOUT_STORE.clear()


def verify_admin_password(
    password: str,
    *,
    users_file: str | os.PathLike[str] | None = None,
    env_password: str | None = None,
    secret_password: str | None = None,
) -> dict[str, Any]:
    """
    Verify an admin unlock password against:
    1. Optional NOVA_ADMIN_PASSWORD env var / Streamlit ADMIN_PASSWORD secret override
    2. The `admin` account in `users.txt` (same credential as Welcome Login)

    Fails closed when neither an override nor an `admin` account in `users.txt` is configured
    (no predictable date-based fallback passwords).
    """
    candidate = str(password or "").strip()
    if not candidate:
        return {"ok": False, "reason": "empty_input", "source": ""}

    env_pw = (
        os.environ.get("NOVA_ADMIN_PASSWORD", "").strip()
        if env_password is None
        else str(env_password).strip()
    )
    sec_pw = str(secret_password or "").strip()

    configured_any = False
    if env_pw:
        configured_any = True
        if verify_password(candidate, env_pw):
            return {"ok": True, "reason": "ok", "source": "env"}

    if sec_pw:
        configured_any = True
        if verify_password(candidate, sec_pw):
            return {"ok": True, "reason": "ok", "source": "secret"}

    users, err_code = load_users(users_file=users_file)
    admin_rec = users.get("admin") if not err_code else None
    if admin_rec and admin_rec.get("password"):
        configured_any = True
        if verify_password(candidate, admin_rec["password"]):
            return {"ok": True, "reason": "ok", "source": "users_file"}

    if not configured_any:
        return {"ok": False, "reason": "unconfigured", "source": ""}
    return {"ok": False, "reason": "invalid_credentials", "source": ""}
