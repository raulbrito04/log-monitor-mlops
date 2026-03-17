#!/usr/bin/env python3
"""
Feature Engineering Pipeline - Semana 5
Log Monitor MLOps Project

Extrai features de logs para machine learning:
- 15+ features base (numéricas, agregação, temporais, URL)
- Features avançadas (entropy, behavioral)
- Feature selection (correlation + RFE)
- Normalization (StandardScaler)
"""

import pandas as pd
import numpy as np
import psycopg2
from scipy.stats import entropy as shannon_entropy
from sklearn.feature_selection import RFE
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from dotenv import load_dotenv
import os
import pickle
import json
from datetime import datetime
import warnings

warnings.filterwarnings('ignore')
load_dotenv()


class FeatureEngineer:
    """Pipeline completo de feature engineering para anomaly detection"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
        self._setup_directories()
        self._connect_db()
    
    def _setup_directories(self):
        """Cria diretórios necessários"""
        for directory in ['data', 'models']:
            os.makedirs(directory, exist_ok=True)
        print("✓ Diretórios criados/verificados")
    
    def _connect_db(self):
        """Conecta ao PostgreSQL"""
        try:
            self.conn = psycopg2.connect(
                host="localhost",
                port=5432,
                database="logmonitor",
                user="postgres",
                password=os.getenv("POSTGRES_PASSWORD", "changeme")
            )
            self.cursor = self.conn.cursor()
            print("✓ Conectado ao PostgreSQL")
        except Exception as e:
            print(f"✗ Erro ao conectar PostgreSQL: {e}")
            raise
    
    def load_data(self, days=30):
        """
        Carrega logs dos últimos N dias
        
        Args:
            days: Número de dias para carregar (default: 7)
        
        Returns:
            DataFrame com logs
        """
        print(f"\n1. Carregando logs dos últimos {days} dias...")
        
        query = f"""
        SELECT 
            id,
            timestamp,
            ip,
            method,
            endpoint,
            status,
            response_time_ms,
            user_agent,
            data
        FROM raw_logs
        WHERE timestamp > NOW() - INTERVAL '{days} days'
        ORDER BY timestamp
        """
        
        try:
            df = pd.read_sql(query, self.conn)
            
            if len(df) == 0:
                raise ValueError(f"Nenhum log encontrado nos últimos {days} dias!")
            
            print(f"   ✓ {len(df):,} logs carregados")
            print(f"   ✓ Período: {df['timestamp'].min()} até {df['timestamp'].max()}")
            
            return df
            
        except Exception as e:
            print(f"   ✗ Erro ao carregar dados: {e}")
            raise
    
    def extract_features(self, df):
        """
        Pipeline completo de extração de features
        
        Args:
            df: DataFrame com logs brutos
        
        Returns:
            DataFrame com features extraídas
        """
        print("\n" + "="*70)
        print("FEATURE ENGINEERING PIPELINE")
        print("="*70 + "\n")
        
        # Cria cópia para não modificar original
        df = df.copy()
        
        # Pipeline de extração
        features = self._numeric_features(df)
        features = self._aggregation_features(df, features)
        features = self._temporal_features(df, features)
        features = self._url_features(df, features)
        features = self._entropy_features(df, features)
        features = self._behavioral_features(df, features)
        
        print(f"\n✓ Total de features extraídas: {len(features.columns)}")
        print(f"✓ Shape: {features.shape}")
        
        return features, df
    
    def _numeric_features(self, df):
        """Features numéricas diretas (2 features)"""
        print("2. Extraindo features numéricas...")
        
        features = pd.DataFrame({
            'status_code': df['status'].astype(float),
            'response_time_ms': df['response_time_ms'].astype(float)
        })
        
        print(f"   ✓ 2 features numéricas")
        return features
    
    def _aggregation_features(self, df, features):
        """Features de agregação por IP - janela 5min (6 features)"""
        print("3. Extraindo features de agregação (janela 5min)...")
        
        # Criar janela de 5 minutos
        df['time_window'] = pd.to_datetime(df['timestamp']).dt.floor('5min')
        
        # Agregações por IP + janela
        agg = df.groupby(['ip', 'time_window']).agg({
            'id': 'count',  # requests_per_ip_5min
            'endpoint': 'nunique',  # unique_endpoints_5min
            'status': lambda x: (x >= 400).sum() / len(x) if len(x) > 0 else 0,  # failed_ratio
            'response_time_ms': ['mean', 'max']
        }).reset_index()
        
        agg.columns = ['ip', 'time_window', 'requests_per_ip_5min', 
                      'unique_endpoints_5min', 'failed_requests_ratio_5min',
                      'avg_response_time_5min', 'max_response_time_5min']
        
        # Merge com dataframe original
        df = df.merge(agg, on=['ip', 'time_window'], how='left')
        
        # Request rate (requests/segundo)
        features['requests_per_ip_5min'] = df['requests_per_ip_5min'].fillna(1)
        features['unique_endpoints_5min'] = df['unique_endpoints_5min'].fillna(1)
        features['failed_requests_ratio_5min'] = df['failed_requests_ratio_5min'].fillna(0)
        features['avg_response_time_5min'] = df['avg_response_time_5min'].fillna(df['response_time_ms'])
        features['max_response_time_5min'] = df['max_response_time_5min'].fillna(df['response_time_ms'])
        features['request_rate_5min'] = features['requests_per_ip_5min'] / 300  # 5min = 300s
        
        print(f"   ✓ 6 features de agregação")
        return features
    
    def _temporal_features(self, df, features):
        """Features temporais (4 features)"""
        print("4. Extraindo features temporais...")
        
        timestamps = pd.to_datetime(df['timestamp'])
        
        features['hour_of_day'] = timestamps.dt.hour.astype(float)
        features['day_of_week'] = timestamps.dt.dayofweek.astype(float)  # 0=Monday
       # features['is_weekend'] = (timestamps.dt.dayofweek >= 5).astype(float)
        features['is_night'] = ((timestamps.dt.hour >= 22) | (timestamps.dt.hour < 6)).astype(float)
        
        print(f"   ✓ 4 features temporais")
        return features
    
    def _url_features(self, df, features):
        """Features de URL/endpoint (3 features)"""
        print("5. Extraindo features de URL...")
        
        features['endpoint_length'] = df['endpoint'].str.len().astype(float)
        features['has_query_params'] = df['endpoint'].str.contains(r'\?', regex=True).astype(float)
        features['query_param_count'] = (
            df['endpoint'].str.count('&').fillna(0) + 
            df['endpoint'].str.contains(r'\?', regex=True).astype(int)
        ).astype(float)
        
        print(f"   ✓ 3 features de URL")
        return features
    
    def _entropy_features(self, df, features):
        """Features de entropy (1 feature)"""
        print("6. Extraindo features de entropy...")
        
        def calculate_entropy(text):
            """Calcula Shannon entropy de uma string"""
            if not text or len(text) == 0:
                return 0.0
            
            # Conta frequência de cada caractere
            chars = list(text)
            if len(chars) == 0:
                return 0.0
                
            freq = np.array([chars.count(c) for c in set(chars)])
            freq = freq / freq.sum()
            
            # Shannon entropy
            return shannon_entropy(freq, base=2)
        
        features['endpoint_entropy'] = df['endpoint'].apply(calculate_entropy).astype(float)
        
        print(f"   ✓ 1 feature de entropy")
        return features
    
    def _behavioral_features(self, df, features):
        """Features comportamentais (2 features)"""
        print("7. Extraindo features comportamentais...")
        
        # Ordena por IP e timestamp
        df_sorted = df.sort_values(['ip', 'timestamp']).copy()
        
        # Tempo desde último request do mesmo IP
        df_sorted['time_diff'] = df_sorted.groupby('ip')['timestamp'].diff()
        df_sorted['time_since_last_request'] = df_sorted['time_diff'].dt.total_seconds()
        
        # Preenche NaN (primeiro request de cada IP) com mediana
        median_time = df_sorted['time_since_last_request'].median()
        df_sorted['time_since_last_request'].fillna(median_time, inplace=True)
        
        # Requests por minuto (rolling window)
        df_sorted['requests_per_minute'] = df_sorted.groupby('ip')['id'].transform(
            lambda x: x.rolling(window=min(60, len(x)), min_periods=1).count()
        )
        
        # Reordena de volta ao índice original
        df_sorted = df_sorted.sort_index()
        
        features['time_since_last_request'] = df_sorted['time_since_last_request'].astype(float)
        features['time_since_last_request'] = features['time_since_last_request'].fillna(999999)
        features['requests_per_minute'] = df_sorted['requests_per_minute'].astype(float)
        
        print(f"   ✓ 2 features comportamentais")
        return features
    
    def create_labels(self, df):
        """
        Cria labels baseados em alertas existentes
        
        Args:
            df: DataFrame com logs
        
        Returns:
            Array com labels (0=normal, 1=anomalia)
        """
        print("\n8. Criando labels a partir de alertas...")
        
        try:
            query = """
            SELECT DISTINCT UNNEST(log_ids) as log_id
            FROM alerts
            """
            alert_log_ids = pd.read_sql(query, self.conn)['log_id'].tolist()
            
            # Label: 1 se log está em alerta, 0 caso contrário
            labels = df['id'].isin(alert_log_ids).astype(int)
            
            anomaly_rate = labels.mean() * 100
            
            print(f"   ✓ Labels criados:")
            print(f"     • Anomalias: {labels.sum():,} ({anomaly_rate:.2f}%)")
            print(f"     • Normais: {(~labels.astype(bool)).sum():,} ({100-anomaly_rate:.2f}%)")
            
            if labels.sum() == 0:
                print("\n   ⚠️  WARNING: Nenhuma anomalia encontrada!")
                print("      Execute: python src/detection/rule_engine.py --mode historical --days 30")
                raise ValueError("Sem labels para treinar RFE!")
            
            if anomaly_rate < 1:
                print(f"\n   ⚠️  WARNING: Anomaly rate muito baixo ({anomaly_rate:.2f}%)")
                print("      Recomendado: > 1% para RFE robusto")
            
            return labels
            
        except Exception as e:
            print(f"   ✗ Erro ao criar labels: {e}")
            raise
    
    def remove_correlated_features(self, features, threshold=0.9):
        """
        Remove features com correlação > threshold
        
        Args:
            features: DataFrame com features
            threshold: Limite de correlação (default: 0.9)
        
        Returns:
            DataFrame sem features correlacionadas
        """
        print(f"\n9. Removendo features correlacionadas (threshold={threshold})...")
        
        # Calcular matriz de correlação
        corr_matrix = features.corr().abs()
        
        # Matriz triangular superior
        upper = corr_matrix.where(
            np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
        )
        
        # Features para remover
        to_drop = [column for column in upper.columns 
                   if any(upper[column] > threshold)]
        
        if len(to_drop) > 0:
            print(f"   ✓ Features altamente correlacionadas: {to_drop}")
            print(f"   ✓ Removendo {len(to_drop)} features")
            features = features.drop(columns=to_drop)
        else:
            print(f"   ✓ Nenhuma feature com correlação > {threshold}")
        
        print(f"   ✓ Features restantes: {len(features.columns)}")
        
        return features
    
    def select_best_features(self, features, labels, n_features=20):
        """
        Seleciona top N features usando RFE
        
        Args:
            features: DataFrame com features
            labels: Array com labels
            n_features: Número de features a selecionar
        
        Returns:
            Tuple (features_selecionadas, nomes_colunas)
        """
        print(f"\n10. Seleção de features com RFE (top {n_features})...")
        
        # Ajusta n_features se necessário
        n_features = min(n_features, len(features.columns))
        
        # Random Forest como estimador
        estimator = RandomForestClassifier(
            n_estimators=100,
            random_state=42,
            n_jobs=-1,
            class_weight='balanced'  # Importante para label imbalance
        )
        
        # RFE
        print("   → Executando RFE (pode demorar 30-60s)...")
        selector = RFE(
            estimator=estimator,
            n_features_to_select=n_features,
            step=1,
            verbose=0
        )
        
        try:
            selector.fit(features, labels)
        except Exception as e:
            print(f"   ✗ Erro no RFE: {e}")
            raise
        
        # Features selecionadas
        selected_features = features.columns[selector.support_].tolist()
        
        print(f"\n   ✓ Features selecionadas ({len(selected_features)}):")
        for i, feat in enumerate(selected_features, 1):
            ranking = selector.ranking_[features.columns.get_loc(feat)]
            print(f"      {i:2d}. {feat:30s} (rank: {ranking})")
        
        # Guardar selector
        with open('models/feature_selector.pkl', 'wb') as f:
            pickle.dump(selector, f)
        print("\n   ✓ Selector salvo: models/feature_selector.pkl")
        
        return features[selected_features], selected_features
    
    def normalize_features(self, features):
        """
        Normaliza features com StandardScaler
        
        Args:
            features: DataFrame com features
        
        Returns:
            Tuple (features_normalizadas, scaler)
        """
        print("\n11. Normalizando features...")
        
        scaler = StandardScaler()
        features_scaled = pd.DataFrame(
            scaler.fit_transform(features),
            columns=features.columns,
            index=features.index
        )
        
        # Guardar scaler
        with open('models/scaler.pkl', 'wb') as f:
            pickle.dump(scaler, f)
        
        print("   ✓ Features normalizadas (StandardScaler)")
        print("   ✓ Scaler salvo: models/scaler.pkl")
        
        return features_scaled, scaler
    
    def save_artifacts(self, df_original, features_final, labels, selected_cols):
        """
        Guarda todos os artefactos
        
        Args:
            df_original: DataFrame original com logs
            features_final: Features finais normalizadas
            labels: Labels
            selected_cols: Nomes das colunas selecionadas
        """
        print("\n12. Salvando artefactos...")
        
        # Dataset completo
        dataset = features_final.copy()
        dataset['label'] = labels.values
        dataset['log_id'] = df_original['id'].values
        dataset['timestamp'] = df_original['timestamp'].values
        
        # CSV
        dataset.to_csv('data/ml_dataset.csv', index=False)
        print("   ✓ data/ml_dataset.csv")
        
        # Pickle (mais rápido para ML)
        dataset.to_pickle('data/ml_dataset.pkl')
        print("   ✓ data/ml_dataset.pkl")
        
        # Feature names
        with open('data/selected_features.txt', 'w') as f:
            f.write('\n'.join(selected_cols))
        print("   ✓ data/selected_features.txt")
        
        # Summary
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_logs': len(df_original),
            'total_features_extracted': 19,
            'total_features_selected': len(selected_cols),
            'anomalies': int(labels.sum()),
            'anomaly_rate': f"{100*labels.mean():.2f}%",
            'selected_features': selected_cols
        }
        
        with open('data/feature_summary.json', 'w') as f:
            json.dump(summary, f, indent=2)
        print("   ✓ data/feature_summary.json")
        
        print(f"\n   ✓ Dataset final shape: {dataset.shape}")
    
    def run_pipeline(self, days=30, n_features_final=20):
        """
        Pipeline completo end-to-end
        
        Args:
            days: Dias para carregar (default: 7)
            n_features_final: Número de features finais (default: 20)
        
        Returns:
            Tuple (features_scaled, labels)
        """
        print("="*70)
        print("FEATURE ENGINEERING PIPELINE - PLANO A+")
        print("Semana 5 - Log Monitor MLOps")
        print("="*70)
        
        try:
            # 1. Load data
            df = self.load_data(days)
            
            # 2. Extract all features
            features, df_with_windows = self.extract_features(df)
            
            # 3. Create labels
            labels = self.create_labels(df)
            
            # 4. Remove correlação
            features = self.remove_correlated_features(features)
            
            # 5. RFE - selecionar top features
            features_selected, selected_cols = self.select_best_features(
                features, labels, n_features=n_features_final
            )
            
            # 6. Normalize
            features_final, scaler = self.normalize_features(features_selected)
            
            # 7. Save
            self.save_artifacts(df, features_final, labels, selected_cols)
            
            print("\n" + "="*70)
            print("✓ PIPELINE COMPLETO COM SUCESSO!")
            print("="*70)
            print(f"\nArtefactos criados:")
            print("  • data/ml_dataset.pkl (dataset final)")
            print("  • data/ml_dataset.csv (versão CSV)")
            print("  • models/scaler.pkl (StandardScaler)")
            print("  • models/feature_selector.pkl (RFE)")
            print("  • data/selected_features.txt (lista de features)")
            print("  • data/feature_summary.json (metadados)")
            
            print(f"\nPróximo passo:")
            print("  → Semana 6: Model Training (Isolation Forest)")
            
            return features_final, labels
            
        except Exception as e:
            print(f"\n✗ ERRO NO PIPELINE: {e}")
            raise
        
        finally:
            if self.conn:
                self.conn.close()
                print("\n✓ Conexão PostgreSQL fechada")


def main():
    """Função principal"""
    try:
        fe = FeatureEngineer()
        features, labels = fe.run_pipeline(days=30, n_features_final=20)
        
        print(f"\n{'='*70}")
        print("RESUMO FINAL")
        print(f"{'='*70}")
        print(f"Shape final: {features.shape}")
        print(f"Features: {list(features.columns)[:5]}... (+{len(features.columns)-5} more)")
        print(f"Anomaly rate: {100*labels.mean():.2f}%")
        print(f"\n✓ Tudo pronto para Semana 6! 🚀")
        
    except Exception as e:
        print(f"\n✗ Falha: {e}")
        print("\nTroubleshooting:")
        print("1. PostgreSQL está a correr? docker compose ps")
        print("2. Tens logs? SELECT COUNT(*) FROM raw_logs;")
        print("3. Tens alertas? SELECT COUNT(*) FROM alerts;")
        print("4. Dependências instaladas? pip install -r requirements.txt")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
