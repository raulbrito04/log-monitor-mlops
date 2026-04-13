from __future__ import annotations

from src.dashboard.auth import require_auth
from src.dashboard.pages_impl import render_alerts_page
from src.dashboard.ui import configure_page


def main() -> None:
    configure_page("Alerts", "🚨")
    require_auth()
    render_alerts_page()


main()
