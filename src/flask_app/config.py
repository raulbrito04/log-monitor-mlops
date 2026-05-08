from __future__ import annotations

import logging
import os
import secrets

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_env() -> str:
    return os.getenv("LOGMONITOR_ENV", "development").strip().lower() or "development"


def is_development() -> bool:
    return get_env() == "development"


def is_test() -> bool:
    return get_env() == "test"


def is_production() -> bool:
    return get_env() == "production"


def get_secret_key() -> str:
    key = os.getenv("FLASK_SECRET_KEY", "").strip()

    if key:
        if len(key) < 32:
            raise ValueError(
                "FLASK_SECRET_KEY demasiado curta (minimo 32 caracteres). "
                "Gera uma com: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return key

    if is_production():
        raise EnvironmentError(
            "FLASK_SECRET_KEY e obrigatoria em producao. Define-a antes de arrancar."
        )

    logger.warning(
        "FLASK_SECRET_KEY nao definida - a usar chave efemera. "
        "Nao usar este comportamento em producao."
    )
    return secrets.token_hex(32)


def _load_demo_user(username_var: str, password_var: str, role: str) -> dict[str, dict[str, str]]:
    username = os.getenv(username_var, "").strip()
    password = os.getenv(password_var, "").strip()
    if not username or not password:
        return {}
    return {username: {"password": password, "role": role}}


def get_demo_users() -> dict[str, dict[str, str]]:
    if is_production():
        return {}

    users: dict[str, dict[str, str]] = {}
    for username_var, password_var, role in [
        ("DEMO_ADMIN_USER", "DEMO_ADMIN_PASS", "admin"),
        ("DEMO_USER1_USER", "DEMO_USER1_PASS", "user"),
        ("DEMO_USER2_USER", "DEMO_USER2_PASS", "user"),
        ("DEMO_ANALYST_USER", "DEMO_ANALYST_PASS", "analyst"),
    ]:
        users.update(_load_demo_user(username_var, password_var, role))
    return users


class AppConfig:
    SECRET_KEY = get_secret_key()
    ENV = get_env()
    DEBUG = is_development()
    TESTING = is_test()
    JSON_SORT_KEYS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = is_production()
    PERMANENT_SESSION_LIFETIME = 3600
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "5")) * 1024 * 1024
    ALLOWED_UPLOAD_EXTENSIONS = {"json", "log", "csv"}
    RATELIMIT_STORAGE_URI = os.getenv("REDIS_URL", "memory://")
    RATELIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "200 per hour")