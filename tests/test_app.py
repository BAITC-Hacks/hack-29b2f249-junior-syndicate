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


def test_ai_event_requires_login_and_never_exposes_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-server-secret")
    monkeypatch.setenv("QADAM_ALLOW_EXTERNAL_AI", "true")
    args_seen = []
    def component(**kwargs):
        args_seen.append(kwargs)
        return {"id": "ai-no-login", "action": "explain", "gid": "100"}
    monkeypatch.setattr("streamlit.components.v1.declare_component", lambda *args, **kwargs: component)
    def unexpected(*args):
        raise AssertionError("Unauthorized API call")
    monkeypatch.setattr("src.workspace.explain_with_ai", unexpected)
    app = AppTest.from_file(str(ROOT / "app/app.py"), default_timeout=30).run()
    assert not app.exception
    assert "войдите" in app.session_state["response"]["error"]
    assert all(not args["ai_enabled"] for args in args_seen)
    assert "test-server-secret" not in json.dumps(args_seen)


def test_ai_event_uses_server_metrics_once_and_handles_errors(tmp_path, monkeypatch, features, sample_data, config):
    from src.scoring import assign_roles, assign_priority, generate_evidence
    nodes = assign_priority(assign_roles(features, config), config)
    nodes["evidence"] = nodes.apply(generate_evidence, axis=1)
    database = tmp_path / "users.sqlite3"
    monkeypatch.setenv("MONEY_GRAPH_ACCOUNTS", str(database))
    monkeypatch.setenv("OPENAI_API_KEY", "test-server-secret")
    monkeypatch.setenv("QADAM_ALLOW_EXTERNAL_AI", "true")
    folder = tmp_path / "output"
    folder.mkdir()
    for name in ("node_features.csv", "graph_edges.csv", "clusters.csv", "run_summary.json"):
        (folder / name).write_text("fixture")
    monkeypatch.setenv("MONEY_GRAPH_OUTPUT", str(folder))
    monkeypatch.setattr("src.workspace.load_workspace", lambda *args: (nodes, sample_data.edges, None, {}))
    monkeypatch.setattr("src.workspace.workspace_payload", lambda *args: {"summary": {}})
    event = {"id": "ai-success", "action": "explain", "gid": "100", "role": "fake-client-role", "priority_score": 999}
    monkeypatch.setattr("streamlit.components.v1.declare_component", lambda *args, **kwargs: lambda **values: event.copy())
    calls = []
    def explain(payload, key, model):
        calls.append(payload)
        assert payload["role"] != "fake-client-role"
        assert payload["priority_score"] != 999
        assert payload["metrics"]["in_degree"] == 20
        return {"summary": "Проверяемая гипотеза", "reasons": ["20 отправителей"], "limitations": ["Неполный вход"]}
    monkeypatch.setattr("src.workspace.explain_with_ai", explain)
    account = account_action(database, "register", "ai-test@example.com", "Local test password!")
    now = time.time()
    app = AppTest.from_file(str(ROOT / "app/app.py"), default_timeout=30)
    app.session_state["account"] = {**account, "created": now, "last_seen": now}
    app.run()
    assert not app.exception and len(calls) == 1
    assert app.session_state["response"]["explanation"]["summary"] == "Проверяемая гипотеза"
    app.run()
    assert len(calls) == 1
    event.update(id="ai-no-permission")
    monkeypatch.setenv("QADAM_ALLOW_EXTERNAL_AI", "false")
    app.run()
    assert "не подключён" in app.session_state["response"]["error"]
    assert len(calls) == 1
    monkeypatch.setenv("QADAM_ALLOW_EXTERNAL_AI", "true")
    event.update(id="ai-invalid-gid", gid="999999")
    app.run()
    assert "error" in app.session_state["response"] and len(calls) == 1
    def unavailable(*args):
        raise RuntimeError("ИИ временно недоступен")
    monkeypatch.setattr("src.workspace.explain_with_ai", unavailable)
    event.update(id="ai-error", gid="100")
    app.run()
    assert not app.exception
    assert app.session_state["response"]["gid"] == "100"
    assert "недоступен" in app.session_state["response"]["error"]
