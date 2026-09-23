import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from streamlit.testing.v1 import AppTest

from src.auth import SupabaseAuth

EMAIL = "analyst@example.com"
URL = "https://test-project.supabase.co"
USER = {"id": "user-1", "email": EMAIL, "email_confirmed_at": "2026-09-23T10:00:00Z"}
TOKENS = {"access_token": "private-access", "refresh_token": "private-refresh", "expires_in": 3600}


@pytest.fixture
def auth():
    return SupabaseAuth(URL, "sb_publishable_test", EMAIL)


def test_login_checks_remote_user_and_does_not_trust_token_response(auth, monkeypatch):
    remote = Mock(side_effect=[{**TOKENS, "user": {"email": "forged@example.com"}}, USER])
    monkeypatch.setattr(auth, "request", remote)
    account = auth.action("login", EMAIL, "A long password!")["account"]
    assert account["email"] == EMAIL
    assert account["user_id"] == USER["id"]
    assert remote.call_args.args == ("GET", "user")
    assert remote.call_args.kwargs["token"] == TOKENS["access_token"]


def test_email_confirmation_does_not_create_an_authenticated_session(auth, monkeypatch):
    monkeypatch.setattr(auth, "request", Mock(return_value={"id": "unconfirmed"}))
    result = auth.action("register", EMAIL, "A long password!")
    assert "account" not in result
    assert "Подтвердите" in result["message"]
    monkeypatch.setattr(auth, "request", Mock(return_value={**USER, "email_confirmed_at": None}))
    with pytest.raises(ValueError, match="Подтвердите"):
        auth.account(TOKENS)


def test_invite_gate_checks_both_input_and_verified_identity(auth, monkeypatch):
    remote = Mock(return_value={**USER, "email": "outsider@example.com"})
    monkeypatch.setattr(auth, "request", remote)
    with pytest.raises(ValueError, match="не предоставлен"):
        auth.action("register", "outsider@example.com", "A long password!")
    remote.assert_not_called()
    with pytest.raises(ValueError, match="не предоставлен"):
        auth.account(TOKENS)


def test_refresh_is_per_session_and_preserves_identity(auth, monkeypatch):
    now = time.time()
    old = {"provider": "supabase", "user_id": USER["id"], "email": EMAIL,
           "created": now, "last_seen": now, "expires_at": now, "refresh_token": "old-refresh"}
    remote = Mock(side_effect=[TOKENS, USER])
    monkeypatch.setattr(auth, "request", remote)
    updated = auth.validate(old, now)
    assert updated["created"] == now
    assert updated["refresh_token"] == "private-refresh"
    assert old["refresh_token"] == "old-refresh"
    assert remote.call_args_list[0].args[2] == {"refresh_token": "old-refresh"}
    remote.side_effect = [TOKENS, {**USER, "id": "another-user"}]
    with pytest.raises(ValueError, match="изменился"):
        auth.validate(old, now)
    assert auth.validate({**old, "last_seen": now - 1801}, now) == {}


@pytest.mark.parametrize("recovery", ["123456", URL + "/auth/v1/verify?token=one-time-hash&type=recovery"])
def test_recovery_verifies_possession_before_updating_password(auth, monkeypatch, recovery):
    remote = Mock(side_effect=[TOKENS, USER, USER, {}])
    monkeypatch.setattr(auth, "request", remote)
    result = auth.action("recover", EMAIL, "New long password!", recovery)
    assert result["password_updated"]
    assert "account" not in result
    assert remote.call_args_list[0].args[:2] == ("POST", "verify")
    assert remote.call_args_list[2].args == ("PUT", "user", {"password": "New long password!"})
    assert remote.call_args_list[3].args == ("POST", "logout?scope=global")


def test_recovery_rejects_foreign_links_and_wrong_accounts(auth, monkeypatch):
    remote = Mock()
    monkeypatch.setattr(auth, "request", remote)
    with pytest.raises(ValueError):
        auth.action("recover", EMAIL, "New long password!", "https://evil.example/?token=secret&type=recovery")
    remote.assert_not_called()
    auth.allowed_emails.add("other@example.com")
    remote.side_effect = [TOKENS, {**USER, "email": "other@example.com"}]
    with pytest.raises(ValueError, match="не совпадает"):
        auth.action("recover", EMAIL, "New long password!", "123456")
    assert remote.call_count == 2


def test_transport_does_not_follow_redirects_or_expose_server_errors(auth, monkeypatch):
    remote = Mock(return_value=Mock(status_code=500, json=lambda: {"msg": "private-password"}))
    monkeypatch.setattr(requests, "request", remote)
    with pytest.raises(ValueError) as error:
        auth.request("GET", "user", token="private-token")
    assert "private" not in str(error.value)
    assert remote.call_args.kwargs["allow_redirects"] is False
    remote.side_effect = requests.ConnectionError("private-network-details")
    with pytest.raises(ValueError, match="связаться"):
        auth.request("GET", "settings")


def test_supabase_component_never_receives_tokens_and_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("MONEY_GRAPH_AUTH", "supabase")
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("MONEY_GRAPH_ALLOWED_EMAILS", EMAIL)
    monkeypatch.setenv("MONEY_GRAPH_OUTPUT", str(tmp_path / "missing"))
    monkeypatch.setattr(SupabaseAuth, "request", Mock(return_value=USER))
    now = time.time()
    account = {"provider": "supabase", "user_id": USER["id"], "email": EMAIL,
               **TOKENS, "created": now, "last_seen": now, "expires_at": now + 3600}
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/app.py"))
    app.session_state["account"] = account
    app.run()
    assert not app.exception
    raw = app.get("component_instance")[0].proto.json_args
    assert json.loads(raw)["authenticated"] is True
    assert "private-access" not in raw and "private-refresh" not in raw
    app.session_state["response"] = {"id": "old-export", "download": {"base64": "private-export"}}
    monkeypatch.setattr(SupabaseAuth, "request", Mock(side_effect=ValueError("Unavailable")))
    app.run()
    args = json.loads(app.get("component_instance")[0].proto.json_args)
    assert args["authenticated"] is False and args["payload"] is None
    assert args["auth_error"] == "Unavailable"
    assert args["response"] == {}


def test_cloud_configuration_cannot_silently_fall_back_to_sqlite(monkeypatch):
    monkeypatch.setenv("MONEY_GRAPH_AUTH", "supabase")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app/app.py")).run()
    assert not app.exception
    args = json.loads(app.get("component_instance")[0].proto.json_args)
    assert args["authenticated"] is False
    assert args["auth_error"]
