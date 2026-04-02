
import os
import psycopg2
import pandas as pd
from dotenv import load_dotenv
from hybrid_pipeline import HybridPipeline

load_dotenv()


def load_logs_with_features(days=7):
    """
    Carrega logs do PostgreSQL + dataset de features da Semana 5.
    Faz JOIN pelo log_id para garantir alinhamento.
    """
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        database=os.getenv("POSTGRES_DB", "logmonitor"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "changeme"),
    )

    # Carregar logs recentes
    logs_query = f"""
        SELECT id, timestamp, ip, endpoint, status, method
        FROM   raw_logs
        WHERE  timestamp > NOW() - INTERVAL '{days} days'
        ORDER  BY timestamp
    """
    logs_df = pd.read_sql(logs_query, conn)
    conn.close()

    print(f"✓ {len(logs_df):,} logs carregados da DB")

    # Carregar dataset de features (Semana 5)
    features_df = pd.read_pickle("data/ml_dataset.pkl")
    print(f"✓ {len(features_df):,} linhas no dataset de features")

    # JOIN pelo log_id
    merged = features_df.merge(
        logs_df[["id"]],
        left_on="log_id",
        right_on="id",
        how="inner",
    )
    print(f"✓ {len(merged):,} logs com features disponíveis (após JOIN)")
    if len(merged) == 0:
       print("⚠ JOIN vazio, a usar features_df directamente.")
       return features_df
    return merged


def main():
    print("=" * 70)
    print("HYBRID PIPELINE — EXECUÇÃO BATCH")
    print("=" * 70)

    # 1. Iniciar pipeline
    pipeline = HybridPipeline()

    # 2. Carregar dados
    df = load_logs_with_features(days=7)

    # 3. Avaliar batch
    results = pipeline.evaluate_batch(df, verbose=True)

    # 4. Guardar resultados localmente
    results.to_csv("data/hybrid_results.csv", index=False)
    print(f"\n✓ Resultados guardados: data/hybrid_results.csv")

    # 5. Top anomalias
    print("\n--- TOP 10 ANOMALIAS (por score final) ---")
    top = results[results["is_anomaly"]].sort_values(
        "final_score", ascending=False
    ).head(10)
    print(
        top[["log_id", "rule_score", "ml_score", "final_score", "severity", "triggered_rules"]].to_string(index=False)
    )

    print("\n✓ PIPELINE CONCLUÍDO!")
    print("✓ Ver tabela na DB: SELECT * FROM hybrid_scores ORDER BY final_score DESC LIMIT 20;")


if __name__ == "__main__":
    main()