from pathlib import Path
import base64
import os
import sys
import time

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import account_action, session_valid
from src.pipeline import run
from src.workspace import load_workspace, workspace_payload, node_dossier, ranked_nodes, simulation_payload

OUTPUT = Path(os.environ.get("MONEY_GRAPH_OUTPUT", str(ROOT / "output")))
DATABASE = Path(os.environ.get("MONEY_GRAPH_ACCOUNTS", str(ROOT / ".streamlit/users.sqlite3")))
st.set_page_config(page_title="MoneyGraph Intelligence · Junior Syndicate", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header[data-testid="stHeader"],footer,[data-testid="stToolbar"]{display:none}
.block-container{padding:0!important;max-width:100%!important}
[data-testid="stVerticalBlock"]{gap:0!important}
iframe{display:block;border:0;width:100%;color-scheme:dark}
html,body,[data-testid="stAppViewContainer"]{background:#080b16}
</style>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def read_results(directory: str, revision: tuple):
    nodes, edges, clusters, summary = load_workspace(Path(directory))
    return nodes, edges, workspace_payload(nodes, edges, clusters, summary)


@st.cache_data(show_spinner=False)
def stress_results(directory: str, revision: tuple, count: int):
    nodes, edges, _, _ = load_workspace(Path(directory))
    return simulation_payload(nodes, edges, count)


google_enabled = False
if (ROOT / ".streamlit/secrets.toml").exists():
    google_enabled = bool(st.secrets.get("auth", {}).get("client_id"))
oidc_user = bool(getattr(st.user, "is_logged_in", False))
now = time.time()
account = st.session_state.get("account", {})
if account and not session_valid(DATABASE, account, now):
    st.session_state.pop("account", None)
    st.session_state.pop("response", None)
    account = {}
authenticated = bool(account or oidc_user)
email = account.get("email", "") if account else (st.user.get("email", "Google account") if oidc_user else "")
payload = None
load_error = ""
revision = ()
if authenticated:
    try:
        revision = tuple((OUTPUT / name).stat().st_mtime_ns for name in ("node_features.csv", "graph_edges.csv", "clusters.csv", "run_summary.json"))
        nodes, edges, payload = read_results(str(OUTPUT), revision)
    except FileNotFoundError:
        load_error = "Нет результатов анализа. Нажмите «Запустить анализ» или выполните python run.py."
    except (ValueError, KeyError, OSError) as error:
        load_error = f"Не удалось прочитать результаты: {error}"

workspace = components.declare_component("analyst_workspace", path=str(ROOT / "app/frontend"))
event = workspace(payload=payload, authenticated=authenticated, email=email, google_enabled=google_enabled,
                  error=load_error, response=st.session_state.get("response", {}), key="workspace", default=None)
if isinstance(event, dict) and event.get("id") and event["id"] != st.session_state.get("handled_event"):
    st.session_state.handled_event = event["id"]
    response = {"id": event["id"], "action": event.get("action")}
    try:
        action = event.get("action")
        if action in ("login", "register", "recover"):
            result = account_action(DATABASE, action, str(event.get("email", "")), str(event.get("password", "")), str(event.get("recovery", "")))
            code = result.pop("recovery_code", None)
            if code:
                response["recovery_code"] = code
            st.session_state.account = {**result, "created": now, "last_seen": now}
        elif action == "google":
            if not google_enabled:
                raise ValueError("Google OAuth ещё не настроен владельцем приложения.")
            st.login()
        elif action == "logout":
            st.session_state.pop("account", None)
            if oidc_user:
                st.logout()
        elif not authenticated:
            raise ValueError("Для доступа к данным войдите в аккаунт.")
        elif action == "run":
            run(Path(os.environ.get("MONEY_GRAPH_DATA", str(ROOT / "data"))), OUTPUT)
            read_results.clear()
            stress_results.clear()
            response["message"] = "Анализ завершён. Все показатели обновлены."
        elif payload is None:
            raise ValueError(load_error)
        elif action == "select":
            response["card"] = node_dossier(nodes, edges, str(event.get("gid", "")))
        elif action == "query":
            cluster = event.get("cluster")
            selected = ranked_nodes(nodes, event.get("role") or None, int(cluster) if cluster not in (None, "") else None, str(event.get("query", "")))
            response["ids"] = selected.gid.astype(str).tolist()
        elif action == "simulate":
            response["simulation"] = stress_results(str(OUTPUT), revision, int(event.get("count", 5)))
        elif action == "export":
            filename = event.get("filename", "nodes_roles.csv")
            if filename not in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv", "analysis_report.md", "run_summary.json"):
                raise ValueError("Неизвестный файл экспорта.")
            response["download"] = {"filename": filename, "base64": base64.b64encode((OUTPUT / filename).read_bytes()).decode()}
        else:
            raise ValueError("Неизвестное действие.")
        if st.session_state.get("account"):
            st.session_state.account["last_seen"] = now
    except (ValueError, KeyError, OSError, TypeError) as error:
        response["error"] = str(error)
    st.session_state.response = response
    st.rerun()
