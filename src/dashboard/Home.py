from __future__ import annotations

from src.dashboard.auth import require_auth
from src.dashboard.pages_impl import render_overview_page
from src.dashboard.ui import configure_page


def main() -> None:
    configure_page("Log Monitor Dashboard", "🛰️")
    require_auth()
    render_overview_page()


main()
