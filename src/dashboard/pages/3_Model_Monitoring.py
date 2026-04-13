from __future__ import annotations

from src.dashboard.auth import require_auth
from src.dashboard.pages_impl import render_model_monitoring_page
from src.dashboard.ui import configure_page


def main() -> None:
    configure_page("Model Monitoring", "📈")
    require_auth()
    render_model_monitoring_page()


main()
