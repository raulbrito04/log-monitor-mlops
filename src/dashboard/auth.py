from __future__ import annotations

import streamlit as st

from src.dashboard.config import get_config

_SESSION_AUTH_KEY = "dashboard_authenticated"
_SESSION_USER_KEY = "dashboard_username"


def is_authenticated() -> bool:
    return bool(st.session_state.get(_SESSION_AUTH_KEY, False))


def current_user() -> str | None:
    return st.session_state.get(_SESSION_USER_KEY)


def attempt_login(username: str, password: str) -> bool:
    config = get_config()
    if username == config.dashboard_username and password == config.dashboard_password:
        st.session_state[_SESSION_AUTH_KEY] = True
        st.session_state[_SESSION_USER_KEY] = username
        return True
    st.session_state[_SESSION_AUTH_KEY] = False
    st.session_state.pop(_SESSION_USER_KEY, None)
    return False


def logout() -> None:
    st.session_state.pop(_SESSION_AUTH_KEY, None)
    st.session_state.pop(_SESSION_USER_KEY, None)


def render_login_gate() -> None:
    st.title("Log Monitor Dashboard")
    st.caption("Read-only operator dashboard for alerts, logs, and model monitoring.")

    with st.form("dashboard_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        if attempt_login(username.strip(), password):
            st.success("Signed in successfully.")
            st.rerun()
        st.error("Invalid dashboard credentials.")


def require_auth() -> None:
    if is_authenticated():
        return
    render_login_gate()
    st.stop()
