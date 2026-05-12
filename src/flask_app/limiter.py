from __future__ import annotations

import os

from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[os.getenv("RATELIMIT_DEFAULT", "200 per hour")],
    storage_uri=os.getenv("REDIS_URL", "memory://"),
    strategy="fixed-window",
)


def init_limiter(app: Flask) -> None:
    limiter.init_app(app)

    @app.errorhandler(429)
    def ratelimit_handler(error):
        return (
            jsonify(
                {
                    "error": "too_many_requests",
                    "message": "Demasiados pedidos. Tenta de novo mais tarde.",
                    "path": request.path,
                    "retry_after": str(getattr(error, "description", "rate limit exceeded")),
                }
            ),
            429,
        )