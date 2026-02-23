"""
tests/test_flask_app.py
-----------------------
Testes unitários e de integração para a aplicação Flask.

Cobre:
- Todos os endpoints e seus casos de sucesso
- Casos de erro e edge cases
- Middleware de logging
- Error handlers

Boas práticas:
- Fixtures reutilizáveis com pytest
- Testes nomeados de forma descritiva
- Separação clara entre arrange/act/assert
- Sem dependências externas (usa test client do Flask)
"""

from __future__ import annotations

import json
import pytest

from src.flask_app.app import create_app, VALID_USERS


# ─── FIXTURES ────────────────────────────────────────────────────────────────


@pytest.fixture
def app():
    """Cria instância da app configurada para testes.

    Yields:
        Aplicação Flask em modo testing.
    """
    app = create_app()
    app.config.update({
        "TESTING": True,
        "LOG_FILE": "/tmp/test_app.log",
    })
    yield app


@pytest.fixture
def client(app):
    """Cria test client da aplicação.

    Args:
        app: Fixture da aplicação.

    Yields:
        Flask test client.
    """
    with app.test_client() as client:
        yield client


@pytest.fixture
def admin_token(client):
    """Autentica como admin e devolve token.

    Args:
        client: Flask test client.

    Returns:
        Token de autenticação de admin.
    """
    response = client.post(
        "/login",
        json={"username": "admin", "password": "admin123"},
    )
    return response.get_json()["token"]


# ─── TESTES: HEALTH CHECK ─────────────────────────────────────────────────────


class TestHealthCheck:
    """Testes para o endpoint de health check."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_json(self, client):
        response = client.get("/health")
        data = response.get_json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_health_has_request_id_header(self, client):
        response = client.get("/health")
        assert "X-Request-ID" in response.headers


# ─── TESTES: LOGIN ───────────────────────────────────────────────────────────


class TestLogin:
    """Testes para o endpoint de autenticação /login."""

    def test_valid_admin_login_returns_200(self, client):
        response = client.post(
            "/login",
            json={"username": "admin", "password": "admin123"},
        )
        assert response.status_code == 200

    def test_valid_login_returns_token(self, client):
        response = client.post(
            "/login",
            json={"username": "user1", "password": "password1"},
        )
        data = response.get_json()
        assert "token" in data
        assert "role" in data

    def test_invalid_password_returns_401(self, client):
        response = client.post(
            "/login",
            json={"username": "admin", "password": "wrongpassword"},
        )
        assert response.status_code == 401

    def test_nonexistent_user_returns_401(self, client):
        response = client.post(
            "/login",
            json={"username": "nonexistent", "password": "anything"},
        )
        assert response.status_code == 401

    def test_missing_password_returns_400(self, client):
        response = client.post(
            "/login",
            json={"username": "admin"},
        )
        assert response.status_code == 400

    def test_missing_username_returns_400(self, client):
        response = client.post(
            "/login",
            json={"password": "admin123"},
        )
        assert response.status_code == 400

    def test_empty_body_returns_400(self, client):
        response = client.post(
            "/login",
            data="not json",
            content_type="text/plain",
        )
        assert response.status_code == 400

    def test_all_valid_users_can_login(self, client):
        """Verificar que todos os utilizadores válidos conseguem autenticar."""
        credentials = {
            "admin": "admin123",
            "user1": "password1",
            "user2": "password2",
            "analyst": "analyst99",
        }
        for username, password in credentials.items():
            response = client.post(
                "/login",
                json={"username": username, "password": password},
            )
            assert response.status_code == 200, (
                f"Login failed for {username}"
            )


# ─── TESTES: API DATA ─────────────────────────────────────────────────────────


class TestApiData:
    """Testes para o endpoint /api/data."""

    def test_returns_200(self, client):
        response = client.get("/api/data")
        assert response.status_code == 200

    def test_returns_data_list(self, client):
        response = client.get("/api/data")
        data = response.get_json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_default_pagination(self, client):
        response = client.get("/api/data")
        data = response.get_json()
        assert data["page"] == 1
        assert data["per_page"] == 10
        assert len(data["data"]) == 10

    def test_custom_pagination(self, client):
        response = client.get("/api/data?page=2&per_page=5")
        data = response.get_json()
        assert data["page"] == 2
        assert data["per_page"] == 5
        assert len(data["data"]) == 5

    def test_invalid_page_returns_400(self, client):
        response = client.get("/api/data?page=abc")
        assert response.status_code == 400

    def test_per_page_capped_at_20(self, client):
        response = client.get("/api/data?per_page=100")
        data = response.get_json()
        assert data["per_page"] <= 20

    def test_returns_total_count(self, client):
        response = client.get("/api/data")
        data = response.get_json()
        assert "total" in data
        assert data["total"] > 0


# ─── TESTES: API USERS ────────────────────────────────────────────────────────


class TestApiUsers:
    """Testes para o endpoint /api/users."""

    def test_returns_200(self, client):
        response = client.get("/api/users")
        assert response.status_code == 200

    def test_returns_users_list(self, client):
        response = client.get("/api/users")
        data = response.get_json()
        assert "users" in data
        assert isinstance(data["users"], list)
        assert len(data["users"]) > 0

    def test_users_have_required_fields(self, client):
        response = client.get("/api/users")
        users = response.get_json()["users"]
        for user in users:
            assert "id" in user
            assert "username" in user
            assert "email" in user


# ─── TESTES: ADMIN ────────────────────────────────────────────────────────────


class TestAdminPanel:
    """Testes para o endpoint /admin."""

    def test_without_token_returns_401(self, client):
        response = client.get("/admin")
        assert response.status_code == 401

    def test_with_invalid_token_returns_403(self, client):
        response = client.get(
            "/admin",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == 403

    def test_with_admin_token_returns_200(self, client, admin_token):
        response = client.get(
            "/admin",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200

    def test_admin_response_has_system_info(self, client, admin_token):
        response = client.get(
            "/admin",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        data = response.get_json()
        assert "system_info" in data

    def test_non_admin_user_returns_403(self, client):
        """Utilizador com role 'user' não deve aceder ao admin."""
        # Autenticar como user1 (role=user)
        login_response = client.post(
            "/login",
            json={"username": "user1", "password": "password1"},
        )
        token = login_response.get_json()["token"]

        response = client.get(
            "/admin",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ─── TESTES: SEARCH ──────────────────────────────────────────────────────────


class TestSearch:
    """Testes para o endpoint /search."""

    def test_valid_query_returns_200(self, client):
        response = client.get("/search?q=data")
        assert response.status_code == 200

    def test_returns_results_and_count(self, client):
        response = client.get("/search?q=data")
        data = response.get_json()
        assert "results" in data
        assert "count" in data
        assert "query" in data

    def test_missing_query_returns_400(self, client):
        response = client.get("/search")
        assert response.status_code == 400

    def test_sql_injection_payload_does_not_crash(self, client):
        """A app não deve crashar com payloads de SQLi.

        Importante: a app recebe e loga o payload, mas não o executa.
        O objetivo é gerar logs para o pipeline detetar.
        """
        sqli_payloads = [
            "' OR 1=1 --",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
        ]
        for payload in sqli_payloads:
            response = client.get(f"/search?q={payload}")
            # Deve retornar 200 (app não crashou) ou 400 (validação)
            assert response.status_code in (200, 400), (
                f"App crashed with payload: {payload!r}"
            )


# ─── TESTES: ERROR HANDLERS ──────────────────────────────────────────────────


class TestErrorHandlers:
    """Testes para os error handlers globais."""

    def test_unknown_endpoint_returns_404(self, client):
        response = client.get("/this/endpoint/does/not/exist")
        assert response.status_code == 404

    def test_404_response_is_json(self, client):
        response = client.get("/nonexistent")
        data = response.get_json()
        assert "error" in data

    def test_wrong_method_returns_405(self, client):
        response = client.delete("/health")
        assert response.status_code == 405


# ─── TESTES: MIDDLEWARE ──────────────────────────────────────────────────────


class TestMiddleware:
    """Testes para o middleware de logging."""

    def test_all_responses_have_request_id(self, client):
        """Todos os responses devem ter X-Request-ID header."""
        endpoints = ["/health", "/api/data", "/api/users", "/nonexistent"]
        for endpoint in endpoints:
            response = client.get(endpoint)
            assert "X-Request-ID" in response.headers, (
                f"Missing X-Request-ID for {endpoint}"
            )

    def test_request_ids_are_unique(self, client):
        """Cada request deve ter um ID único."""
        ids = set()
        for _ in range(10):
            response = client.get("/health")
            request_id = response.headers.get("X-Request-ID")
            assert request_id not in ids, "Duplicate request ID detected"
            ids.add(request_id)
