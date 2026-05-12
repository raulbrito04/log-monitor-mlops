from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from flask import Flask, Response, g, jsonify, request
from pydantic import ValidationError
from prometheus_flask_exporter import PrometheusMetrics
from pythonjsonlogger import jsonlogger

from src.flask_app.config import AppConfig, get_demo_users
from src.flask_app.limiter import init_limiter, limiter
from src.flask_app.security import add_cache_headers, init_security_headers
from src.flask_app.validators import (
    LoginPayload,
    PaginationQuery,
    SearchQuery,
    first_validation_error,
    validate_model,
    validate_upload_filename,
)
from src.monitoring.metrics import persist_runtime_metrics, refresh_monitoring_metrics

LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
APP_VERSION: str = "1.0.0"

SAMPLE_DATA: list[dict[str, Any]] = [
    {"id": i, "value": f"data_item_{i}", "category": ["A", "B", "C"][i % 3]}
    for i in range(1, 51)
]

SAMPLE_USERS: list[dict[str, str | int]] = [
    {"id": i, "username": f"user{i}", "email": f"user{i}@example.com", "role": "user"}
    for i in range(1, 21)
]


@dataclass
class LogEntry:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ip: str = "unknown"
    method: str = "unknown"
    endpoint: str = "unknown"
    status: int = 0
    response_time_ms: float = 0.0
    user_agent: str = "unknown"
    request_body: dict[str, Any] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)
    user: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "ip": self.ip,
            "method": self.method,
            "endpoint": self.endpoint,
            "status": self.status,
            "response_time_ms": round(self.response_time_ms, 2),
            "user_agent": self.user_agent,
        }
        if self.request_body:
            result["request_body"] = self.request_body
        if self.query_params:
            result["query_params"] = self.query_params
        if self.user:
            result["user"] = self.user
        if self.extra:
            result.update(self.extra)
        return result


def setup_logging(log_file: str = LOG_FILE, level: str = LOG_LEVEL) -> logging.Logger:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger("flask_app")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    json_formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(json_formatter)

    if not logger.handlers:
        logger.addHandler(stream_handler)
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(json_formatter)
            logger.addHandler(file_handler)
        except OSError:
            logger.warning("Cannot write to log file %s — logging to stdout only", log_file)

    return logger


def require_admin(valid_users: dict[str, dict[str, str]]):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                g.log_entry.extra["auth_result"] = "missing_token"
                return jsonify({"error": "Authorization header required"}), 401

            token = auth_header.replace("Bearer ", "")
            parts = token.split("_")
            if len(parts) != 3 or parts[0] != "token":
                g.log_entry.extra["auth_result"] = "invalid_token"
                return jsonify({"error": "Invalid token"}), 403

            username = parts[1]
            user = valid_users.get(username)
            if not user or user["role"] != "admin":
                g.log_entry.extra["auth_result"] = "insufficient_permissions"
                g.log_entry.extra["attempted_username"] = username
                return jsonify({"error": "Admin access required"}), 403

            g.log_entry.user = username
            g.log_entry.extra["auth_result"] = "success"
            return func(*args, **kwargs)

        return wrapper

    return decorator


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(AppConfig)

    logger = setup_logging(app.config.get("LOG_FILE", LOG_FILE), LOG_LEVEL)
    valid_users = get_demo_users()

    metrics = PrometheusMetrics(app, path="/metrics")
    metrics.info(
        "logmonitor_build_info",
        "Build metadata for the Flask service",
        version=APP_VERSION,
        environment=app.config["ENV"],
    )

    init_security_headers(app)
    add_cache_headers(app)
    init_limiter(app)

    @app.before_request
    def before_request() -> None:
        g.start_time = time.perf_counter()
        g.request_id = str(uuid.uuid4())

        if request.path == "/metrics":
            refresh_monitoring_metrics()

        body: dict[str, Any] = {}
        if request.is_json and request.content_length:
            try:
                body = request.get_json(silent=True) or {}
                if "password" in body:
                    body = {**body, "password": "*" * 12}
            except Exception:
                body = {}

        g.log_entry = LogEntry(
            request_id=g.request_id,
            ip=_get_real_ip(),
            method=request.method,
            endpoint=request.path,
            user_agent=request.headers.get("User-Agent", "unknown"),
            request_body=body,
            query_params=dict(request.args),
        )

    @app.after_request
    def after_request(response: Response) -> Response:
        elapsed_ms = (time.perf_counter() - getattr(g, "start_time", time.perf_counter())) * 1000
        if hasattr(g, "log_entry"):
            g.log_entry.status = response.status_code
            g.log_entry.response_time_ms = elapsed_ms
            log_data = g.log_entry.to_dict()
            if response.status_code >= 500:
                logger.error("request_processed", extra=log_data)
            elif response.status_code >= 400:
                logger.warning("request_processed", extra=log_data)
            else:
                logger.info("request_processed", extra=log_data)
        response.headers["X-Request-ID"] = getattr(g, "request_id", str(uuid.uuid4()))
        return response

    @app.route("/", methods=["GET"])
    def index() -> tuple[Response, int]:
        return jsonify({"service": "log-monitor-mlops", "version": APP_VERSION, "status": "ok"}), 200

    @app.route("/health", methods=["GET"])
    def health_check() -> tuple[Response, int]:
        return jsonify({"status": "healthy", "version": APP_VERSION}), 200

    @app.route("/metrics/ml_quality", methods=["POST"])
    def update_ml_quality() -> tuple[Response, int]:
        payload = request.get_json(silent=True) or {}
        ml_f1_score = payload.get("ml_f1_score")
        if ml_f1_score is None:
            return jsonify({"error": "ml_f1_score is required"}), 400
        try:
            ml_f1_score = float(ml_f1_score)
        except (TypeError, ValueError):
            return jsonify({"error": "ml_f1_score must be numeric"}), 400

        saved = persist_runtime_metrics(
            {
                "ml_f1_score": ml_f1_score,
                "model": payload.get("model", "hybrid_ensemble"),
                "dataset": payload.get("dataset", "holdout"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        refresh_monitoring_metrics(force=True)
        return jsonify({"status": "updated", "runtime_metrics": saved}), 200

    @app.route("/login", methods=["POST"])
    @limiter.limit(os.getenv("RATELIMIT_LOGIN", "5 per minute"))
    def login() -> tuple[Response, int]:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        try:
            payload = validate_model(LoginPayload, data)
        except ValidationError as exc:
            return jsonify({"error": "invalid_request", "message": first_validation_error(exc)}), 400

        username = payload.username
        password = payload.password
        user = valid_users.get(username)

        if user and user["password"] == password:
            g.log_entry.user = username
            g.log_entry.extra["login_result"] = "success"
            g.log_entry.extra["user_role"] = user["role"]
            token = f"token_{username}_{int(time.time())}"
            return jsonify({"token": token, "role": user["role"], "message": "Login successful"}), 200

        g.log_entry.extra["login_result"] = "failed"
        g.log_entry.extra["attempted_username"] = username
        return jsonify({"error": "Invalid credentials"}), 401

    @app.route("/api/data", methods=["GET"])
    def get_data() -> tuple[Response, int]:
        try:
            params = validate_model(PaginationQuery, request.args.to_dict())
        except ValidationError as exc:
            return jsonify({"error": "invalid_request", "message": first_validation_error(exc)}), 400

        page = params.page
        per_page = params.per_page
        start = (page - 1) * per_page
        end = start + per_page
        items = SAMPLE_DATA[start:end]

        return jsonify(
            {
                "data": items,
                "page": page,
                "per_page": per_page,
                "total": len(SAMPLE_DATA),
                "pages": (len(SAMPLE_DATA) + per_page - 1) // per_page,
            }
        ), 200

    @app.route("/api/users", methods=["GET"])
    def get_users() -> tuple[Response, int]:
        return jsonify({"users": SAMPLE_USERS, "total": len(SAMPLE_USERS)}), 200

    @app.route("/admin", methods=["GET"])
    @limiter.limit(os.getenv("RATELIMIT_ADMIN", "20 per minute"))
    @require_admin(valid_users)
    def admin_panel() -> tuple[Response, int]:
        return jsonify(
            {
                "message": "Welcome to admin panel",
                "system_info": {
                    "users_count": len(valid_users),
                    "data_count": len(SAMPLE_DATA),
                    "version": APP_VERSION,
                },
            }
        ), 200

    @app.route("/search", methods=["GET"])
    @limiter.limit(os.getenv("RATELIMIT_SEARCH", "30 per minute"))
    def search() -> tuple[Response, int]:
        try:
            params = validate_model(SearchQuery, {"q": request.args.get("q", "")})
        except ValidationError as exc:
            return jsonify({"error": "invalid_request", "message": first_validation_error(exc)}), 400

        query = params.q
        g.log_entry.extra["search_query"] = query
        g.log_entry.extra["query_length"] = len(query)

        results = [item for item in SAMPLE_DATA if query.lower() in str(item.get("value", "")).lower()]
        return jsonify({"query": query, "results": results, "count": len(results)}), 200

    @app.route("/api/upload", methods=["POST"])
    @limiter.limit(os.getenv("RATELIMIT_UPLOAD", "10 per minute"))
    def upload() -> tuple[Response, int]:
        content_length = request.content_length or 0
        g.log_entry.extra["content_length_bytes"] = content_length

        if content_length > app.config["MAX_CONTENT_LENGTH"]:
            return jsonify({"error": "Payload too large"}), 413

        uploaded_file = request.files.get("file")
        if uploaded_file and uploaded_file.filename:
            try:
                filename = validate_upload_filename(
                    uploaded_file.filename,
                    allowed_extensions=app.config["ALLOWED_UPLOAD_EXTENSIONS"],
                )
            except (ValidationError, ValueError) as exc:
                return jsonify({"error": "invalid_request", "message": str(exc)}), 400
            g.log_entry.extra["uploaded_filename"] = filename
            return jsonify({"message": "Upload received", "bytes_received": content_length, "filename": filename}), 200

        return jsonify({"message": "Upload received", "bytes_received": content_length}), 200

    @app.errorhandler(404)
    def not_found(error: Exception) -> tuple[Response, int]:
        if hasattr(g, "log_entry"):
            g.log_entry.extra["error_type"] = "not_found"
        return jsonify({"error": "Endpoint not found", "path": request.path}), 404

    @app.errorhandler(405)
    def method_not_allowed(error: Exception) -> tuple[Response, int]:
        return jsonify({"error": "Method not allowed", "method": request.method, "path": request.path}), 405

    @app.errorhandler(413)
    def payload_too_large(error: Exception) -> tuple[Response, int]:
        return jsonify({"error": "Payload too large"}), 413

    @app.errorhandler(500)
    def internal_error(error: Exception) -> tuple[Response, int]:
        logger.exception("Unhandled internal server error")
        return jsonify({"error": "Internal server error"}), 500

    return app


def _get_real_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.remote_addr or "unknown"


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("FLASK_PORT", "5001"))
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug)
