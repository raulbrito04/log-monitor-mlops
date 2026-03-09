"""
Rule Engine - Deteção baseada em regras SQL
Suporta dois modos:
  --mode historical   Analisa todo o historico (janela larga, corre uma vez)
  --mode realtime     Analisa janela recente em loop continuo (producao)

Uso:
  python src/detection/rule_engine.py --mode historical
  python src/detection/rule_engine.py --mode realtime
  python src/detection/rule_engine.py --mode realtime --interval 30
"""

import psycopg2
import os
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


def get_rules(window):
    """
    Retorna as 3 regras SQL com a janela de tempo fornecida.
    window: string PostgreSQL interval, ex: '60 seconds' ou '7 days'
    """
    return [
        (
            "Brute Force Detection",
            """
            INSERT INTO alerts (alert_type, severity, source, confidence,
                                description, log_ids, ip, timestamp, metadata)
            SELECT
                'brute_force', 'HIGH', 'rule', 1.0,
                'Detected ' || COUNT(*) || ' failed login attempts from IP ' || ip,
                ARRAY_AGG(id ORDER BY timestamp),
                ip,
                MAX(timestamp),
                jsonb_build_object(
                    'failed_attempts',    COUNT(*),
                    'endpoints_targeted', ARRAY_AGG(DISTINCT endpoint),
                    'time_window',        '{window}',
                    'first_attempt',      MIN(timestamp),
                    'last_attempt',       MAX(timestamp)
                )
            FROM raw_logs
            WHERE endpoint = '/login'
              AND status = 401
              AND timestamp > NOW() - INTERVAL '{window}'
            GROUP BY ip
            HAVING COUNT(*) >= 5;
            """.replace("{window}", window)
        ),
        (
            "SQL Injection Detection",
            """
            INSERT INTO alerts (alert_type, severity, source, confidence,
                                description, log_ids, ip, timestamp, metadata)
            SELECT
                'sql_injection', 'CRITICAL', 'rule', 1.0,
                'SQL injection attempt from IP ' || ip || ' on ' || endpoint,
                ARRAY_AGG(id ORDER BY timestamp),
                ip,
                MAX(timestamp),
                jsonb_build_object(
                    'endpoint', endpoint,
                    'method',   method,
                    'attempts', COUNT(*)
                )
            FROM raw_logs
            WHERE timestamp > NOW() - INTERVAL '{window}'
              AND (
                  endpoint ILIKE '%union%select%'
               OR endpoint ILIKE '%or%1=1%'
               OR endpoint ILIKE '%drop%table%'
               OR endpoint ILIKE '%--%'
              )
            GROUP BY ip, endpoint, method
            HAVING COUNT(*) >= 1;
            """.replace("{window}", window)
        ),
        (
            "Port Scanning Detection",
            """
            INSERT INTO alerts (alert_type, severity, source, confidence,
                                description, log_ids, ip, timestamp, metadata)
            SELECT
                'port_scanning', 'MEDIUM', 'rule', 0.9,
                'Scanning: ' || COUNT(DISTINCT endpoint) || ' endpoints from IP ' || ip,
                ARRAY_AGG(id ORDER BY timestamp),
                ip,
                MAX(timestamp),
                jsonb_build_object(
                    'unique_endpoints',    COUNT(DISTINCT endpoint),
                    'total_requests',      COUNT(*),
                    'endpoints_list',      ARRAY_AGG(DISTINCT endpoint),
                    'time_window',         '{window}',
                    'average_response_ms', AVG(response_time_ms)
                )
            FROM raw_logs
            WHERE timestamp > NOW() - INTERVAL '{window}'
            GROUP BY ip
            HAVING COUNT(DISTINCT endpoint) >= 10;
            """.replace("{window}", window)
        ),
    ]


def execute_rule(cursor, rule_name, sql_query):
    try:
        start = datetime.now()
        cursor.execute(sql_query)
        count = cursor.rowcount
        ms = (datetime.now() - start).total_seconds() * 1000
        print(f"  OK  {rule_name:<30} {count} alertas  ({ms:.1f}ms)")
        return count
    except Exception as e:
        print(f"  ERRO {rule_name}: {e}")
        return 0


def run_once(cursor, window, label):
    print(f"\n{'=' * 60}")
    print(f"RULE ENGINE [{label}] -- janela: {window}")
    print(f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

    total = 0
    for name, sql in get_rules(window):
        total += execute_rule(cursor, name, sql)

    print(f"\n  Total de alertas criados: {total}")
    print(f"{'=' * 60}\n")
    return total


def connect():
    return psycopg2.connect(
        host="localhost",
        port=5432,
        database="logmonitor",
        user="postgres",
        password=os.getenv("POSTGRES_PASSWORD", "changeme")
    )


def mode_historical(days):
    """Corre uma vez sobre todo o historico."""
    print(f"\nModo HISTORICAL -- analisando ultimos {days} dias")
    conn = connect()
    cursor = conn.cursor()
    run_once(cursor, f"{days} days", "HISTORICAL")
    conn.commit()
    cursor.close()
    conn.close()
    print("Analise historica concluida.")


def mode_realtime(interval_seconds):
    """Corre em loop, analisando janela recente a cada interval_seconds."""
    print(f"\nModo REALTIME -- janela: 60 seconds | ciclo: {interval_seconds}s")
    print("Ctrl+C para parar.\n")
    conn = connect()
    cursor = conn.cursor()
    try:
        while True:
            run_once(cursor, "60 seconds", "REALTIME")
            conn.commit()
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\nParado pelo utilizador.")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rule Engine -- detecao de anomalias")
    parser.add_argument(
        "--mode",
        choices=["historical", "realtime"],
        required=True,
        help="historical: analisa todo o historico uma vez | realtime: loop continuo"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Dias a analisar no modo historical (default: 7)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Segundos entre ciclos no modo realtime (default: 60)"
    )
    args = parser.parse_args()

    if args.mode == "historical":
        mode_historical(args.days)
    else:
        mode_realtime(args.interval)
