from pathlib import Path
import base64
import os
import sys
import time

from dotenv import dotenv_values

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth import account_action, session_valid, SupabaseAuth
from src.pipeline import run, explain_node
from src.workspace import load_workspace, workspace_payload, node_dossier, ranked_nodes, simulation_payload, node_ai_context, explain_with_ai

OUTPUT = Path(os.environ.get("MONEY_GRAPH_OUTPUT", str(ROOT / "output")))
DATABASE = Path(os.environ.get("MONEY_GRAPH_ACCOUNTS", str(ROOT / ".streamlit/users.sqlite3")))
st.set_page_config(page_title="Qadam · Junior Syndicate", layout="wide", initial_sidebar_state="collapsed")
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


try:
    settings = st.secrets.to_dict()
except FileNotFoundError:
    settings = {}
supabase_settings = settings.get("supabase", {})
google_settings = settings.get("auth", {})
supabase_url = os.environ.get("SUPABASE_URL", supabase_settings.get("url", ""))
auth_mode = os.environ.get("MONEY_GRAPH_AUTH", "supabase" if supabase_url else "local")
supabase = None
auth_error = ""
try:
    if auth_mode == "supabase":
        supabase = SupabaseAuth(supabase_url,
                                os.environ.get("SUPABASE_PUBLISHABLE_KEY", supabase_settings.get("publishable_key", "")),
                                os.environ.get("MONEY_GRAPH_ALLOWED_EMAILS", supabase_settings.get("allowed_emails", "")))
    elif auth_mode != "local":
        raise ValueError("Неизвестный режим авторизации.")
except ValueError as error:
    auth_error = str(error)
google_required = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")
google_enabled = auth_mode == "local" and all(str(google_settings.get(key, "")).strip() for key in google_required)
if auth_mode == "local" and google_settings and not google_enabled:
    auth_error = "Google OAuth настроен не полностью. Проверьте redirect_uri, cookie_secret, client_id и client_secret."
oidc_user = auth_mode == "local" and bool(getattr(st.user, "is_logged_in", False))
now = time.time()
account = st.session_state.get("account", {})
had_account = bool(account)
try:
    if account:
        if auth_mode == "supabase":
            account = supabase.validate(account, now) if supabase else {}
        elif account.get("provider") == "supabase" or not session_valid(DATABASE, account, now):
            account = {}
except ValueError as error:
    account = {}
    auth_error = str(error)
if account:
    st.session_state.account = account
else:
    st.session_state.pop("account", None)
    if had_account:
        st.session_state.pop("response", None)
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

ai_settings = {**dotenv_values(ROOT / ".env"), **os.environ}
api_key = (ai_settings.get("OPENAI_API_KEY") or "").strip()
ai_enabled = bool(api_key and (ai_settings.get("QADAM_ALLOW_EXTERNAL_AI") or "").lower() == "true")

workspace = components.declare_component("analyst_workspace", path=str(ROOT / "app/frontend"))
event = workspace(payload=payload, authenticated=authenticated, email=email, google_enabled=google_enabled,
                  auth_mode=auth_mode, auth_error=auth_error,
                  error=load_error, ai_enabled=authenticated and ai_enabled, response=st.session_state.get("response", {}), key="workspace", default=None)
if isinstance(event, dict) and event.get("id") and event["id"] != st.session_state.get("handled_event"):
    st.session_state.handled_event = event["id"]
    response = {"id": event["id"], "action": event.get("action")}
    if event.get("action") == "explain":
        response["gid"] = str(event.get("gid", ""))
    try:
        action = event.get("action")
        if action in ("login", "register", "recover", "recover_request") and auth_mode == "supabase":
            if not supabase:
                raise ValueError(auth_error)
            result = supabase.action(action, str(event.get("email", "")), str(event.get("password", "")), str(event.get("recovery", "")))
            new_account = result.pop("account", None)
            response.update(result)
            if new_account:
                st.session_state.account = {**new_account, "created": now, "last_seen": now}
            elif result.get("password_updated"):
                st.session_state.pop("account", None)
        elif action in ("login", "register", "recover") and auth_mode == "local":
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
            if account.get("provider") == "supabase" and supabase:
                supabase.request("POST", "logout?scope=local", token=account["access_token"])
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
        elif action == "explain":
            if not ai_enabled:
                raise ValueError("ИИ не подключён. Настройте локальный .env; исходное обоснование доступно.")
            selected_card = explain_node(int(response["gid"]), features=nodes)
            context = node_ai_context(selected_card, edges)
            response["explanation"] = explain_with_ai(context, api_key, ai_settings.get("OPENAI_MODEL") or "gpt-4o-mini")
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
    except (ValueError, KeyError, OSError, TypeError, RuntimeError) as error:
        response["error"] = str(error)
    st.session_state.response = response
    st.rerun()
