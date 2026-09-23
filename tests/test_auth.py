import sqlite3
import time

import pytest

from src.auth import account_action, session_valid


def test_password_storage_login_and_logout_expiry(tmp_path):
    database = tmp_path / "accounts.sqlite3"
    result = account_action(database, "register", "Analyst@example.com", "Long analyst password!")
    assert account_action(database, "login", "analyst@example.com", "Long analyst password!")["email"] == "analyst@example.com"
    now = time.time()
    account = {**result, "created": now, "last_seen": now}
    assert session_valid(database, account, now)
    assert not session_valid(database, account, now + 1801)
    with sqlite3.connect(database) as connection:
        salt, digest, recovery = connection.execute("SELECT salt, digest, recovery FROM users").fetchone()
    assert len(salt) == 16 and len(digest) == 32
    assert b"Long analyst password!" not in database.read_bytes()
    assert result["recovery_code"].encode() not in database.read_bytes()
    assert len(recovery) == 32


def test_recovery_rotates_code_password_and_revokes_sessions(tmp_path):
    database = tmp_path / "accounts.sqlite3"
    old = account_action(database, "register", "analyst@example.com", "Long analyst password!")
    now = time.time()
    session = {**old, "created": now, "last_seen": now}
    updated = account_action(database, "recover", old["email"], "New analyst password!", old["recovery_code"])
    assert updated["recovery_code"] != old["recovery_code"]
    assert not session_valid(database, session, now)
    with pytest.raises(ValueError):
        account_action(database, "login", old["email"], "Long analyst password!")
    with pytest.raises(ValueError):
        account_action(database, "recover", old["email"], "Third analyst password!", old["recovery_code"])
    assert account_action(database, "login", old["email"], "New analyst password!")["version"] == 2


def test_repeated_failures_are_rate_limited_across_connections(tmp_path):
    database = tmp_path / "accounts.sqlite3"
    account_action(database, "register", "analyst@example.com", "Long analyst password!")
    for _ in range(5):
        with pytest.raises(ValueError, match="Неверный"):
            account_action(database, "login", "analyst@example.com", "wrong")
    with pytest.raises(ValueError, match="Слишком много"):
        account_action(database, "login", "analyst@example.com", "Long analyst password!")


def test_registration_validation_and_unique_accounts(tmp_path):
    database = tmp_path / "accounts.sqlite3"
    with pytest.raises(ValueError):
        account_action(database, "register", "not-an-email", "Long analyst password!")
    with pytest.raises(ValueError):
        account_action(database, "register", "analyst@example.com", "short")
    account_action(database, "register", "analyst@example.com", "Long analyst password!")
    with pytest.raises(ValueError, match="существует"):
        account_action(database, "register", "ANALYST@example.com", "Long analyst password!")
