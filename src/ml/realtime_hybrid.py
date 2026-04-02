
import os
import time
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv
from hybrid_pipeline import HybridPipeline
from feature_engineering import FeatureEngineer

load_dotenv()


class RealtimeHybridProcessor:

    def __init__(self, poll_interval_sec=30):
        self.poll_interval = poll_interval_sec
        self.pipeline  = HybridPipeline()
        self.feat_eng  = FeatureEngineer()
        self.last_processed_id = self._get_last_processed_id()
        print(f"✓ RealtimeHybridProcessor iniciado")
        print(f"  Último log processado: id={self.last_processed_id}")
        print(f"  Poll interval: {self.poll_interval}s")

    def _get_last_processed_id(self):
        """Encontra o último log_id já avaliado."""
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            database=os.getenv("POSTGRES_DB", "logmonitor"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme"),
        )
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(log_id), 0) FROM hybrid_scores")
        last_id = cur.fetchone()[0]
        cur.close()
        conn.close()
        return last_id

    def fetch_new_logs(self):
        """Busca logs novos que ainda não foram avaliados."""
        conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            database=os.getenv("POSTGRES_DB", "logmonitor"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme"),
        )
        query = """
            SELECT id, timestamp, ip, method, endpoint,
                   status, response_time_ms, user_agent
            FROM   raw_logs
            WHERE  id > %s
            ORDER  BY id
            LIMIT  500
        """
        df = pd.read_sql(query, conn, params=(self.last_processed_id,))
        conn.close()
        return df

    def process_logs(self, raw_df):
        """Extrai features e avalia cada log."""
        if raw_df.empty:
            return

        # Extrair features com o FeatureEngineer da Semana 5
        features_df = self.feat_eng.extract_features(raw_df)
        features_df["log_id"] = raw_df["id"].values

        # Avaliar cada log
        anomalies_found = 0
        for _, row in features_df.iterrows():
            result = self.pipeline.evaluate_log(
                log_id=int(row["log_id"]),
                log_features=row.to_dict(),
            )
            if result["is_anomaly"]:
                anomalies_found += 1
                sev = result["severity"]
                score = result["final_score"]
                rules = ", ".join(result["triggered_rules"]) or "none"
                print(f"  [{sev}] log_id={result['log_id']} "
                      f"score={score:.3f} rules=[{rules}]")

        # Atualizar último ID processado
        self.last_processed_id = int(features_df["log_id"].max())

        n = len(features_df)
        print(f"  Processados: {n} logs | Anomalias: {anomalies_found} ({100*anomalies_found/n:.1f}%)")

    def run(self):
        """Loop principal."""
        print(f"\n{'='*60}")
        print("REALTIME HYBRID PROCESSOR")
        print(f"{'='*60}")
        print(f"A iniciar loop (Ctrl+C para parar)...\n")

        while True:
            ts = datetime.now().strftime("%H:%M:%S")
            new_logs = self.fetch_new_logs()

            if new_logs.empty:
                print(f"[{ts}] Sem logs novos. A aguardar {self.poll_interval}s...")
            else:
                print(f"[{ts}] {len(new_logs)} logs novos encontrados:")
                self.process_logs(new_logs)

            time.sleep(self.poll_interval)


if __name__ == "__main__":
    processor = RealtimeHybridProcessor(poll_interval_sec=30)
    processor.run()
