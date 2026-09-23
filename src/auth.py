from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
import time


def password_digest(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)


def account_action(database: Path, action: str, email: str, password: str, recovery: str = "") -> dict:
    email = email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 254:
        raise ValueError("Введите корректный email.")
    if len(password) > 256:
        raise ValueError("Пароль должен содержать не более 256 символов.")
    if action in ("register", "recover") and len(password) < 12:
        raise ValueError("Используйте пароль длиной от 12 символов.")
    if action not in ("register", "login", "recover"):
        raise ValueError("Неизвестное действие.")
    database.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    with sqlite3.connect(database, timeout=10) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, salt BLOB NOT NULL, digest BLOB NOT NULL, recovery BLOB NOT NULL, version INTEGER NOT NULL DEFAULT 1)")
        connection.execute("CREATE TABLE IF NOT EXISTS attempts (email TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL)")
        attempt = connection.execute("SELECT count, until FROM attempts WHERE email = ?", (email,)).fetchone()
        if attempt and attempt[0] >= 5 and attempt[1] > now:
            raise ValueError("Слишком много попыток. Повторите через минуту.")
        row = connection.execute("SELECT salt, digest, recovery, version FROM users WHERE email = ?", (email,)).fetchone()
        if action == "register":
            if row:
                raise ValueError("Аккаунт уже существует. Войдите или восстановите доступ.")
            salt = secrets.token_bytes(16)
            code = secrets.token_urlsafe(24)
            connection.execute("INSERT INTO users VALUES (?, ?, ?, ?, 1)", (email, salt, password_digest(password, salt), hashlib.sha256(code.encode()).digest()))
            return {"email": email, "version": 1, "recovery_code": code}
        candidate = password_digest(password, row[0] if row else b"missing-user-salt")
        valid = row and (hmac.compare_digest(candidate, row[1]) if action == "login" else hmac.compare_digest(hashlib.sha256(recovery.encode()).digest(), row[2]))
        if not valid:
            count = attempt[0] + 1 if attempt and attempt[1] > now else 1
            connection.execute("INSERT OR REPLACE INTO attempts VALUES (?, ?, ?)", (email, count, now + 60))
            connection.commit()
            raise ValueError("Неверный email, пароль или резервный код.")
        connection.execute("DELETE FROM attempts WHERE email = ?", (email,))
        if action == "recover":
            salt = secrets.token_bytes(16)
            code = secrets.token_urlsafe(24)
            connection.execute("UPDATE users SET salt = ?, digest = ?, recovery = ?, version = version + 1 WHERE email = ?", (salt, password_digest(password, salt), hashlib.sha256(code.encode()).digest(), email))
            return {"email": email, "version": row[3] + 1, "recovery_code": code}
        return {"email": email, "version": row[3]}


def session_valid(database: Path, account: dict, now: float) -> bool:
    if not account or now - account.get("last_seen", 0) > 1800 or now - account.get("created", 0) > 28800 or not database.exists():
        return False
    with sqlite3.connect(database) as connection:
        row = connection.execute("SELECT version FROM users WHERE email = ?", (account["email"],)).fetchone()
    return bool(row and row[0] == account["version"])
