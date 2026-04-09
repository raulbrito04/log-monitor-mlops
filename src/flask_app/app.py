"""
src/flask_app/app.py
--------------------
Aplicação Flask sintética para geração de logs HTTP realistas.

Simula uma aplicação web com autenticação, API endpoints, e rotas
administrativas. Todos os requests são logados em formato JSON estruturado
para posterior análise pelo pipeline de deteção de anomalias.

Boas práticas aplicadas:
- Type hints em todas as funções (PEP 484)
- Docstrings no formato Google Style (PEP 257)
- Single Responsibility: cada rota faz uma coisa
- Constantes com UPPER_CASE (PEP 8)
- Error handling explícito com respostas consistentes
- Logging estruturado via middleware (não repetido em cada rota)
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any

from flask import Flask, Response, g, jsonify, request
from prometheus_flask_exporter import PrometheusMetrics
from pythonjsonlogger import jsonlogger
from src.monitoring.metrics import persist_runtime_metrics, refresh_monitoring_metrics

# ─── CONSTANTES ─────────────────────────────────────────────────────────────

LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
SECRET_KEY: str = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod")
APP_VERSION: str = "1.0.0"

# Utilizadores válidos simulados (em produção: base de dados)
# Estrutura: {username: {"password": str, "role": str}}
VALID_USERS: dict[str, dict[str, str]] = {
    "admin": {"password": "admin123", "role": "admin"},
    "user1": {"password": "password1", "role": "user"},
    "user2": {"password": "password2", "role": "user"},
    "analyst": {"password": "analyst99", "role": "analyst"},
}

# Dados fictícios para endpoints de API
SAMPLE_DATA: list[dict[str, Any]] = [
    {"id": i, "value": f"data_item_{i}", "category": ["A", "B", "C"][i % 3]}
    for i in range(1, 51)
]

SAMPLE_USERS: list[dict[str, str | int]] = [
    {"id": i, "username": f"user{i}", "email": f"user{i}@example.com", "role": "user"}
    for i in range(1, 21)
]


# ─── DATACLASSES ────────────────────────────────────────────────────────────


@dataclass
class LogEntry:
    """Representa uma entrada de log estruturada.

    Todos os campos têm valores por defeito para facilitar
    construção incremental durante o processamento do request.

    Attributes:
        request_id: Identificador único do request (UUID4).
        timestamp: Timestamp ISO 8601 com timezone UTC.
        ip: Endereço IP do cliente.
        method: Método HTTP (GET, POST, etc).
        endpoint: Path do endpoint acedido.
        status: HTTP status code da resposta.
        response_time_ms: Latência em milissegundos.
        user_agent: User-Agent do cliente.
        request_body: Body do request (se existir).
        query_params: Query parameters do request.
        user: Username autenticado (se aplicável).
        extra: Campos adicionais contextuais.
    """

    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
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
        """Serializa o LogEntry para dicionário.

        Returns:
            Dicionário com todos os campos não-None.
        """
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


# ─── LOGGING SETUP ──────────────────────────────────────────────────────────


def setup_logging(log_file: str = LOG_FILE, level: str = LOG_LEVEL) -> logging.Logger:
    """Configura logging estruturado em formato JSON.

    Cria dois handlers:
    - StreamHandler: output para stdout (útil para Docker logs)
    - FileHandler: output para ficheiro (persistência)

    Ambos usam formato JSON com campos timestamp, level, message, e extras.

    Args:
        log_file: Caminho para o ficheiro de log.
        level: Nível de logging (DEBUG, INFO, WARNING, ERROR).

    Returns:
        Logger configurado pronto a usar.

    Example:
        >>> logger = setup_logging("logs/app.log", "INFO")
        >>> logger.info("Server started", extra={"port": 5000})
    """
    # Garantir que diretório existe
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger("flask_app")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Formato JSON com campos úteis para análise
    json_formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )

    # Handler para stdout (Docker friendly)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(json_formatter)

    # Handler para ficheiro
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(json_formatter)

    # Evitar duplicação de handlers em hot-reload do Flask
    if not logger.handlers:
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

    return logger


# ─── FACTORY DA APLICAÇÃO ───────────────────────────────────────────────────


def create_app() -> Flask:
    """Factory function para criar e configurar a aplicação Flask.

    Usa o padrão Application Factory para facilitar testes e
    múltiplas instâncias com configurações diferentes.

    Returns:
        Aplicação Flask configurada com todas as rotas e middleware.

    Example:
        >>> app = create_app()
        >>> app.run(debug=True)
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["JSON_SORT_KEYS"] = False

    logger = setup_logging()
    metrics = PrometheusMetrics(app, path="/metrics")
    metrics.info(
        "logmonitor_build_info",
        "Build metadata for the Flask service",
        version=APP_VERSION,
        environment=os.getenv("LOGMONITOR_ENV", "development"),
    )

    # ── MIDDLEWARE: LOGGING DE TODOS OS REQUESTS ─────────────────────────────
    # Usar before_request e after_request para centralizar logging
    # em vez de repetir em cada rota (DRY principle)

    @app.before_request
    def before_request() -> None:
        """Inicializa contexto do request antes do processamento.

        Guarda o timestamp de início em flask.g para calcular
        latência no after_request. Cria LogEntry parcial com
        dados disponíveis antes da resposta.
        """
        g.start_time = time.perf_counter()
        g.request_id = str(uuid.uuid4())

        if request.path == "/metrics":
            refresh_monitoring_metrics()

        # Capturar body de forma segura (pode ser JSON ou form data)
        body: dict[str, Any] = {}
        if request.is_json and request.content_length:
            try:
                body = request.get_json(silent=True) or {}
                # Nunca logar passwords em texto limpo
                if "password" in body:
                    body = {**body, "password": "***REDACTED***"}
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
        """Completa e persiste o log entry após cada request.

        Calcula latência, adiciona status code e escreve log.
        Separação clara entre logging e lógica de negócio.

        Args:
            response: Objeto Response do Flask.

        Returns:
            Response inalterado (middleware transparente).
        """
        elapsed_ms = (time.perf_counter() - g.start_time) * 1000

        g.log_entry.status = response.status_code
        g.log_entry.response_time_ms = elapsed_ms

        log_data = g.log_entry.to_dict()

        # Escolher nível de log baseado no status code
        if response.status_code >= 500:
            logger.error("request_processed", extra=log_data)
        elif response.status_code >= 400:
            logger.warning("request_processed", extra=log_data)
        else:
            logger.info("request_processed", extra=log_data)

        # Adicionar request ID à resposta para rastreabilidade
        response.headers["X-Request-ID"] = g.request_id
        return response

    # ── ROTAS ────────────────────────────────────────────────────────────────

    @app.route("/health", methods=["GET"])
    def health_check() -> tuple[Response, int]:
        """Endpoint de health check para Docker/Kubernetes.

        Returns:
            JSON com status e versão da aplicação.
        """
        return jsonify({"status": "healthy", "version": APP_VERSION}), 200

    @app.route("/metrics/ml_quality", methods=["POST"])
    def update_ml_quality() -> tuple[Response, int]:
        """Atualiza a metrica operacional de F1 usada no monitoring."""
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
    def login() -> tuple[Response, int]:
        """Simula autenticação com username/password.

        Aceita JSON body com campos 'username' e 'password'.
        Regista tentativas falhadas no log para deteção de brute force.

        Returns:
            200 + token se credenciais válidas.
            400 se body inválido ou campos em falta.
            401 se credenciais incorretas.

        Example request body:
            {"username": "admin", "password": "admin123"}
        """
        data = request.get_json(silent=True)

        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        username = data.get("username", "").strip()
        password = data.get("password", "")

        if not username or not password:
            return jsonify({"error": "username and password are required"}), 400

        user = VALID_USERS.get(username)

        if user and user["password"] == password:
            # Login bem-sucedido
            g.log_entry.user = username
            g.log_entry.extra["login_result"] = "success"
            g.log_entry.extra["user_role"] = user["role"]

            # Token simulado (em produção: JWT real)
            token = f"token_{username}_{int(time.time())}"
            return jsonify({
                "token": token,
                "role": user["role"],
                "message": "Login successful",
            }), 200

        # Login falhado — log extra para deteção de brute force
        g.log_entry.extra["login_result"] = "failed"
        g.log_entry.extra["attempted_username"] = username
        return jsonify({"error": "Invalid credentials"}), 401

    @app.route("/api/data", methods=["GET"])
    def get_data() -> tuple[Response, int]:
        """Devolve lista de dados fictícios com suporte a paginação.

        Query params:
            page (int): Número da página (default: 1).
            per_page (int): Items por página, max 20 (default: 10).

        Returns:
            JSON com lista de items e metadata de paginação.
        """
        try:
            page = max(1, int(request.args.get("page", 1)))
            per_page = min(20, max(1, int(request.args.get("per_page", 10))))
        except ValueError:
            return jsonify({"error": "page and per_page must be integers"}), 400

        start = (page - 1) * per_page
        end = start + per_page
        items = SAMPLE_DATA[start:end]

        return jsonify({
            "data": items,
            "page": page,
            "per_page": per_page,
            "total": len(SAMPLE_DATA),
            "pages": (len(SAMPLE_DATA) + per_page - 1) // per_page,
        }), 200

    @app.route("/api/users", methods=["GET"])
    def get_users() -> tuple[Response, int]:
        """Lista utilizadores simulados.

        Em produção requereria autenticação. Aqui é deixado aberto
        propositadamente para simular endpoint mal configurado.

        Returns:
            JSON com lista de utilizadores (sem passwords).
        """
        return jsonify({
            "users": SAMPLE_USERS,
            "total": len(SAMPLE_USERS),
        }), 200

    @app.route("/admin", methods=["GET"])
    def admin_panel() -> tuple[Response, int]:
        """Painel administrativo protegido por token.

        Verifica header Authorization: Bearer <token>.
        Simula acesso a endpoint sensível que deve ser monitorizado.

        Headers:
            Authorization: Bearer <token>

        Returns:
            200 com dados admin se autorizado.
            401 se token ausente.
            403 se token inválido ou utilizador sem role admin.
        """
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            g.log_entry.extra["auth_result"] = "missing_token"
            return jsonify({"error": "Authorization header required"}), 401

        token = auth_header.replace("Bearer ", "")

        # Validação de token simulada
        # token format: "token_{username}_{timestamp}"
        parts = token.split("_")
        if len(parts) != 3 or parts[0] != "token":
            g.log_entry.extra["auth_result"] = "invalid_token"
            return jsonify({"error": "Invalid token"}), 403

        username = parts[1]
        user = VALID_USERS.get(username)

        if not user or user["role"] != "admin":
            g.log_entry.extra["auth_result"] = "insufficient_permissions"
            g.log_entry.extra["attempted_username"] = username
            return jsonify({"error": "Admin access required"}), 403

        g.log_entry.user = username
        g.log_entry.extra["auth_result"] = "success"

        return jsonify({
            "message": "Welcome to admin panel",
            "system_info": {
                "users_count": len(VALID_USERS),
                "data_count": len(SAMPLE_DATA),
                "version": APP_VERSION,
            },
        }), 200

    @app.route("/search", methods=["GET"])
    def search() -> tuple[Response, int]:
        """Endpoint de pesquisa intencionalmente vulnerável a SQLi para testes.

        Aceita query param ?q= e devolve resultados filtrados.
        Regista o query param no log para deteção de injection patterns
        pela camada de regras do pipeline.

        Query params:
            q (str): Termo de pesquisa.

        Returns:
            JSON com resultados da pesquisa.
            400 se q ausente.
        """
        query = request.args.get("q", "").strip()

        if not query:
            return jsonify({"error": "Query parameter 'q' is required"}), 400

        # Registar o query para análise de SQLi
        g.log_entry.extra["search_query"] = query
        g.log_entry.extra["query_length"] = len(query)

        # Filtro simples simulado (sem SQLi real — é só para gerar logs)
        results = [
            item for item in SAMPLE_DATA
            if query.lower() in str(item.get("value", "")).lower()
        ]

        return jsonify({
            "query": query,
            "results": results,
            "count": len(results),
        }), 200

    @app.route("/api/upload", methods=["POST"])
    def upload() -> tuple[Response, int]:
        """Endpoint de upload simulado.

        Gera padrões de log para análise de requests grandes
        e potenciais ataques de upload malicioso.

        Returns:
            200 com confirmação de upload simulado.
        """
        content_length = request.content_length or 0
        g.log_entry.extra["content_length_bytes"] = content_length

        return jsonify({
            "message": "Upload received",
            "bytes_received": content_length,
        }), 200

    # ── ERROR HANDLERS ───────────────────────────────────────────────────────
    # Respostas de erro consistentes em JSON para todo o lado

    @app.errorhandler(404)
    def not_found(error: Exception) -> tuple[Response, int]:
        """Handler para endpoints não encontrados.

        Estes logs são importantes para deteção de scanning.
        O middleware já regista o IP e endpoint tentado.
        """
        g.log_entry.extra["error_type"] = "not_found"
        return jsonify({"error": "Endpoint not found", "path": request.path}), 404

    @app.errorhandler(405)
    def method_not_allowed(error: Exception) -> tuple[Response, int]:
        """Handler para métodos HTTP não permitidos."""
        return jsonify({
            "error": "Method not allowed",
            "method": request.method,
            "path": request.path,
        }), 405

    @app.errorhandler(500)
    def internal_error(error: Exception) -> tuple[Response, int]:
        """Handler para erros internos não esperados."""
        logger.exception("Unhandled internal server error")
        return jsonify({"error": "Internal server error"}), 500

    return app


# ─── HELPERS PRIVADOS ────────────────────────────────────────────────────────


def _get_real_ip() -> str:
    """Extrai o IP real do cliente considerando proxies.

    Verifica headers X-Forwarded-For e X-Real-IP antes
    de usar request.remote_addr como fallback.

    Returns:
        String com endereço IP do cliente.
    """
    # X-Forwarded-For pode conter lista de IPs separados por vírgula
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    return request.remote_addr or "unknown"


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("FLASK_PORT", "5001"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
    )


