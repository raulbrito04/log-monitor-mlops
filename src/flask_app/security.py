from __future__ import annotations

from flask import Flask, request
from flask_talisman import Talisman

from src.flask_app.config import is_production

CSP_POLICY = {
    "default-src": "'self'",
    "script-src": ["'self'", "https://cdn.jsdelivr.net"],
    "style-src": ["'self'", "https://cdn.jsdelivr.net", "'unsafe-inline'"],
    "img-src": ["'self'", "data:"],
    "font-src": ["'self'", "https://cdn.jsdelivr.net"],
    "connect-src": ["'self'"],
    "frame-src": ["'none'"],
    "object-src": ["'none'"],
}


def init_security_headers(app: Flask) -> None:
    Talisman(
        app,
        force_https=is_production(),
        strict_transport_security=is_production(),
        strict_transport_security_max_age=31536000,
        strict_transport_security_include_subdomains=True,
        content_security_policy=CSP_POLICY,
        referrer_policy="no-referrer",
        frame_options="DENY",
        session_cookie_secure=is_production(),
        session_cookie_http_only=True,
    )


def add_cache_headers(app: Flask) -> None:
    @app.after_request
    def set_cache_headers(response):
        sensitive_prefixes = ("/login", "/admin", "/api/upload")
        if any(request.path.startswith(prefix) for prefix in sensitive_prefixes):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response