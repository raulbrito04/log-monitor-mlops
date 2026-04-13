from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from src.dashboard.auth import current_user, logout
from src.dashboard.config import get_config


def configure_page(title: str, icon: str) -> None:
    st.set_page_config(
        page_title=title,
        page_icon=icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        [data-testid="stMetricValue"] { font-size: 1.65rem; }
        .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
        .dashboard-note { color: #5f6368; font-size: 0.95rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(page_title: str, auto_refresh: bool) -> None:
    config = get_config()
    st.sidebar.title("Log Monitor")
    st.sidebar.caption(page_title)
    st.sidebar.write(f"Signed in as `{current_user() or 'anonymous'}`")
    st.sidebar.write(f"Refresh interval: `{config.refresh_seconds}s`")
    st.sidebar.write(f"Auto refresh: `{'on' if auto_refresh else 'off'}`")
    st.sidebar.caption(f"Updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    if st.sidebar.button("Log out", use_container_width=True):
        logout()
        st.rerun()


def format_timestamp(value) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return str(value)


def humanize_seconds(value: float | int | None) -> str:
    if value is None:
        return "-"
    seconds = float(value)
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def render_error(message: str) -> None:
    st.error(message)


def render_empty(message: str) -> None:
    st.info(message)
