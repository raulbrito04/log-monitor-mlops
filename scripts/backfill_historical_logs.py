#!/usr/bin/env python3
"""Backfill historico de logs sinteticos sem duplicar a logica do projeto.

Reutiliza os cenarios e assinaturas de ataque do traffic_generator e o
mesmo esquema de insercao do ingester para popular raw_logs com timestamps
espalhados ao longo de varios dias sinteticos.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from src.flask_app.traffic_generator import (
    BRUTE_FORCE_CREDENTIALS,
    NORMAL_ENDPOINTS,
    SCAN_TARGETS,
    SQL_INJECTION_PAYLOADS,
    _generate_attacker_ip,
    _get_legitimate_user_agent,
    _get_random_user_agent,
)
from src.log_processor.ingester import get_db_connection, insert_logs_batch
from src.detection.rule_engine import mode_historical


@dataclass
class DayPlan:
    day_offset: int
    normal_requests: int
    brute_force_attempts: int
    scanning_requests: int
    sqli_requests: int
    rate_abuse_requests: int
    offhours_requests: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Historical synthetic log backfill")
    parser.add_argument("--days", type=int, default=21, help="Numero de dias sinteticos a gerar")
    parser.add_argument("--seed", type=int, default=42, help="Seed para reproducibilidade")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size para INSERT")
    parser.add_argument("--apply", action="store_true", help="Insere na base de dados")
    parser.add_argument("--truncate-existing", action="store_true", help="Apaga raw_logs e alerts antes de inserir")
    parser.add_argument("--run-rule-engine", action="store_true", help="Executa o rule engine historical no fim")
    return parser.parse_args()


def build_day_plans(num_days: int) -> list[DayPlan]:
    plans = []
    scenario_cycle = [
        (220, 0, 0, 0, 0, 0),
        (260, 18, 0, 0, 0, 0),
        (200, 0, 24, 0, 0, 0),
        (210, 0, 0, 18, 0, 0),
        (240, 0, 0, 0, 180, 0),
        (190, 0, 0, 0, 0, 35),
        (280, 8, 12, 10, 80, 20),
    ]
    for idx in range(num_days):
        normal, brute, scan, sqli, abuse, offhours = scenario_cycle[idx % len(scenario_cycle)]
        plans.append(
            DayPlan(
                day_offset=num_days - idx,
                normal_requests=normal,
                brute_force_attempts=brute,
                scanning_requests=scan,
                sqli_requests=sqli,
                rate_abuse_requests=abuse,
                offhours_requests=offhours,
            )
        )

    # Garantir anomalias tambem no fim da serie temporal.
    for idx in range(max(0, num_days - 5), num_days):
        plan = plans[idx]
        plan.brute_force_attempts = max(plan.brute_force_attempts, 10)
        plan.sqli_requests = max(plan.sqli_requests, 6)
        plan.offhours_requests = max(plan.offhours_requests, 12)

    return plans


def day_base_timestamp(day_offset: int) -> datetime:
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(days=day_offset)


def build_log(timestamp: datetime, ip: str, method: str, endpoint: str, status: int,
              response_time_ms: int, user_agent: str, extra: dict | None = None) -> dict:
    payload = {
        "log_type": "web",
        "synthetic_backfill": True,
        "timestamp": timestamp.isoformat(),
        "ip": ip,
        "method": method,
        "endpoint": endpoint,
        "status": status,
        "response_time_ms": response_time_ms,
        "user_agent": user_agent,
    }
    if extra:
        payload.update(extra)
    return payload


def random_business_timestamp(base_day: datetime) -> datetime:
    hour = random.randint(8, 20)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    return base_day + timedelta(hours=hour, minutes=minute, seconds=second)


def random_offhours_timestamp(base_day: datetime) -> datetime:
    hour = random.choice([22, 23, 0, 1, 2, 3, 4, 5])
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    day_adjust = 1 if hour < 6 else 0
    return base_day + timedelta(days=day_adjust, hours=hour, minutes=minute, seconds=second)


def generate_normal_logs(base_day: datetime, count: int) -> list[dict]:
    logs = []
    good_passwords = {"user1": "password1", "user2": "password2", "analyst": "analyst99"}
    for _ in range(count):
        method, endpoint = random.choice(NORMAL_ENDPOINTS)
        ip_addr = f"10.0.{random.randint(1, 20)}.{random.randint(2, 254)}"
        ts = random_business_timestamp(base_day)
        ua = _get_legitimate_user_agent()
        status = 200
        response_time = random.randint(30, 250)
        extra = {}
        if endpoint == "/health":
            response_time = random.randint(5, 30)
        elif endpoint == "/login":
            if random.random() < 0.08:
                status = 401
                extra = {"username": f"user{random.randint(3, 20)}"}
            else:
                username = random.choice(list(good_passwords.keys()))
                extra = {"username": username}
                status = 200
                response_time = random.randint(60, 180)
        extra["scenario"] = "normal"
        logs.append(build_log(ts, ip_addr, method, endpoint, status, response_time, ua, extra))
    return logs


def generate_brute_force_logs(base_day: datetime, attempts: int) -> list[dict]:
    logs = []
    attacker_ip = _generate_attacker_ip()
    start = base_day + timedelta(hours=10, minutes=random.randint(0, 20))
    for idx in range(attempts):
        username, password = BRUTE_FORCE_CREDENTIALS[idx % len(BRUTE_FORCE_CREDENTIALS)]
        ts = start + timedelta(seconds=idx * random.randint(2, 8))
        logs.append(
            build_log(
                ts,
                attacker_ip,
                "POST",
                "/login",
                401,
                random.randint(40, 140),
                "python-requests/2.31.0",
                {"username": username, "password": password, "scenario": "brute_force"},
            )
        )
    return logs


def generate_scanning_logs(base_day: datetime, count: int) -> list[dict]:
    logs = []
    attacker_ip = _generate_attacker_ip()
    start = base_day + timedelta(hours=14, minutes=random.randint(0, 20))
    for idx in range(count):
        endpoint = SCAN_TARGETS[idx % len(SCAN_TARGETS)]
        ts = start + timedelta(seconds=idx * random.randint(1, 4))
        logs.append(
            build_log(
                ts,
                attacker_ip,
                "GET",
                endpoint,
                404,
                random.randint(10, 90),
                "Nikto/2.1.6",
                {"scenario": "scanning"},
            )
        )
    return logs


def generate_sqli_logs(base_day: datetime, count: int) -> list[dict]:
    logs = []
    attacker_ip = _generate_attacker_ip()
    start = base_day + timedelta(hours=16, minutes=random.randint(0, 20))
    for idx in range(count):
        payload = SQL_INJECTION_PAYLOADS[idx % len(SQL_INJECTION_PAYLOADS)]
        endpoint = f"/search?q={payload}"
        ts = start + timedelta(seconds=idx * random.randint(3, 9))
        logs.append(
            build_log(
                ts,
                attacker_ip,
                "GET",
                endpoint,
                500 if random.random() < 0.35 else 200,
                random.randint(80, 260),
                "sqlmap/1.7.8#stable",
                {"scenario": "sql_injection"},
            )
        )
    return logs


def generate_rate_abuse_logs(base_day: datetime, count: int) -> list[dict]:
    logs = []
    attacker_ip = _generate_attacker_ip()
    start = base_day + timedelta(hours=18, minutes=random.randint(0, 20))
    targets = ["/api/data", "/api/users", "/health", "/search?q=test"]
    for idx in range(count):
        endpoint = targets[idx % len(targets)]
        ts = start + timedelta(milliseconds=idx * random.randint(120, 400))
        logs.append(
            build_log(
                ts,
                attacker_ip,
                "GET",
                endpoint,
                200,
                random.randint(15, 60),
                _get_random_user_agent(),
                {"scenario": "rate_abuse"},
            )
        )
    return logs


def generate_offhours_logs(base_day: datetime, count: int) -> list[dict]:
    logs = []
    actor_ip = _generate_attacker_ip()
    for _ in range(count):
        ts = random_offhours_timestamp(base_day)
        endpoint = random.choice(["/api/data", "/api/users", "/search?q=data"])
        logs.append(
            build_log(
                ts,
                actor_ip,
                "GET",
                endpoint,
                200,
                random.randint(20, 120),
                _get_random_user_agent(),
            )
        )
    return logs


def generate_logs(num_days: int) -> tuple[list[dict], list[dict]]:
    plans = build_day_plans(num_days)
    all_logs = []
    summaries = []
    for plan in plans:
        base_day = day_base_timestamp(plan.day_offset)
        day_logs = []
        day_logs.extend(generate_normal_logs(base_day, plan.normal_requests))
        day_logs.extend(generate_brute_force_logs(base_day, plan.brute_force_attempts))
        day_logs.extend(generate_scanning_logs(base_day, plan.scanning_requests))
        day_logs.extend(generate_sqli_logs(base_day, plan.sqli_requests))
        day_logs.extend(generate_rate_abuse_logs(base_day, plan.rate_abuse_requests))
        day_logs.extend(generate_offhours_logs(base_day, plan.offhours_requests))
        day_logs.sort(key=lambda log: log["timestamp"])
        all_logs.extend(day_logs)
        summaries.append(
            {
                "day": base_day.date().isoformat(),
                "total_logs": len(day_logs),
                "normal": plan.normal_requests,
                "brute_force": plan.brute_force_attempts,
                "scanning": plan.scanning_requests,
                "sql_injection": plan.sqli_requests,
                "rate_abuse": plan.rate_abuse_requests,
                "offhours": plan.offhours_requests,
            }
        )
    return all_logs, summaries


def truncate_existing(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE alerts RESTART IDENTITY CASCADE")
        cursor.execute("TRUNCATE TABLE raw_logs RESTART IDENTITY CASCADE")
    conn.commit()


def insert_logs(logs: list[dict], batch_size: int, truncate_before_insert: bool) -> None:
    conn = get_db_connection()
    try:
        if truncate_before_insert:
            truncate_existing(conn)
            print("✓ raw_logs e alerts limpos antes do backfill")
        with conn.cursor() as cursor:
            total_inserted = 0
            for start in range(0, len(logs), batch_size):
                batch = logs[start:start + batch_size]
                inserted = insert_logs_batch(cursor, batch)
                conn.commit()
                total_inserted += inserted
                print(f"✓ Inseridos {total_inserted}/{len(logs)} logs")
    finally:
        conn.close()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    logs, summaries = generate_logs(args.days)

    print("=" * 70)
    print("HISTORICAL BACKFILL PLAN")
    print("=" * 70)
    print(f"Dias sinteticos: {args.days}")
    print(f"Total de logs a gerar: {len(logs)}")
    for summary in summaries:
        print(summary)

    if not args.apply:
        print("\nModo dry-run. Usa --apply para inserir na base.")
        return 0

    insert_logs(logs, batch_size=args.batch_size, truncate_before_insert=args.truncate_existing)
    print("\n✓ Backfill concluido.")

    if args.run_rule_engine:
        print(f"\nA correr rule_engine historical para {args.days} dias...")
        mode_historical(args.days)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
