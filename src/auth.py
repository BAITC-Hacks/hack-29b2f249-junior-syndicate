from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

import requests


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


class SupabaseAuth:
    def __init__(self, url: str, key: str, allowed_emails: str):
        self.url = url.rstrip("/")
        if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co", self.url):
            raise ValueError("Укажите URL проекта Supabase вида https://project.supabase.co.")
        if not key or key.startswith("sb_secret_"):
            raise ValueError("Для Supabase нужен publishable key, а не секретный ключ.")
        self.key = key
        self.allowed_emails = {email.strip().lower() for email in allowed_emails.split(",") if email.strip()}
        if not self.allowed_emails:
            raise ValueError("Укажите разрешённые email в MONEY_GRAPH_ALLOWED_EMAILS.")

    def request(self, method: str, path: str, data: dict | None = None, token: str = "") -> dict:
        headers = {"apikey": self.key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.request(method, self.url + "/auth/v1/" + path,
                                        headers=headers, json=data, timeout=15, allow_redirects=False)
        except requests.RequestException:
            raise ValueError("Не удалось связаться с Supabase. Повторите попытку позже.") from None
        if not 200 <= response.status_code < 300:
            try:
                code = response.json().get("error_code", "")
            except ValueError:
                code = ""
            messages = {
                "email_not_confirmed": "Подтвердите email по письму Supabase, затем войдите.",
                "invalid_credentials": "Неверный email или пароль.",
                "otp_expired": "Код недействителен или истёк. Запросите новый код.",
                "email_address_not_authorized": "Настройте отправку почты в Supabase или используйте разрешённый адрес.",
                "signup_disabled": "Регистрация отключена владельцем проекта.",
                "weak_password": "Пароль не соответствует требованиям Supabase.",
                "same_password": "Новый пароль должен отличаться от предыдущего.",
            }
            if response.status_code == 429:
                raise ValueError("Слишком много запросов. Подождите перед повторной попыткой.")
            raise ValueError(messages.get(code, "Supabase отклонил запрос. Проверьте данные и настройки авторизации."))
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            raise ValueError("Supabase вернул некорректный ответ.") from None

    def check_email(self, email: str) -> str:
        email = email.strip().lower()
        if email not in self.allowed_emails:
            raise ValueError("Доступ к рабочей области для этого email не предоставлен.")
        return email

    def account(self, result: dict) -> dict:
        token = result.get("access_token", "")
        if not token:
            raise ValueError("В ответе Supabase нет сессии. Войдите повторно.")
        user = self.request("GET", "user", token=token)
        email = self.check_email(user.get("email", ""))
        if not user.get("email_confirmed_at"):
            raise ValueError("Подтвердите email перед входом.")
        return {"provider": "supabase", "email": email, "user_id": user["id"],
                "access_token": token, "refresh_token": result.get("refresh_token", ""),
                "expires_at": time.time() + int(result.get("expires_in", 3600))}

    def action(self, action: str, email: str, password: str = "", recovery: str = "") -> dict:
        email = self.check_email(email)
        if len(password) > 256:
            raise ValueError("Пароль должен содержать не более 256 символов.")
        if action in ("register", "recover") and len(password) < 12:
            raise ValueError("Используйте пароль длиной от 12 символов.")
        if action == "login":
            result = self.request("POST", "token?grant_type=password", {"email": email, "password": password})
            return {"account": self.account(result)}
        if action == "register":
            result = self.request("POST", "signup", {"email": email, "password": password})
            if result.get("access_token"):
                return {"account": self.account(result)}
            return {"message": "Если регистрация доступна, письмо подтверждения отправлено. Подтвердите email и войдите."}
        if action == "recover_request":
            self.request("POST", "recover", {"email": email})
            return {"message": "Если аккаунт существует, письмо отправлено. Скопируйте из него ссылку восстановления или код и задайте новый пароль.",
                    "recovery_sent": True}
        if action == "recover":
            verification = {"email": email, "token": recovery.strip(), "type": "recovery"}
            if not re.fullmatch(r"\d{6,10}", recovery.strip()):
                link = urlsplit(recovery.strip())
                query = parse_qs(link.query)
                if link.scheme != "https" or link.netloc != urlsplit(self.url).netloc or link.path != "/auth/v1/verify" or query.get("type") != ["recovery"] or not query.get("token"):
                    raise ValueError("Введите код или скопированную ссылку восстановления из письма Supabase.")
                verification = {"token_hash": query["token"][0], "type": "recovery"}
            result = self.request("POST", "verify", verification)
            account = self.account(result)
            if account["email"] != email:
                raise ValueError("Email сессии не совпадает с запросом восстановления.")
            self.request("PUT", "user", {"password": password}, token=account["access_token"])
            self.request("POST", "logout?scope=global", token=account["access_token"])
            return {"message": "Пароль обновлён. Войдите с новым паролем.", "password_updated": True}
        raise ValueError("Неизвестное действие авторизации.")

    def validate(self, account: dict, now: float) -> dict:
        if account.get("provider") != "supabase" or now - account.get("last_seen", 0) > 1800 or now - account.get("created", 0) > 28800:
            return {}
        if account.get("expires_at", 0) <= now + 60:
            result = self.request("POST", "token?grant_type=refresh_token", {"refresh_token": account.get("refresh_token", "")})
            updated = self.account(result)
            if updated["user_id"] != account.get("user_id"):
                raise ValueError("Пользователь сессии изменился. Войдите повторно.")
            return {**account, **updated}
        user = self.request("GET", "user", token=account.get("access_token", ""))
        if not user.get("email_confirmed_at") or user.get("id") != account.get("user_id"):
            return {}
        return {**account, "email": self.check_email(user.get("email", ""))}
