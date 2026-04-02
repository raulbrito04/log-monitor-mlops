#!/usr/bin/env python3
"""Model Training Pipeline - hybrid supervised + novelty detection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import pickle
import warnings

import matplotlib.pyplot as plt
import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")


class ModelTrainer:
    """Pipeline de treino responsavel com ensemble hibrido."""

    MIN_RELIABLE_ANOMALIES = 20
    IFOREST_THRESHOLD_QUANTILES = [0.80, 0.84, 0.88, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97, 0.98, 0.99]

    def __init__(self, mlflow_uri="http://localhost:5000"):
        self.mlflow_uri = mlflow_uri
        self.experiment_name = "isolation-forest-experiments"
        try:
            mlflow.set_tracking_uri(mlflow_uri)
            mlflow.set_experiment(self.experiment_name)
            print(f"? MLflow tracking: {mlflow_uri}")
        except Exception as exc:
            fallback_uri = f"file:{Path('mlruns').resolve().as_posix()}"
            self.mlflow_uri = fallback_uri
            mlflow.set_tracking_uri(fallback_uri)
            mlflow.set_experiment(self.experiment_name)
            print(f"! MLflow remoto indisponivel ({exc})")
            print(f"? MLflow fallback local: {fallback_uri}")

    def load_data(self):
        print("\n1. Carregando dataset...")
        data_dir = Path("data")
        pickle_path = data_dir / "ml_dataset.pkl"
        csv_path = data_dir / "ml_dataset.csv"
        iforest_pickle_path = data_dir / "ml_dataset_iforest.pkl"
        iforest_csv_path = data_dir / "ml_dataset_iforest.csv"
        features_path = data_dir / "selected_features.txt"
        iforest_features_path = data_dir / "iforest_features.txt"

        try:
            df = pd.read_pickle(pickle_path)
            print(f"   ? Dataset carregado de: {pickle_path}")
        except (NotImplementedError, ModuleNotFoundError, AttributeError) as exc:
            if not csv_path.exists():
                raise RuntimeError(
                    f"Falha ao ler {pickle_path} e nao existe fallback CSV em {csv_path}"
                ) from exc
            print(f"   ! Pickle incompativel com a versao atual do pandas: {exc}")
            print(f"   ! A usar fallback CSV: {csv_path}")
            df = pd.read_csv(csv_path, parse_dates=["timestamp"])

        try:
            df_iforest = pd.read_pickle(iforest_pickle_path)
            print(f"   ? Dataset IF carregado de: {iforest_pickle_path}")
        except (NotImplementedError, ModuleNotFoundError, AttributeError, FileNotFoundError) as exc:
            if not iforest_csv_path.exists():
                raise RuntimeError(
                    f"Falha ao ler {iforest_pickle_path} e nao existe fallback CSV em {iforest_csv_path}"
                ) from exc
            print(f"   ! A usar fallback IF CSV: {iforest_csv_path}")
            df_iforest = pd.read_csv(iforest_csv_path, parse_dates=["timestamp"])

        if features_path.exists():
            feature_cols = [line.strip() for line in features_path.read_text().splitlines() if line.strip()]
        else:
            feature_cols = [c for c in df.columns if c not in ["label", "log_id", "timestamp"]]

        if iforest_features_path.exists():
            iforest_feature_cols = [line.strip() for line in iforest_features_path.read_text().splitlines() if line.strip()]
        else:
            iforest_feature_cols = [c for c in df_iforest.columns if c not in ["label", "log_id", "timestamp"]]

        for col in feature_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        for col in iforest_feature_cols:
            df_iforest[col] = pd.to_numeric(df_iforest[col], errors="coerce")

        for frame in (df, df_iforest):
            frame["label"] = pd.to_numeric(frame["label"], errors="raise").astype(int)
            frame["log_id"] = pd.to_numeric(frame["log_id"], errors="raise").astype(int)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
            for col in ["scenario", "protocol_role", "protocol_split"]:
                if col in frame.columns:
                    frame[col] = frame[col].fillna("observed").astype(str)

        align_cols = ["log_id", "timestamp", "label"]
        if "protocol_split" in df.columns and "protocol_split" in df_iforest.columns:
            align_cols.append("protocol_split")
        if not df[align_cols].reset_index(drop=True).equals(df_iforest[align_cols].reset_index(drop=True)):
            raise RuntimeError("Datasets supervisionado e iforest nao estao alinhados temporalmente.")

        x_data = df[feature_cols]
        x_iforest = df_iforest[iforest_feature_cols]
        y_data = df["label"]
        metadata_cols = [col for col in ["log_id", "timestamp", "scenario", "protocol_role", "protocol_split"] if col in df.columns]
        metadata = df[metadata_cols].copy()
        print(f"   ? Shape supervisionado: {x_data.shape}")
        print(f"   ? Shape iforest: {x_iforest.shape}")
        print(f"   ? Features supervisionadas: {list(x_data.columns)}")
        print(f"   ? Features iforest: {list(x_iforest.columns)}")
        print(f"   ? Anomaly rate: {y_data.mean():.2%}")
        return x_data, x_iforest, y_data, metadata

    def build_novelty_protocol_split(self, x_iforest, y_data, metadata):
        print("\n2.1. Criando split por protocolo de novelty detection...")
        if 'protocol_split' not in metadata.columns:
            raise RuntimeError('Metadata sem protocol_split para novelty detection.')
        splits = {}
        for split_name in ['baseline_train', 'threshold_validation', 'novelty_test']:
            mask = metadata['protocol_split'] == split_name
            splits[split_name] = {
                'X': x_iforest.loc[mask],
                'y': y_data.loc[mask],
                'metadata': metadata.loc[mask],
            }
            print(f"   ? {split_name}: {len(splits[split_name]['X'])} rows, {int(splits[split_name]['y'].sum())} anomalias")
        if len(splits['baseline_train']['X']) == 0 or len(splits['threshold_validation']['X']) == 0 or len(splits['novelty_test']['X']) == 0:
            raise RuntimeError('Split de novelty detection incompleto.')
        return splits

    def select_best_iforest_novelty(self, novelty_split):
        print("\n4.1. Afinando Isolation Forest no protocolo novelty-by-scenario...")
        best = None
        x_train = novelty_split['baseline_train']['X']
        y_train = novelty_split['baseline_train']['y']
        x_validation = novelty_split['threshold_validation']['X']
        y_validation = novelty_split['threshold_validation']['y']
        x_test = novelty_split['novelty_test']['X']
        y_test = novelty_split['novelty_test']['y']
        for config in self.get_iforest_candidates(x_train):
            print(f"   -> IF novelty config: {config}")
            bundle = self.build_iforest_bundle(x_train, y_train, config)
            validation_scores = self.score_iforest(bundle, x_validation)
            threshold_info = self.find_best_threshold(validation_scores, y_validation, self.get_iforest_threshold_candidates(validation_scores))
            val_metrics, _ = self.evaluate_scores(validation_scores, y_validation, threshold_info['threshold'], 'iforest_novelty_validation', log_metrics=False)
            test_scores = self.score_iforest(bundle, x_test)
            test_metrics, _ = self.evaluate_scores(test_scores, y_test, threshold_info['threshold'], 'iforest_novelty_test', log_metrics=False)
            candidate = {
                'config': config,
                'threshold': threshold_info['threshold'],
                'validation': val_metrics,
                'test': test_metrics,
            }
            key = (candidate['test']['f1_score'], candidate['validation']['f1_score'], candidate['test']['precision'], candidate['test']['recall'])
            if best is None or key > best['key']:
                best = {'candidate': candidate, 'key': key}
        print(f"   -> Melhor novelty config: {best['candidate']['config']}")
        return best['candidate']

    def build_holdout_split(self, x_data, y_data, metadata, train_size=0.6, validation_size=0.2):
        print("\n2. Criando holdout temporal...")
        n_rows = len(x_data)
        train_end = int(n_rows * train_size)
        validation_end = int(n_rows * (train_size + validation_size))
        splits = {
            "train": {"X": x_data.iloc[:train_end], "y": y_data.iloc[:train_end], "metadata": metadata.iloc[:train_end]},
            "validation": {"X": x_data.iloc[train_end:validation_end], "y": y_data.iloc[train_end:validation_end], "metadata": metadata.iloc[train_end:validation_end]},
            "test": {"X": x_data.iloc[validation_end:], "y": y_data.iloc[validation_end:], "metadata": metadata.iloc[validation_end:]},
        }
        for split_name, split in splits.items():
            print(f"   ✓ {split_name.capitalize():10s}: {len(split['X'])} ({split['y'].mean():.2%} anomalias, {int(split['y'].sum())} positivas)")
        return splits

    def build_backtest_splits(self, x_data, y_data, metadata, validation_frac=0.2, test_frac=0.1):
        print("\n3. Criando folds walk-forward...")
        n_rows = len(x_data)
        validation_size = int(n_rows * validation_frac)
        test_size = int(n_rows * test_frac)
        fold_starts = [0.4, 0.5, 0.6]
        folds = []
        for fold_idx, train_frac in enumerate(fold_starts, start=1):
            train_end = int(n_rows * train_frac)
            validation_end = train_end + validation_size
            test_end = validation_end + test_size
            if test_end > n_rows:
                continue
            fold = {
                "name": f"fold_{fold_idx}",
                "train": {"X": x_data.iloc[:train_end], "y": y_data.iloc[:train_end], "metadata": metadata.iloc[:train_end]},
                "validation": {"X": x_data.iloc[train_end:validation_end], "y": y_data.iloc[train_end:validation_end], "metadata": metadata.iloc[train_end:validation_end]},
                "test": {"X": x_data.iloc[validation_end:test_end], "y": y_data.iloc[validation_end:test_end], "metadata": metadata.iloc[validation_end:test_end]},
            }
            val_pos = int(fold["validation"]["y"].sum())
            test_pos = int(fold["test"]["y"].sum())
            if val_pos == 0 or test_pos == 0:
                print(f"   ! {fold['name']} ignorado: validation={val_pos}, test={test_pos}")
                continue
            print(f"   ✓ {fold['name']}: train={len(fold['train']['X'])}, validation={len(fold['validation']['X'])} ({val_pos} anomalias), test={len(fold['test']['X'])} ({test_pos} anomalias)")
            folds.append(fold)
        if not folds:
            raise RuntimeError("Nao foi possivel criar folds walk-forward com anomalias suficientes.")
        return folds


    def get_iforest_feature_sets(self, x_frame):
        groups = {
            'all_features': list(x_frame.columns),
            'behavioral_core': ['response_time_ms', 'requests_per_ip_5min', 'unique_endpoints_5min', 'failed_requests_ratio_5min', 'avg_response_time_5min', 'max_response_time_5min', 'request_rate_5min', 'endpoint_length', 'query_param_count', 'endpoint_entropy', 'time_since_last_request', 'requests_per_minute'],
            'traffic_shape': ['status_code', 'response_time_ms', 'requests_per_ip_5min', 'unique_endpoints_5min', 'failed_requests_ratio_5min', 'avg_response_time_5min', 'max_response_time_5min', 'request_rate_5min', 'time_since_last_request', 'requests_per_minute'],
            'endpoint_temporal': ['status_code', 'hour_of_day', 'day_of_week', 'is_night', 'endpoint_length', 'has_query_params', 'query_param_count', 'endpoint_entropy'],
        }
        resolved = {}
        for name, cols in groups.items():
            available = [col for col in cols if col in x_frame.columns]
            if len(available) >= 4:
                resolved[name] = available
        if 'all_features' not in resolved:
            resolved['all_features'] = list(x_frame.columns)
        return resolved

    def prepare_iforest_features(self, x_frame, feature_names, scaler=None, fit=False):
        selected = x_frame[feature_names].copy().replace([np.inf, -np.inf], np.nan)
        selected = selected.fillna(selected.median(numeric_only=True))
        if selected.isna().any().any():
            selected = selected.fillna(0.0)
        if fit:
            scaler = StandardScaler()
            return scaler.fit_transform(selected), scaler
        return scaler.transform(selected)

    def get_iforest_threshold_candidates(self, scores):
        series = pd.Series(scores, dtype=float)
        return [float(series.quantile(q)) for q in self.IFOREST_THRESHOLD_QUANTILES] + np.linspace(float(series.min()), float(series.max()), num=25).tolist()

    def build_iforest_bundle(self, x_train, y_train, config):
        feature_names = self.get_iforest_feature_sets(x_train)[config['feature_set']]
        x_normal = x_train.loc[y_train == 0, feature_names]
        x_scaled, scaler = self.prepare_iforest_features(x_normal, feature_names, fit=True)
        model = self.fit_iforest(x_scaled, config['n_estimators'], config['max_samples'], config['max_features'], config['bootstrap'])
        return {'model': model, 'scaler': scaler, 'feature_names': feature_names, 'config': config}

    def normalize_scores(self, scores):
        scores = pd.Series(scores, dtype=float)
        min_value = scores.min()
        max_value = scores.max()
        return ((scores - min_value) / (max_value - min_value + 1e-9)).to_numpy()

    def evaluate_scores(self, scores, y_true, threshold, split_name, log_metrics=True):
        print(f"\n5. Avaliando modelo em {split_name}...")
        print(f"   ✓ Threshold calibrado: {threshold:.6f}")
        y_pred = (scores >= threshold).astype(int)
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1_value = f1_score(y_true, y_pred, zero_division=0)
        try:
            roc_auc = roc_auc_score(y_true, scores)
        except Exception:
            roc_auc = 0.5
        metrics = {
            "precision": precision,
            "recall": recall,
            "f1_score": f1_value,
            "roc_auc": roc_auc,
            "accuracy": float((y_pred == y_true).mean()),
            "positives": int(y_true.sum()),
            "predicted_positives": int(y_pred.sum()),
        }
        if log_metrics:
            for metric_name, metric_value in metrics.items():
                mlflow.log_metric(f"{split_name}_{metric_name}", metric_value)
            mlflow.log_metric(f"{split_name}_threshold", threshold)
        print(f"\n   METRICAS ({split_name.upper()}):")
        print(f"   ├─ Precision: {precision:.3f}")
        print(f"   ├─ Recall:    {recall:.3f}")
        print(f"   ├─ F1-score:  {f1_value:.3f}")
        print(f"   ├─ ROC-AUC:   {roc_auc:.3f}")
        print(f"   └─ Accuracy:  {metrics['accuracy']:.3f}")
        cm = confusion_matrix(y_true, y_pred)
        print(f"\n   CONFUSION MATRIX ({split_name.upper()}):")
        print(f"   TN={cm[0,0]:4d}  FP={cm[0,1]:4d}")
        print(f"   FN={cm[1,0]:4d}  TP={cm[1,1]:4d}")
        print(f"\n{classification_report(y_true, y_pred, target_names=['Normal', 'Anomalia'])}")
        return metrics, y_pred

    def find_best_threshold(self, scores, y_true, thresholds):
        best = None
        for threshold in thresholds:
            y_pred = (scores >= threshold).astype(int)
            precision = precision_score(y_true, y_pred, zero_division=0)
            recall = recall_score(y_true, y_pred, zero_division=0)
            f1_value = f1_score(y_true, y_pred, zero_division=0)
            candidate = (f1_value, precision, recall, -threshold)
            if best is None or candidate > best["key"]:
                best = {"threshold": float(threshold), "precision": precision, "recall": recall, "f1_score": f1_value, "key": candidate}
        return best

    def fit_iforest(self, x_train_normal, n_estimators, max_samples, max_features, bootstrap):
        model = IsolationForest(contamination='auto', n_estimators=n_estimators, max_samples=max_samples, max_features=max_features, bootstrap=bootstrap, random_state=42, n_jobs=-1)
        model.fit(x_train_normal)
        return model

    def fit_random_forest(self, x_train, y_train, n_estimators, class_weight):
        model = RandomForestClassifier(n_estimators=n_estimators, random_state=42, n_jobs=-1, class_weight=class_weight)
        model.fit(x_train, y_train)
        return model

    def get_iforest_candidates(self, x_frame):
        feature_sets = self.get_iforest_feature_sets(x_frame)
        base_configs = [
            {'n_estimators': 200, 'max_samples': 'auto', 'max_features': 1.0, 'bootstrap': False},
            {'n_estimators': 300, 'max_samples': 'auto', 'max_features': 0.8, 'bootstrap': False},
            {'n_estimators': 400, 'max_samples': 256, 'max_features': 0.7, 'bootstrap': False},
            {'n_estimators': 400, 'max_samples': 256, 'max_features': 1.0, 'bootstrap': True},
            {'n_estimators': 500, 'max_samples': 512, 'max_features': 0.8, 'bootstrap': True},
        ]
        return [{'feature_set': feature_set, **config} for feature_set in feature_sets for config in base_configs]

    def get_rf_candidates(self):
        return [
            {"n_estimators": 300, "class_weight": None, "thresholds": [0.4, 0.45, 0.5, 0.55, 0.6]},
            {"n_estimators": 300, "class_weight": 'balanced_subsample', "thresholds": [0.2, 0.25, 0.3, 0.35, 0.4]},
            {"n_estimators": 500, "class_weight": 'balanced_subsample', "thresholds": [0.2, 0.25, 0.3, 0.35]},
        ]

    def score_iforest(self, bundle, x_eval):
        transformed = self.prepare_iforest_features(x_eval, bundle['feature_names'], scaler=bundle['scaler'], fit=False)
        return -bundle['model'].decision_function(transformed)

    def score_rf(self, model, x_eval):
        return model.predict_proba(x_eval)[:, 1]

    def select_best_iforest(self, folds):
        print("\n4. Afinando Isolation Forest com pipeline proprio de novelty detection...")
        best = None
        for config in self.get_iforest_candidates(folds[0]['train']['X']):
            print(f"   -> IF config: {config}")
            validation_metrics = []
            test_metrics = []
            thresholds = []
            for fold in folds:
                bundle = self.build_iforest_bundle(fold['train']['X'], fold['train']['y'], config)
                validation_scores = self.score_iforest(bundle, fold['validation']['X'])
                threshold_info = self.find_best_threshold(validation_scores, fold['validation']['y'], self.get_iforest_threshold_candidates(validation_scores))
                val_metrics, _ = self.evaluate_scores(validation_scores, fold['validation']['y'], threshold_info['threshold'], f"if_{fold['name']}_validation", log_metrics=False)
                test_scores_fold = self.score_iforest(bundle, fold['test']['X'])
                test_metrics_fold, _ = self.evaluate_scores(test_scores_fold, fold['test']['y'], threshold_info['threshold'], f"if_{fold['name']}_test", log_metrics=False)
                validation_metrics.append(val_metrics)
                test_metrics.append(test_metrics_fold)
                thresholds.append(threshold_info['threshold'])
            candidate = {
                'model_type': 'iforest',
                'config': config,
                'threshold': sum(thresholds) / len(thresholds),
                'validation': {'f1_score': sum(m['f1_score'] for m in validation_metrics) / len(validation_metrics), 'precision': sum(m['precision'] for m in validation_metrics) / len(validation_metrics), 'recall': sum(m['recall'] for m in validation_metrics) / len(validation_metrics)},
                'backtest_test': {'f1_score': sum(m['f1_score'] for m in test_metrics) / len(test_metrics), 'precision': sum(m['precision'] for m in test_metrics) / len(test_metrics), 'recall': sum(m['recall'] for m in test_metrics) / len(test_metrics)},
            }
            key = (candidate['validation']['f1_score'], candidate['backtest_test']['f1_score'], candidate['validation']['precision'], candidate['validation']['recall'])
            if best is None or key > best['key']:
                best = {'candidate': candidate, 'key': key}
        print(f"   -> Melhor IF config: {best['candidate']['config']}")
        return best['candidate']

    def select_best_rf(self, folds):
        print("\n4. Afinando RandomForest supervisionado...")
        best = None
        for config in self.get_rf_candidates():
            print(f"   → RF config: {config}")
            validation_metrics = []
            test_metrics = []
            thresholds = []
            for fold in folds:
                model = self.fit_random_forest(fold['train']['X'], fold['train']['y'], config['n_estimators'], config['class_weight'])
                validation_scores = self.score_rf(model, fold['validation']['X'])
                threshold_info = self.find_best_threshold(validation_scores, fold['validation']['y'], config['thresholds'])
                val_metrics, _ = self.evaluate_scores(validation_scores, fold['validation']['y'], threshold_info['threshold'], f"rf_{fold['name']}_validation", log_metrics=False)
                test_scores_fold = self.score_rf(model, fold['test']['X'])
                test_metrics_fold, _ = self.evaluate_scores(test_scores_fold, fold['test']['y'], threshold_info['threshold'], f"rf_{fold['name']}_test", log_metrics=False)
                validation_metrics.append(val_metrics)
                test_metrics.append(test_metrics_fold)
                thresholds.append(threshold_info['threshold'])
            candidate = {
                "model_type": "rf",
                "config": {"n_estimators": config['n_estimators'], "class_weight": config['class_weight']},
                "threshold": sum(thresholds) / len(thresholds),
                "validation": {
                    "f1_score": sum(m['f1_score'] for m in validation_metrics) / len(validation_metrics),
                    "precision": sum(m['precision'] for m in validation_metrics) / len(validation_metrics),
                    "recall": sum(m['recall'] for m in validation_metrics) / len(validation_metrics),
                },
                "backtest_test": {
                    "f1_score": sum(m['f1_score'] for m in test_metrics) / len(test_metrics),
                    "precision": sum(m['precision'] for m in test_metrics) / len(test_metrics),
                    "recall": sum(m['recall'] for m in test_metrics) / len(test_metrics),
                },
            }
            key = (candidate['validation']['f1_score'], candidate['validation']['precision'], candidate['validation']['recall'], candidate['backtest_test']['f1_score'])
            if best is None or key > best['key']:
                best = {"candidate": candidate, "key": key}
        return best['candidate']

    def select_best_ensemble(self, rf_folds, if_folds, best_rf, best_iforest):
        print("\n4. Afinando ensemble ponderado RF + IF...")
        best = None
        alpha_values = [0.6, 0.7, 0.8, 0.9]
        threshold_values = [x / 100 for x in range(30, 76, 5)]
        for alpha in alpha_values:
            print(f"   → Ensemble alpha_rf={alpha:.2f}")
            validation_metrics = []
            test_metrics = []
            thresholds = []
            for rf_fold, if_fold in zip(rf_folds, if_folds):
                if rf_fold['name'] != if_fold['name']:
                    raise RuntimeError('RF folds e IF folds nao estao alinhados')
                rf_model = self.fit_random_forest(rf_fold['train']['X'], rf_fold['train']['y'], best_rf['config']['n_estimators'], best_rf['config']['class_weight'])
                if_bundle = self.build_iforest_bundle(if_fold['train']['X'], if_fold['train']['y'], best_iforest['config'])
                validation_rf = self.score_rf(rf_model, rf_fold['validation']['X'])
                validation_if = self.normalize_scores(self.score_iforest(if_bundle, if_fold['validation']['X']))
                ensemble_validation = alpha * validation_rf + (1 - alpha) * validation_if
                threshold_info = self.find_best_threshold(ensemble_validation, rf_fold['validation']['y'], threshold_values)
                val_metrics, _ = self.evaluate_scores(ensemble_validation, rf_fold['validation']['y'], threshold_info['threshold'], f"ens_{rf_fold['name']}_validation", log_metrics=False)
                test_rf = self.score_rf(rf_model, rf_fold['test']['X'])
                test_if = self.normalize_scores(self.score_iforest(if_bundle, if_fold['test']['X']))
                ensemble_test = alpha * test_rf + (1 - alpha) * test_if
                test_metrics_fold, _ = self.evaluate_scores(ensemble_test, rf_fold['test']['y'], threshold_info['threshold'], f"ens_{rf_fold['name']}_test", log_metrics=False)
                validation_metrics.append(val_metrics)
                test_metrics.append(test_metrics_fold)
                thresholds.append(threshold_info['threshold'])
            candidate = {
                "model_type": "ensemble",
                "config": {"alpha_rf": alpha, "rf_config": best_rf['config'], "iforest_config": best_iforest['config']},
                "threshold": sum(thresholds) / len(thresholds),
                "validation": {
                    "f1_score": sum(m['f1_score'] for m in validation_metrics) / len(validation_metrics),
                    "precision": sum(m['precision'] for m in validation_metrics) / len(validation_metrics),
                    "recall": sum(m['recall'] for m in validation_metrics) / len(validation_metrics),
                },
                "backtest_test": {
                    "f1_score": sum(m['f1_score'] for m in test_metrics) / len(test_metrics),
                    "precision": sum(m['precision'] for m in test_metrics) / len(test_metrics),
                    "recall": sum(m['recall'] for m in test_metrics) / len(test_metrics),
                },
            }
            key = (candidate['validation']['f1_score'], candidate['backtest_test']['f1_score'], candidate['validation']['precision'], candidate['validation']['recall'])
            if best is None or key > best['key']:
                best = {"candidate": candidate, "key": key}
        return best['candidate']

    def evaluate_review_budget(self, scores, y_true, split_name, budgets=(0.01, 0.02, 0.05, 0.10), log_metrics=True):
        scores_series = pd.Series(scores, dtype=float)
        y_series = pd.Series(y_true).reset_index(drop=True)
        ranked_index = scores_series.sort_values(ascending=False).index.to_list()
        total_rows = len(y_series)
        total_anomalies = int(y_series.sum())
        results = {}
        print(f"\n6. Avaliando novelty review budgets em {split_name}...")
        for budget in budgets:
            top_k = max(1, int(total_rows * budget))
            selected = ranked_index[:top_k]
            hits = int(y_series.iloc[selected].sum())
            precision_at_k = hits / top_k
            recall_at_k = hits / total_anomalies if total_anomalies else 0.0
            key = f"top_{int(budget * 100)}pct"
            results[key] = {
                "budget": budget,
                "top_k": top_k,
                "hits": hits,
                "precision_at_k": precision_at_k,
                "recall_at_k": recall_at_k,
            }
            if log_metrics:
                mlflow.log_metric(f"{split_name}_{key}_precision", precision_at_k)
                mlflow.log_metric(f"{split_name}_{key}_recall", recall_at_k)
                mlflow.log_metric(f"{split_name}_{key}_hits", hits)
            print(f"   - {key}: top_k={top_k}, hits={hits}, precision={precision_at_k:.3f}, recall={recall_at_k:.3f}")
        return results

    def evaluate_iforest_only_cases(self, if_pred, rf_pred, y_true, split_name, log_metrics=True):
        if_only_mask = (np.asarray(if_pred) == 1) & (np.asarray(rf_pred) == 0)
        reviewed = int(if_only_mask.sum())
        hits = int(np.asarray(y_true)[if_only_mask].sum()) if reviewed else 0
        precision = (hits / reviewed) if reviewed else 0.0
        coverage = (hits / int(np.asarray(y_true).sum())) if int(np.asarray(y_true).sum()) else 0.0
        results = {
            "reviewed": reviewed,
            "hits": hits,
            "precision": precision,
            "anomaly_coverage": coverage,
        }
        if log_metrics:
            mlflow.log_metric(f"{split_name}_iforest_only_reviewed", reviewed)
            mlflow.log_metric(f"{split_name}_iforest_only_hits", hits)
            mlflow.log_metric(f"{split_name}_iforest_only_precision", precision)
            mlflow.log_metric(f"{split_name}_iforest_only_coverage", coverage)
        print(f"\n6. Casos exclusivos do IsolationForest em {split_name}: reviewed={reviewed}, hits={hits}, precision={precision:.3f}, coverage={coverage:.3f}")
        return results

    def save_confusion_matrix(self, y_true, y_pred, filename):
        output_dir = Path("experiments")
        output_dir.mkdir(parents=True, exist_ok=True)
        cm = confusion_matrix(y_true, y_pred)
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", xticklabels=["Normal", "Anomalia"], yticklabels=["Normal", "Anomalia"])
        plt.title("Confusion Matrix")
        plt.ylabel("True Label")
        plt.xlabel("Predicted Label")
        plt.tight_layout()
        filepath = output_dir / filename
        plt.savefig(filepath, dpi=150)
        plt.close()
        mlflow.log_artifact(str(filepath))
        print(f"   ✓ Confusion matrix saved: {filepath}")

    def save_pickle_with_metadata(self, object_to_save, metadata, model_name):
        models_dir = Path("models")
        models_dir.mkdir(parents=True, exist_ok=True)
        model_path = models_dir / f"{model_name}.pkl"
        with open(model_path, "wb") as handle:
            pickle.dump(object_to_save, handle)
        metadata_path = models_dir / f"{model_name}_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        mlflow.log_artifact(str(metadata_path))
        print(f"   ✓ Local: {model_path}")
        print(f"   ✓ Metadata: {metadata_path}")
        return model_path

    def run_experiment(self, experiment_name="exp_hybrid_temporal_validation"):
        print("=" * 70)
        print(f"EXPERIMENTO: {experiment_name}")
        print("=" * 70)
        x_data, x_iforest, y_data, metadata = self.load_data()
        holdout = self.build_holdout_split(x_data, y_data, metadata)
        holdout_if = self.build_holdout_split(x_iforest, y_data, metadata)
        novelty_split = self.build_novelty_protocol_split(x_iforest, y_data, metadata)
        folds = self.build_backtest_splits(x_data, y_data, metadata)
        folds_if = self.build_backtest_splits(x_iforest, y_data, metadata)
        if mlflow.active_run() is not None:
            mlflow.end_run()
        with mlflow.start_run(run_name=experiment_name):
            mlflow.log_param("split_strategy", "walk_forward_backtesting_plus_holdout")
            best_iforest = self.select_best_iforest(folds_if)
            novelty_iforest = self.select_best_iforest_novelty(novelty_split)
            best_rf = self.select_best_rf(folds)
            best_ensemble = self.select_best_ensemble(folds, folds_if, best_rf, best_iforest)
            mlflow.log_param("iforest_feature_set", best_iforest['config']['feature_set'])
            mlflow.log_param("iforest_novelty_feature_set", novelty_iforest['config']['feature_set'])
            mlflow.log_metric("iforest_backtest_validation_f1_mean", best_iforest['validation']['f1_score'])
            mlflow.log_metric("iforest_backtest_test_f1_mean", best_iforest['backtest_test']['f1_score'])
            mlflow.log_metric("iforest_novelty_validation_f1", novelty_iforest['validation']['f1_score'])
            mlflow.log_metric("iforest_novelty_test_f1", novelty_iforest['test']['f1_score'])
            mlflow.log_metric("random_forest_backtest_validation_f1_mean", best_rf['validation']['f1_score'])
            mlflow.log_metric("random_forest_backtest_test_f1_mean", best_rf['backtest_test']['f1_score'])
            mlflow.log_metric("ensemble_backtest_validation_f1_mean", best_ensemble['validation']['f1_score'])
            mlflow.log_metric("ensemble_backtest_test_f1_mean", best_ensemble['backtest_test']['f1_score'])

            rf_model = self.fit_random_forest(holdout['train']['X'], holdout['train']['y'], best_rf['config']['n_estimators'], best_rf['config']['class_weight'])
            if_bundle = self.build_iforest_bundle(holdout_if['train']['X'], holdout_if['train']['y'], best_iforest['config'])

            val_if_scores_raw = self.score_iforest(if_bundle, holdout_if['validation']['X'])
            val_if_scores = self.normalize_scores(val_if_scores_raw)
            test_if_scores_raw = self.score_iforest(if_bundle, holdout_if['test']['X'])
            test_if_scores = self.normalize_scores(test_if_scores_raw)
            val_rf_scores = self.score_rf(rf_model, holdout['validation']['X'])
            test_rf_scores = self.score_rf(rf_model, holdout['test']['X'])

            if_val_threshold = self.find_best_threshold(val_if_scores_raw, holdout['validation']['y'], self.get_iforest_threshold_candidates(val_if_scores_raw))
            rf_val_threshold = self.find_best_threshold(val_rf_scores, holdout['validation']['y'], [0.4, 0.45, 0.5, 0.55, 0.6])
            ensemble_val_scores = best_ensemble['config']['alpha_rf'] * val_rf_scores + (1 - best_ensemble['config']['alpha_rf']) * val_if_scores
            ensemble_val_threshold = self.find_best_threshold(ensemble_val_scores, holdout['validation']['y'], [x / 100 for x in range(30, 76, 5)])

            if_validation_metrics, if_val_pred = self.evaluate_scores(val_if_scores_raw, holdout_if['validation']['y'], if_val_threshold['threshold'], 'iforest_holdout_validation', log_metrics=True)
            if_test_metrics, if_y_pred = self.evaluate_scores(test_if_scores_raw, holdout_if['test']['y'], if_val_threshold['threshold'], 'iforest_holdout_test', log_metrics=True)
            rf_validation_metrics, rf_val_pred = self.evaluate_scores(val_rf_scores, holdout['validation']['y'], rf_val_threshold['threshold'], 'random_forest_holdout_validation', log_metrics=True)
            rf_test_metrics, rf_y_pred = self.evaluate_scores(test_rf_scores, holdout['test']['y'], rf_val_threshold['threshold'], 'random_forest_holdout_test', log_metrics=True)
            ensemble_test_scores = best_ensemble['config']['alpha_rf'] * test_rf_scores + (1 - best_ensemble['config']['alpha_rf']) * test_if_scores
            ensemble_validation_metrics, _ = self.evaluate_scores(ensemble_val_scores, holdout['validation']['y'], ensemble_val_threshold['threshold'], 'ensemble_holdout_validation', log_metrics=True)
            ensemble_test_metrics, ensemble_y_pred = self.evaluate_scores(ensemble_test_scores, holdout['test']['y'], ensemble_val_threshold['threshold'], 'ensemble_holdout_test', log_metrics=True)

            if_review_validation = self.evaluate_review_budget(val_if_scores_raw, holdout_if['validation']['y'], 'iforest_holdout_validation_review', log_metrics=True)
            if_review_test = self.evaluate_review_budget(test_if_scores_raw, holdout_if['test']['y'], 'iforest_holdout_test_review', log_metrics=True)
            if_only_validation = self.evaluate_iforest_only_cases(if_val_pred, rf_val_pred, holdout['validation']['y'], 'iforest_holdout_validation', log_metrics=True)
            if_only_test = self.evaluate_iforest_only_cases(if_y_pred, rf_y_pred, holdout['test']['y'], 'iforest_holdout_test', log_metrics=True)

            novelty_bundle = self.build_iforest_bundle(novelty_split['baseline_train']['X'], novelty_split['baseline_train']['y'], novelty_iforest['config'])
            novelty_validation_scores = self.score_iforest(novelty_bundle, novelty_split['threshold_validation']['X'])
            novelty_test_scores = self.score_iforest(novelty_bundle, novelty_split['novelty_test']['X'])
            novelty_validation_metrics, novelty_val_pred = self.evaluate_scores(novelty_validation_scores, novelty_split['threshold_validation']['y'], novelty_iforest['threshold'], 'iforest_protocol_validation', log_metrics=True)
            novelty_test_metrics, novelty_test_pred = self.evaluate_scores(novelty_test_scores, novelty_split['novelty_test']['y'], novelty_iforest['threshold'], 'iforest_protocol_test', log_metrics=True)
            novelty_review_validation = self.evaluate_review_budget(novelty_validation_scores, novelty_split['threshold_validation']['y'], 'iforest_protocol_validation_review', log_metrics=True)
            novelty_review_test = self.evaluate_review_budget(novelty_test_scores, novelty_split['novelty_test']['y'], 'iforest_protocol_test_review', log_metrics=True)

            self.save_confusion_matrix(holdout['test']['y'], rf_y_pred, 'confusion_matrix_random_forest.png')
            self.save_confusion_matrix(holdout['test']['y'], if_y_pred, 'confusion_matrix_isolation_forest.png')
            self.save_confusion_matrix(holdout['test']['y'], ensemble_y_pred, 'confusion_matrix_ensemble.png')
            novelty_report_path = Path('experiments') / 'iforest_novelty_report.json'
            novelty_report_path.write_text(json.dumps({
                'validation_review_budgets': if_review_validation,
                'test_review_budgets': if_review_test,
                'validation_iforest_only': if_only_validation,
                'test_iforest_only': if_only_test,
                'protocol_validation_metrics': novelty_validation_metrics,
                'protocol_test_metrics': novelty_test_metrics,
                'protocol_validation_review_budgets': novelty_review_validation,
                'protocol_test_review_budgets': novelty_review_test,
                'protocol_config': novelty_iforest['config'],
                'protocol_threshold': novelty_iforest['threshold'],
            }, indent=2), encoding='utf-8')
            mlflow.log_artifact(str(novelty_report_path))

            reliable_test = int(holdout['test']['y'].sum()) >= self.MIN_RELIABLE_ANOMALIES
            mlflow.log_param('holdout_test_reliable', reliable_test)

            deployment_x = pd.concat([holdout['train']['X'], holdout['validation']['X']])
            deployment_y = pd.concat([holdout['train']['y'], holdout['validation']['y']])
            deployment_rf = self.fit_random_forest(deployment_x, deployment_y, best_rf['config']['n_estimators'], best_rf['config']['class_weight'])
            deployment_if = self.build_iforest_bundle(pd.concat([holdout_if['train']['X'], holdout_if['validation']['X']]), deployment_y, best_iforest['config'])

            self.save_pickle_with_metadata(deployment_rf, {"threshold": rf_val_threshold['threshold'], "saved_at": datetime.now().isoformat(), "tracking_uri": self.mlflow_uri, "model_family": "random_forest"}, 'random_forest_latest')
            self.save_pickle_with_metadata(deployment_if, {"threshold": if_val_threshold['threshold'], "saved_at": datetime.now().isoformat(), "tracking_uri": self.mlflow_uri, "model_family": "isolation_forest", "train_on_normals_only": True, "feature_set": best_iforest['config']['feature_set'], "feature_names": deployment_if['feature_names']}, 'isolation_forest_latest')
            ensemble_bundle = {
                "alpha_rf": best_ensemble['config']['alpha_rf'],
                "rf_model_path": 'models/random_forest_latest.pkl',
                "iforest_model_path": 'models/isolation_forest_latest.pkl',
                "iforest_feature_set": best_iforest['config']['feature_set'],
            }
            self.save_pickle_with_metadata(ensemble_bundle, {"threshold": ensemble_val_threshold['threshold'], "saved_at": datetime.now().isoformat(), "tracking_uri": self.mlflow_uri, "model_family": "hybrid_ensemble", "alpha_rf": best_ensemble['config']['alpha_rf']}, 'hybrid_ensemble_latest')
            mlflow.log_param('model_promoted', reliable_test)

            print("\n" + "=" * 70)
            print("✓ EXPERIMENTO COMPLETO!")
            print(f"✓ Isolation Forest holdout F1: {if_test_metrics['f1_score']:.3f}")
            print(f"✓ RandomForest holdout F1: {rf_test_metrics['f1_score']:.3f}")
            print(f"✓ Ensemble holdout F1: {ensemble_test_metrics['f1_score']:.3f}")
            print("=" * 70)
            return {
                "best_iforest": best_iforest,
                "best_random_forest": best_rf,
                "best_ensemble": best_ensemble,
                "iforest_holdout_validation": if_validation_metrics,
                "iforest_holdout_test": if_test_metrics,
                "random_forest_holdout_validation": rf_validation_metrics,
                "random_forest_holdout_test": rf_test_metrics,
                "ensemble_holdout_validation": ensemble_validation_metrics,
                "ensemble_holdout_test": ensemble_test_metrics,
                "iforest_review_validation": if_review_validation,
                "iforest_review_test": if_review_test,
                "iforest_only_validation": if_only_validation,
                "iforest_only_test": if_only_test,
                "iforest_protocol_validation": novelty_validation_metrics,
                "iforest_protocol_test": novelty_test_metrics,
                "iforest_protocol_review_validation": novelty_review_validation,
                "iforest_protocol_review_test": novelty_review_test,
                "holdout_test_reliable": reliable_test,
            }


def main():
    trainer = ModelTrainer()
    results = trainer.run_experiment()
    summary = pd.DataFrame([
        {"Model": "IsolationForest", "Split": "Holdout Validation", "F1-Score": results['iforest_holdout_validation']['f1_score'], "Precision": results['iforest_holdout_validation']['precision'], "Recall": results['iforest_holdout_validation']['recall']},
        {"Model": "IsolationForest", "Split": "Holdout Test", "F1-Score": results['iforest_holdout_test']['f1_score'], "Precision": results['iforest_holdout_test']['precision'], "Recall": results['iforest_holdout_test']['recall']},
        {"Model": "RandomForest", "Split": "Holdout Validation", "F1-Score": results['random_forest_holdout_validation']['f1_score'], "Precision": results['random_forest_holdout_validation']['precision'], "Recall": results['random_forest_holdout_validation']['recall']},
        {"Model": "RandomForest", "Split": "Holdout Test", "F1-Score": results['random_forest_holdout_test']['f1_score'], "Precision": results['random_forest_holdout_test']['precision'], "Recall": results['random_forest_holdout_test']['recall']},
        {"Model": "Ensemble", "Split": "Holdout Validation", "F1-Score": results['ensemble_holdout_validation']['f1_score'], "Precision": results['ensemble_holdout_validation']['precision'], "Recall": results['ensemble_holdout_validation']['recall']},
        {"Model": "Ensemble", "Split": "Holdout Test", "F1-Score": results['ensemble_holdout_test']['f1_score'], "Precision": results['ensemble_holdout_test']['precision'], "Recall": results['ensemble_holdout_test']['recall']},
    ])
    print("\n" + "=" * 70)
    print("RESUMO FINAL")
    print("=" * 70)
    print(summary.to_string(index=False))
    print("\n✓ Ver detalhes no MLflow: http://localhost:5000")
    return summary


if __name__ == '__main__':
    results = main()
