"""
src/flask_app/traffic_generator.py
------------------------------------
Gerador de tráfego sintético para a aplicação Flask.

Gera diferentes padrões de requests HTTP para simular tráfego
real e ataques, permitindo testar o pipeline de deteção de anomalias.

Modos disponíveis:
- normal: Utilizadores legítimos a navegar aleatoriamente
- attack: Padrões de ataque específicos

Tipos de ataque:
- brute_force: Muitos POSTs /login com credenciais erradas
- scanning: Tentativas de acesso a endpoints inexistentes
- sql_injection: Payloads SQLi no endpoint /search
- rate_abuse: Volume anómalo de requests de um IP
- mixed: Combinação aleatória de todos os ataques

Boas práticas aplicadas:
- Dataclasses para configuração tipada
- Enum para tipos de modo/ataque (evita magic strings)
- Context managers para sessões HTTP
- Logging de progresso do próprio gerador
- Separação clara entre configuração e execução
- Funções pequenas e focadas (Single Responsibility)

Uso:
    python traffic_generator.py --mode normal --duration 60
    python traffic_generator.py --mode attack --type brute_force --target-ip 10.0.0.1
    python traffic_generator.py --mode attack --type mixed --num-requests 500
    python traffic_generator.py --mode attack --type sql_injection --num-requests 50
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator

import requests
from faker import Faker

# ─── CONSTANTES ──────────────────────────────────────────────────────────────

BASE_URL: str = os.getenv("TARGET_URL", "http://localhost:5001")
REQUEST_TIMEOUT: int = 5  # segundos
DEFAULT_DELAY_NORMAL: float = 0.5  # segundos entre requests normais
DEFAULT_DELAY_ATTACK: float = 0.05  # segundos entre requests de ataque

# User agents reais para simular browsers
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
    "Mozilla/5.0 (Android 14; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
    "python-requests/2.31.0",  # Scripts/bots legítimos
    "curl/8.4.0",
]

# Payloads comuns de SQL injection para teste
SQL_INJECTION_PAYLOADS: list[str] = [
    "' OR 1=1 --",
    "' OR '1'='1",
    "'; DROP TABLE users; --",
    "' UNION SELECT * FROM users --",
    "admin'--",
    "' OR 1=1#",
    "1; SELECT * FROM information_schema.tables",
    "' AND 1=0 UNION ALL SELECT NULL, NULL --",
    "' WAITFOR DELAY '0:0:5' --",
    "1 OR 1=1",
    "' OR 'x'='x",
    "105 OR 1=1",
    "' OR ''='",
    ") OR ('1'='1",
    "' OR 1=1 LIMIT 1 --",
]

# Endpoints para scanning (a maioria não existe)
SCAN_TARGETS: list[str] = [
    "/admin/config", "/.env", "/wp-admin", "/phpmyadmin",
    "/config.php", "/.git/config", "/backup.zip", "/admin.php",
    "/api/v1/users", "/api/v2/users", "/actuator/health",
    "/swagger.json", "/.htaccess", "/server-status",
    "/api/token", "/oauth/token", "/reset-password",
    "/debug", "/console", "/shell", "/exec",
    "/etc/passwd", "/proc/self/environ", "/api/admin",
    "/api/config", "/api/secrets", "/api/keys",
]

# Credenciais comuns para brute force
BRUTE_FORCE_CREDENTIALS: list[tuple[str, str]] = [
    ("admin", "admin"),
    ("admin", "password"),
    ("admin", "123456"),
    ("admin", "admin123"),
    ("root", "root"),
    ("root", "toor"),
    ("administrator", "admin"),
    ("admin", ""),
    ("test", "test"),
    ("user", "user"),
    ("admin", "pass"),
    ("admin", "qwerty"),
    ("admin", "letmein"),
    ("admin", "welcome"),
    ("admin", "monkey"),
]

# Endpoints normais da aplicação
NORMAL_ENDPOINTS: list[tuple[str, str]] = [
    ("GET", "/api/data"),
    ("GET", "/api/data?page=1&per_page=10"),
    ("GET", "/api/data?page=2"),
    ("GET", "/api/users"),
    ("GET", "/health"),
    ("GET", "/search?q=data"),
    ("GET", "/search?q=item"),
    ("POST", "/login"),  # Logins bem-sucedidos
]


# ─── ENUMS ───────────────────────────────────────────────────────────────────


class TrafficMode(Enum):
    """Modo de geração de tráfego."""
    NORMAL = auto()
    ATTACK = auto()


class AttackType(Enum):
    """Tipo de ataque a simular."""
    BRUTE_FORCE = "brute_force"
    SCANNING = "scanning"
    SQL_INJECTION = "sql_injection"
    RATE_ABUSE = "rate_abuse"
    MIXED = "mixed"


# ─── CONFIGURAÇÃO ────────────────────────────────────────────────────────────


@dataclass
class GeneratorConfig:
    """Configuração do gerador de tráfego.

    Attributes:
        mode: Modo de operação (normal ou attack).
        attack_type: Tipo de ataque (se mode=attack).
        duration_seconds: Duração em segundos (0 = infinito até num_requests).
        num_requests: Número total de requests (0 = baseado em duration).
        target_ip: IP do atacante (gerado aleatoriamente se não fornecido).
        base_url: URL base da aplicação alvo.
        delay: Pausa entre requests em segundos.
        verbose: Ativar output detalhado.
    """

    mode: TrafficMode = TrafficMode.NORMAL
    attack_type: AttackType = AttackType.MIXED
    duration_seconds: int = 60
    num_requests: int = 0
    target_ip: str = field(default_factory=lambda: _generate_attacker_ip())
    base_url: str = BASE_URL
    delay: float = DEFAULT_DELAY_NORMAL
    verbose: bool = False


# ─── LOGGING DO GERADOR ──────────────────────────────────────────────────────


def _setup_generator_logger() -> logging.Logger:
    """Configura logger do gerador com output simples para stdout.

    Returns:
        Logger configurado para output em stdout.
    """
    logger = logging.getLogger("traffic_generator")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


logger = _setup_generator_logger()


# ─── HELPERS ─────────────────────────────────────────────────────────────────


def _generate_attacker_ip() -> str:
    """Gera um IP de atacante aleatório mas consistente por sessão.

    Returns:
        String com endereço IPv4 simulado.
    """
    return f"{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}.{random.randint(1, 254)}"


def _get_random_user_agent() -> str:
    """Seleciona um User-Agent aleatório da lista.

    Returns:
        String com User-Agent.
    """
    return random.choice(USER_AGENTS)


def _get_legitimate_user_agent() -> str:
    """Seleciona um User-Agent de browser legítimo (não scripts).

    Returns:
        String com User-Agent de browser.
    """
    browser_agents = [ua for ua in USER_AGENTS if "Mozilla" in ua]
    return random.choice(browser_agents)


def _make_request(
    session: requests.Session,
    method: str,
    url: str,
    headers: dict | None = None,
    json: dict | None = None,
    params: dict | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> requests.Response | None:
    """Faz um request HTTP com error handling robusto.

    Não levanta exceções — retorna None em caso de falha.
    Garante que o gerador continua mesmo com a app em baixo.

    Args:
        session: Sessão requests reutilizável.
        method: Método HTTP ('GET', 'POST', etc).
        url: URL completo do endpoint.
        headers: Headers HTTP opcionais.
        json: Body JSON opcional.
        params: Query params opcionais.
        timeout: Timeout em segundos.

    Returns:
        Response object ou None se falhar.
    """
    try:
        response = session.request(
            method=method,
            url=url,
            headers=headers or {},
            json=json,
            params=params,
            timeout=timeout,
        )
        return response
    except requests.exceptions.ConnectionError:
        logger.warning(f"Connection refused to {url}. Is the app running?")
        return None
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout on {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        return None


def _count_or_time_iterator(config: GeneratorConfig) -> Iterator[int]:
    """Iterador que controla o loop de geração.

    Itera por num_requests se especificado, ou por duration_seconds.
    Permite controlo flexível sem código duplicado nos geradores.

    Args:
        config: Configuração do gerador.

    Yields:
        Índice do request atual.
    """
    if config.num_requests > 0:
        yield from range(config.num_requests)
    else:
        start = time.time()
        i = 0
        while time.time() - start < config.duration_seconds:
            yield i
            i += 1


# ─── GERADORES DE TRÁFEGO ────────────────────────────────────────────────────


def generate_normal_traffic(config: GeneratorConfig) -> None:
    """Gera tráfego normal simulando utilizadores legítimos.

    Simula múltiplos utilizadores com IPs e User-Agents variados,
    a aceder a diferentes endpoints com padrões realistas.
    Inclui logins bem-sucedidos e falhas ocasionais (5% de taxa de erro).

    Args:
        config: Configuração do gerador.
    """
    fake = Faker()
    stats = {"total": 0, "success": 0, "failed": 0}

    logger.info("Starting NORMAL traffic generation")
    logger.info(f"Target: {config.base_url}")

    with requests.Session() as session:
        for i in _count_or_time_iterator(config):
            # IP diferente para cada "utilizador" (simulação multi-user)
            user_ip = fake.ipv4_private()
            user_agent = _get_legitimate_user_agent()

            headers = {
                "User-Agent": user_agent,
                "X-Forwarded-For": user_ip,
                "X-Real-IP": user_ip,
                "Accept": "application/json",
            }

            # Escolher ação com pesos realistas
            action = random.choices(
                ["browse_data", "list_users", "health", "search", "login", "bad_login"],
                weights=[30, 15, 10, 25, 15, 5],  # 5% login falhado ocasional
                k=1,
            )[0]

            response = None

            if action == "browse_data":
                page = random.randint(1, 5)
                response = _make_request(
                    session, "GET",
                    f"{config.base_url}/api/data",
                    headers=headers,
                    params={"page": page, "per_page": 10},
                )

            elif action == "list_users":
                response = _make_request(
                    session, "GET",
                    f"{config.base_url}/api/users",
                    headers=headers,
                )

            elif action == "health":
                response = _make_request(
                    session, "GET",
                    f"{config.base_url}/health",
                    headers=headers,
                )

            elif action == "search":
                query = random.choice(["data", "item", "category", "value", "test"])
                response = _make_request(
                    session, "GET",
                    f"{config.base_url}/search",
                    headers=headers,
                    params={"q": query},
                )

            elif action == "login":
                # Login bem-sucedido com credenciais válidas
                username = random.choice(["user1", "user2", "analyst"])
                passwords = {"user1": "password1", "user2": "password2", "analyst": "analyst99"}
                response = _make_request(
                    session, "POST",
                    f"{config.base_url}/login",
                    headers=headers,
                    json={"username": username, "password": passwords[username]},
                )

            elif action == "bad_login":
                # Login ocasionalmente falhado (comportamento normal)
                response = _make_request(
                    session, "POST",
                    f"{config.base_url}/login",
                    headers=headers,
                    json={"username": fake.user_name(), "password": fake.password()},
                )

            stats["total"] += 1
            if response and response.status_code < 400:
                stats["success"] += 1
            else:
                stats["failed"] += 1

            if config.verbose and response:
                logger.info(
                    f"[{i+1}] {action.upper()} → {response.status_code} "
                    f"({response.elapsed.total_seconds()*1000:.0f}ms) IP:{user_ip}"
                )

            time.sleep(config.delay)

    logger.info(
        f"Normal traffic complete: {stats['total']} requests, "
        f"{stats['success']} success, {stats['failed']} failed"
    )


def generate_brute_force(config: GeneratorConfig) -> None:
    """Simula ataque de brute force ao endpoint /login.

    Um único IP tenta múltiplas combinações de username/password
    em rápida sucessão, excedendo o threshold da regra de deteção.

    Args:
        config: Configuração com target_ip e delay.
    """
    attacker_ip = config.target_ip
    attempts = 0
    blocked_count = 0

    logger.info(f"Starting BRUTE FORCE attack from IP: {attacker_ip}")

    headers = {
        "User-Agent": "python-requests/2.31.0",  # Tool signature
        "X-Forwarded-For": attacker_ip,
        "X-Real-IP": attacker_ip,
    }

    with requests.Session() as session:
        for i in _count_or_time_iterator(config):
            # Ciclar pelas credenciais comuns
            username, password = BRUTE_FORCE_CREDENTIALS[
                i % len(BRUTE_FORCE_CREDENTIALS)
            ]

            response = _make_request(
                session, "POST",
                f"{config.base_url}/login",
                headers=headers,
                json={"username": username, "password": password},
            )

            attempts += 1

            if response:
                status = response.status_code
                if status == 429:  # Rate limited
                    blocked_count += 1
                    logger.warning(f"Rate limited after {attempts} attempts!")
                    time.sleep(5)  # Esperar antes de continuar

                if config.verbose:
                    result = "SUCCESS" if status == 200 else f"FAIL ({status})"
                    logger.info(
                        f"[{attempts}] {username}:{password} → {result}"
                    )

            time.sleep(config.delay)

    logger.info(
        f"Brute force complete: {attempts} attempts, "
        f"{blocked_count} times rate-limited"
    )


def generate_scanning(config: GeneratorConfig) -> None:
    """Simula scanning de endpoints para descoberta de recursos.

    Um único IP faz requests a endpoints aleatórios, a maioria
    inexistentes, gerando múltiplas respostas 404 rapidamente.

    Args:
        config: Configuração com target_ip e delay.
    """
    attacker_ip = config.target_ip
    found = []
    not_found = 0

    logger.info(f"Starting SCANNING attack from IP: {attacker_ip}")

    headers = {
        "User-Agent": "Nikto/2.1.6",  # Scanner signature
        "X-Forwarded-For": attacker_ip,
        "X-Real-IP": attacker_ip,
    }

    # Combinar endpoints existentes com targets de scanning
    all_targets = SCAN_TARGETS.copy()
    # Adicionar targets aleatórios gerados programaticamente
    all_targets.extend([
        f"/api/v{v}/{resource}"
        for v in range(1, 4)
        for resource in ["config", "secrets", "tokens", "debug", "admin"]
    ])

    with requests.Session() as session:
        for i in _count_or_time_iterator(config):
            # Ciclar pelos targets ou escolher aleatoriamente
            if config.num_requests > 0:
                endpoint = all_targets[i % len(all_targets)]
            else:
                endpoint = random.choice(all_targets)

            response = _make_request(
                session, "GET",
                f"{config.base_url}{endpoint}",
                headers=headers,
            )

            if response:
                if response.status_code != 404:
                    found.append((endpoint, response.status_code))
                    logger.info(f"FOUND: {endpoint} → {response.status_code}")
                else:
                    not_found += 1

                if config.verbose:
                    logger.info(
                        f"[{i+1}] {endpoint} → {response.status_code}"
                    )

            time.sleep(config.delay)

    logger.info(
        f"Scanning complete: {len(found)} endpoints found, "
        f"{not_found} not found (404)"
    )
    if found:
        logger.info(f"Found endpoints: {found}")


def generate_sql_injection(config: GeneratorConfig) -> None:
    """Simula tentativas de SQL injection no endpoint /search.

    Envia payloads comuns de SQL injection como query parameter,
    que serão detetados pela regra de regex do pipeline.

    Args:
        config: Configuração com target_ip e delay.
    """
    attacker_ip = config.target_ip
    attempts = 0

    logger.info(f"Starting SQL INJECTION attack from IP: {attacker_ip}")

    headers = {
        "User-Agent": "sqlmap/1.7.8#stable",  # SQLMap signature
        "X-Forwarded-For": attacker_ip,
        "X-Real-IP": attacker_ip,
    }

    with requests.Session() as session:
        for i in _count_or_time_iterator(config):
            payload = SQL_INJECTION_PAYLOADS[i % len(SQL_INJECTION_PAYLOADS)]

            response = _make_request(
                session, "GET",
                f"{config.base_url}/search",
                headers=headers,
                params={"q": payload},
            )

            attempts += 1

            if config.verbose and response:
                logger.info(
                    f"[{attempts}] Payload: {payload!r} → {response.status_code}"
                )

            time.sleep(config.delay)

    logger.info(f"SQL injection complete: {attempts} payloads sent")


def generate_rate_abuse(config: GeneratorConfig) -> None:
    """Simula abuso de rate limiting com volume anómalo de requests.

    Um único IP envia centenas de requests em poucos segundos,
    excedendo em muito o threshold normal de utilizador.

    Args:
        config: Configuração com target_ip e delay muito baixo.
    """
    attacker_ip = config.target_ip
    total = 0
    start_time = time.time()

    logger.info(f"Starting RATE ABUSE from IP: {attacker_ip}")
    logger.info(f"Delay between requests: {config.delay}s")

    headers = {
        "User-Agent": _get_random_user_agent(),
        "X-Forwarded-For": attacker_ip,
        "X-Real-IP": attacker_ip,
    }

    # Endpoints a abusar (rodar entre vários)
    targets = ["/api/data", "/api/users", "/health", "/search?q=test"]

    with requests.Session() as session:
        for i in _count_or_time_iterator(config):
            endpoint = targets[i % len(targets)]

            _make_request(
                session, "GET",
                f"{config.base_url}{endpoint}",
                headers=headers,
            )

            total += 1

            if config.verbose and total % 50 == 0:
                elapsed = time.time() - start_time
                rps = total / elapsed if elapsed > 0 else 0
                logger.info(f"[{total}] {rps:.1f} req/s")

            time.sleep(config.delay)

    elapsed = time.time() - start_time
    rps = total / elapsed if elapsed > 0 else 0
    logger.info(
        f"Rate abuse complete: {total} requests in {elapsed:.1f}s "
        f"({rps:.1f} req/s)"
    )


def generate_mixed_attack(config: GeneratorConfig) -> None:
    """Gera combinação aleatória de todos os tipos de ataque.

    Útil para simular um ambiente realista onde múltiplos
    atacantes com diferentes técnicas estão ativos simultaneamente.

    Args:
        config: Configuração base (delay e duração são usados).
    """
    logger.info("Starting MIXED attack simulation")

    attack_functions = [
        generate_brute_force,
        generate_scanning,
        generate_sql_injection,
        generate_rate_abuse,
    ]

    with requests.Session() as session:
        for i in _count_or_time_iterator(config):
            # Escolher ataque aleatório com pesos
            attack_fn = random.choices(
                attack_functions,
                weights=[30, 25, 25, 20],
                k=1,
            )[0]

            # Criar config com novo IP para cada "atacante"
            attack_config = GeneratorConfig(
                mode=TrafficMode.ATTACK,
                attack_type=config.attack_type,
                num_requests=random.randint(5, 20),
                target_ip=_generate_attacker_ip(),
                base_url=config.base_url,
                delay=config.delay,
                verbose=config.verbose,
            )

            attack_fn(attack_config)
            time.sleep(random.uniform(0.5, 2.0))

    logger.info("Mixed attack simulation complete")


# ─── DISPATCHER ──────────────────────────────────────────────────────────────


def run_generator(config: GeneratorConfig) -> None:
    """Seleciona e executa o gerador correto baseado na configuração.

    Usa dicionário de dispatch em vez de if/elif chain (mais limpo e extensível).

    Args:
        config: Configuração completa do gerador.

    Raises:
        ValueError: Se o modo ou tipo de ataque for inválido.
    """
    logger.info(f"Generator starting with mode={config.mode.name}")

    if config.mode == TrafficMode.NORMAL:
        generate_normal_traffic(config)
        return

    # Mapeamento de AttackType → função geradora
    attack_dispatch: dict = {
        AttackType.BRUTE_FORCE: generate_brute_force,
        AttackType.SCANNING: generate_scanning,
        AttackType.SQL_INJECTION: generate_sql_injection,
        AttackType.RATE_ABUSE: generate_rate_abuse,
        AttackType.MIXED: generate_mixed_attack,
    }

    attack_fn = attack_dispatch.get(config.attack_type)
    if not attack_fn:
        raise ValueError(f"Unknown attack type: {config.attack_type}")

    attack_fn(config)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    """Faz parse dos argumentos de linha de comando.

    Returns:
        Namespace com os argumentos parseados.
    """
    parser = argparse.ArgumentParser(
        description="Traffic Generator for Log Monitor MLOps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Tráfego normal por 60 segundos
  python traffic_generator.py --mode normal --duration 60

  # Brute force com 100 tentativas
  python traffic_generator.py --mode attack --type brute_force --num-requests 100

  # Scanning com IP específico
  python traffic_generator.py --mode attack --type scanning --target-ip 192.168.1.50

  # SQL injection, verbose
  python traffic_generator.py --mode attack --type sql_injection --num-requests 50 --verbose

  # Mix de ataques por 120 segundos
  python traffic_generator.py --mode attack --type mixed --duration 120

  # Rate abuse muito rápido
  python traffic_generator.py --mode attack --type rate_abuse --num-requests 500 --delay 0.01
        """,
    )

    parser.add_argument(
        "--mode",
        choices=["normal", "attack"],
        default="normal",
        help="Traffic mode: normal (legitimate users) or attack",
    )

    parser.add_argument(
        "--type",
        dest="attack_type",
        choices=["brute_force", "scanning", "sql_injection", "rate_abuse", "mixed"],
        default="mixed",
        help="Attack type (only used with --mode attack)",
    )

    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in seconds (used if --num-requests not set)",
    )

    parser.add_argument(
        "--num-requests",
        type=int,
        default=0,
        help="Total number of requests (overrides --duration if > 0)",
    )

    parser.add_argument(
        "--target-ip",
        type=str,
        default="",
        help="Attacker IP address (random if not set)",
    )

    parser.add_argument(
        "--url",
        default=BASE_URL,
        help=f"Base URL of the target app (default: {BASE_URL})",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=-1.0,
        help="Delay between requests in seconds (-1 = auto based on mode)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print details of each request",
    )

    return parser.parse_args()


def main() -> None:
    """Entry point principal do gerador de tráfego.

    Faz parse de argumentos, constrói configuração e executa gerador.
    """
    args = parse_args()

    # Determinar delay automático se não especificado
    if args.delay < 0:
        delay = (
            DEFAULT_DELAY_NORMAL
            if args.mode == "normal"
            else DEFAULT_DELAY_ATTACK
        )
    else:
        delay = args.delay

    # Construir configuração
    config = GeneratorConfig(
        mode=TrafficMode.NORMAL if args.mode == "normal" else TrafficMode.ATTACK,
        attack_type=AttackType(args.attack_type),
        duration_seconds=args.duration,
        num_requests=args.num_requests,
        target_ip=args.target_ip if args.target_ip else _generate_attacker_ip(),
        base_url=args.url,
        delay=delay,
        verbose=args.verbose,
    )

    logger.info("=" * 50)
    logger.info("Log Monitor MLOps - Traffic Generator")
    logger.info("=" * 50)
    logger.info(f"Mode: {config.mode.name}")
    if config.mode == TrafficMode.ATTACK:
        logger.info(f"Attack type: {config.attack_type.value}")
        logger.info(f"Attacker IP: {config.target_ip}")
    logger.info(f"Target: {config.base_url}")
    logger.info(f"Duration: {config.duration_seconds}s" if config.num_requests == 0
                else f"Requests: {config.num_requests}")
    logger.info(f"Delay: {config.delay}s")
    logger.info("=" * 50)

    try:
        run_generator(config)
    except KeyboardInterrupt:
        logger.info("Generator stopped by user (Ctrl+C)")
        sys.exit(0)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
