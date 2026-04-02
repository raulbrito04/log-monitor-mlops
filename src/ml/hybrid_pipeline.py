#!/usr/bin/env python3
"""
Hybrid Detection Pipeline — Semana 7
Combina Rule Engine (Semana 4) com Isolation Forest (Semana 6)
"""

import pickle
import json
import os
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# ─── Configuração ────────────────────────────────────────────────────────────

RULE_WEIGHT  = 0.55   # Regras são mais confiáveis em padrões conhecidos
ML_WEIGHT    = 0.45   # ML apanha o que as regras não cobrem
# RULE_WEIGHT + ML_WEIGHT deve ser 1.0

THRESHOLDS = {
    "CRITICAL": 0.80,
    "HIGH":     0.60,
    "MEDIUM":   0.40,
    # Abaixo de 0.40 → NORMAL
}


# ─── Hybrid Pipeline ─────────────────────────────────────────────────────────

class HybridPipeline:
    """
    Pipeline híbrido: Rules + ML → Score final + Severidade.

    Fluxo por log:
        1. Rule Engine → rule_score (0.0–1.0) + lista de regras
        2. ML Model    → ml_score (0.0–1.0) baseado em anomaly score
        3. Combiner    → final_score = rule_score * RULE_WEIGHT + ml_score * ML_WEIGHT
        4. Classifier  → severidade baseada em thresholds
        5. Persist     → guardar em hybrid_scores
    """

    def __init__(
        self,
        model_path="models/isolation_forest_latest.pkl",
        scaler_path="models/scaler.pkl",
        features_path="data/selected_features.txt",
        rule_weight=RULE_WEIGHT,
        ml_weight=ML_WEIGHT,
    ):
        # Pesos
        assert abs(rule_weight + ml_weight - 1.0) < 1e-6, \
            "rule_weight + ml_weight deve ser 1.0"
        self.rule_weight = rule_weight
        self.ml_weight   = ml_weight

        # Carregar modelo ML e scaler (guardado como dict)
        with open(model_path, "rb") as f:
            bundle = pickle.load(f)
        self.model  = bundle["model"]
        self.scaler = bundle["scaler"]

        # Features esperadas pelo modelo (na ordem correta)
        with open(features_path) as f:
            self.feature_cols = [line.strip() for line in f if line.strip()]

        # DB connection
        self.conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            database=os.getenv("POSTGRES_DB", "logmonitor"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "changeme"),
        )
        self.conn.autocommit = False

        print("✓ HybridPipeline iniciado")
        print(f"  rule_weight={self.rule_weight}, ml_weight={self.ml_weight}")
        print(f"  Features esperadas: {len(self.feature_cols)}")

    # ── Score de Regras ───────────────────────────────────────────────────────

    def get_rule_score(self, log_id: int):
        """
        Busca score de regras para um log a partir da tabela alerts.

        Retorna:
            rule_score  (float 0–1): 0 = sem alertas, 1 = máxima severidade
            rule_ids    (list[str]): lista de rule_ids que dispararam
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT alert_type, severity
            FROM   alerts
            WHERE  %s = ANY(log_ids)
            ORDER  BY severity DESC
            """,
            (log_id,),
        )
        rows = cursor.fetchall()
        cursor.close()

        if not rows:
            return 0.0, []

        # Mapa de severidade → peso
        severity_map = {
            "CRITICAL": 1.00,
            "HIGH":     0.75,
            "MEDIUM":   0.50,
            "LOW":      0.25,
        }

        # Score = máximo das severidades encontradas
        scores = [severity_map.get(row[1], 0.25) for row in rows]
        rule_score = max(scores)
        rule_ids   = [row[0] for row in rows]

        return rule_score, rule_ids

    # ── Score de ML ───────────────────────────────────────────────────────────

    def get_ml_score(self, log_features: dict):
        """
        Calcula score ML a partir de features de um log.

        O Isolation Forest retorna decision_function scores negativos
        para anomalias. Convertemos para [0, 1]:
            0.0 → normal
            1.0 → anomalia máxima

        Retorna:
            ml_score    (float 0–1)
            confidence  (float 0–1): quão confiante o modelo está
        """
        # Construir DataFrame na ordem correta
        row = {col: log_features.get(col, 0.0) for col in self.feature_cols}
        X = pd.DataFrame([row])

        # Normalizar com o scaler da Semana 5
        X_scaled = self.scaler.transform(X)

        # decision_function: mais negativo = mais anómalo
        raw_score = self.model.decision_function(X_scaled)[0]

        # Converter para [0, 1]:
        # Isolation Forest tipicamente retorna scores entre -0.5 e 0.5
        # Clamp + normalizar
        raw_clamped = np.clip(raw_score, -0.5, 0.5)
        ml_score = 1.0 - (raw_clamped + 0.5)  # 0 = normal, 1 = anomalia

        # Confidence: quão longe está do threshold (0.5)
        confidence = abs(ml_score - 0.5) * 2.0

        return float(ml_score), float(confidence)

    # ── Combinar Scores ───────────────────────────────────────────────────────

    def combine_scores(self, rule_score: float, ml_score: float):
        """
        Combina os dois scores com pesos configuráveis.

        Regra adicional: Se rule_score == 1.0 (CRITICAL rule), forçar
        final_score mínimo de 0.75 independentemente do ML.
        """
        final = rule_score * self.rule_weight + ml_score * self.ml_weight

        # Override: regra CRITICAL sempre no mínimo HIGH
        if rule_score >= 1.0:
            final = max(final, 0.75)

        return round(float(final), 4)

    # ── Classificar Severidade ────────────────────────────────────────────────

    def classify_severity(self, final_score: float):
        """Mapeia score final → severidade."""
        if final_score >= THRESHOLDS["CRITICAL"]:
            return "CRITICAL"
        elif final_score >= THRESHOLDS["HIGH"]:
            return "HIGH"
        elif final_score >= THRESHOLDS["MEDIUM"]:
            return "MEDIUM"
        else:
            return "NORMAL"

    # ── Avaliar um Log ────────────────────────────────────────────────────────

    def evaluate_log(self, log_id: int, log_features: dict):
        """
        Avalia um único log e persiste o resultado.

        Args:
            log_id       : ID do log em raw_logs
            log_features : dict com features pré-calculadas (da Semana 5)

        Returns:
            dict com o resultado completo
        """
        # 1. Rule score
        rule_score, rule_ids = self.get_rule_score(log_id)

        # 2. ML score
        ml_score, ml_confidence = self.get_ml_score(log_features)

        # 3. Score combinado
        final_score = self.combine_scores(rule_score, ml_score)

        # 4. Severidade
        severity = self.classify_severity(final_score)

        result = {
            "log_id":       log_id,
            "rule_score":   rule_score,
            "ml_score":     ml_score,
            "final_score":  final_score,
            "severity":     severity,
            "triggered_rules": rule_ids,
            "ml_confidence":   ml_confidence,
            "is_anomaly":   severity != "NORMAL",
        }

        # 5. Persistir na DB
        self._persist(result)

        return result

    # ── Persistência ──────────────────────────────────────────────────────────

    def _persist(self, result: dict):
        """Guarda resultado em hybrid_scores."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO hybrid_scores
                (log_id, rule_score, ml_score, final_score,
                 severity, triggered_rules, ml_confidence, is_anomaly)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                result["log_id"],
                result["rule_score"],
                result["ml_score"],
                result["final_score"],
                result["severity"],
                result["triggered_rules"],
                result["ml_confidence"],
                result["is_anomaly"],
            ),
        )
        self.conn.commit()
        cursor.close()

    # ── Avaliar Batch ─────────────────────────────────────────────────────────

    def evaluate_batch(self, logs_df: pd.DataFrame, verbose=True):
        """
        Avalia um DataFrame de logs completo.

        Args:
            logs_df : DataFrame com coluna 'id' + features da Semana 5

        Returns:
            DataFrame com colunas de resultado adicionadas
        """
        results = []
        total = len(logs_df)

        print(f"\nAvaliando {total:,} logs...")

        for i, (_, row) in enumerate(logs_df.iterrows(), 1):
            log_id = int(row["id"]) if "id" in row else int(row["log_id"])
            features = row.to_dict()

            result = self.evaluate_log(log_id, features)
            results.append(result)

            if verbose and i % 500 == 0:
                print(f"  {i:,}/{total:,} avaliados...")

        results_df = pd.DataFrame(results)

        if verbose:
            print(f"\n✓ Batch completo!")
            self._print_summary(results_df)

        return results_df

    # ── Sumário ───────────────────────────────────────────────────────────────

    def _print_summary(self, results_df: pd.DataFrame):
        
        """Imprime sumário dos resultados."""
        print("\n" + "=" * 60)
        print("SUMÁRIO DO PIPELINE HÍBRIDO")
        print("=" * 60)

        total = len(results_df)
        if results_df.empty:
          print("⚠ DataFrame vazio, nada para sumarizar.")
          return
        severity_counts = results_df["severity"].value_counts()

        for sev in ["CRITICAL", "HIGH", "MEDIUM", "NORMAL"]:
            count = severity_counts.get(sev, 0)
            pct = 100 * count / total
            bar = "█" * int(pct / 2)
            print(f"  {sev:<10} {count:>5} ({pct:5.1f}%)  {bar}")

        print(f"\n  Total avaliado : {total:,}")
        print(f"  Anomalias      : {results_df['is_anomaly'].sum():,} ({100*results_df['is_anomaly'].mean():.1f}%)")
        print(f"  Score médio    : {results_df['final_score'].mean():.3f}")
        print(f"  Rule score médio: {results_df['rule_score'].mean():.3f}")
        print(f"  ML score médio  : {results_df['ml_score'].mean():.3f}")
        print("=" * 60)