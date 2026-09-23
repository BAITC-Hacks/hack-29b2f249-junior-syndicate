import json
from pathlib import Path
import time

from streamlit.testing.v1 import AppTest

from src.auth import account_action

ROOT = Path(__file__).resolve().parents[1]


def test_unauthenticated_component_receives_no_analysis():
    app = AppTest.from_file(str(ROOT / "app/app.py")).run()
    assert not app.exception
    args = json.loads(app.get("component_instance")[0].proto.json_args)
    assert args["authenticated"] is False
    assert args["payload"] is None
    assert args["email"] == ""


def test_authenticated_missing_output_has_helpful_state(tmp_path, monkeypatch):
    database = tmp_path / "users.sqlite3"
    monkeypatch.setenv("MONEY_GRAPH_OUTPUT", str(tmp_path / "missing"))
    monkeypatch.setenv("MONEY_GRAPH_ACCOUNTS", str(database))
    account = account_action(database, "register", "analyst@example.com", "Long analyst password!")
    now = time.time()
    app = AppTest.from_file(str(ROOT / "app/app.py"))
    app.session_state["account"] = {**account, "created": now, "last_seen": now}
    app.run()
    assert not app.exception
    args = json.loads(app.get("component_instance")[0].proto.json_args)
    assert args["authenticated"] is True
    assert args["payload"] is None
    assert "python run.py" in args["error"]


def test_expired_session_receives_no_analysis(tmp_path, monkeypatch):
    database = tmp_path / "users.sqlite3"
    monkeypatch.setenv("MONEY_GRAPH_ACCOUNTS", str(database))
    account = account_action(database, "register", "analyst@example.com", "Long analyst password!")
    app = AppTest.from_file(str(ROOT / "app/app.py"))
    app.session_state["account"] = {**account, "created": time.time() - 1900, "last_seen": time.time() - 1900}
    app.run()
    args = json.loads(app.get("component_instance")[0].proto.json_args)
    assert args["payload"] is None
    assert not args["authenticated"]
