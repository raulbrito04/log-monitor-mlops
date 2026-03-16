# 🔍 Log Monitor MLOps

Sistema híbrido de deteção de anomalias em logs web usando **regras determinísticas** + **machine learning**.

---

## 📊 Status do Projeto

**Progresso:** 40% completo (Semana 6/16)  
**Apresentação Intercalar:** 11-15 Maio 2025  
**Objetivo Intercalar:** Plano A completo

---

## ✅ Fases Completadas

### **Semana 1-2: Foundation & Logging**
- ✅ Flask application com 6 rotas funcionais
- ✅ Logging estruturado JSON
- ✅ Traffic generator com padrões de ataque
- ✅ 2,560+ logs de teste gerados

### **Semana 3: PostgreSQL + TimescaleDB**
- ✅ PostgreSQL 16 em Docker
- ✅ TimescaleDB hypertable para time-series optimization
- ✅ 5 tabelas: raw_logs, alerts, ml_predictions, model_runs, feedback
- ✅ Ingestão: 9,355 logs/segundo
- ✅ 2,566 logs armazenados

### **Semana 4: Rule-Based Detection**
- ✅ 6 regras SQL implementadas:
  - Brute Force (≥5 login failures)
  - SQL Injection (pattern matching)
  - Port Scanning (≥10 distinct endpoints)
  - Path Traversal (../, /etc/passwd patterns)
  - Suspicious User Agent (sqlmap, nikto, nmap)
  - Time-Based Anomaly (requests 22h-6h)
- ✅ Performance: < 50ms por regra
- ✅ 21 alertas criados em 2,566 logs
- ✅ Zero falsos positivos nos testes

### **Semana 5: Feature Engineering**
- ✅ 18 features extraídas:
  - 2 numéricas diretas (status, response_time)
  - 6 agregação por IP/janela 5min
  - 4 temporais (hora, dia, weekend, night)
  - 3 URL (length, query params)
  - 1 entropy (Shannon - deteta obfuscation)
  - 2 behavioral (tempo entre requests)
- ✅ Correlation analysis: removeu 8 features redundantes
- ✅ RFE: selecionou 10 features otimizadas
- ✅ Dataset ML-ready: 2,326 logs, 17.45% anomaly rate
- ✅ StandardScaler aplicado (normalização)

---

## 🔄 Em Desenvolvimento

**Semana 6: Model Training** (PRÓXIMO)
- Isolation Forest (unsupervised anomaly detection)
- MLflow tracking server
- 3-5 experimentos com hyperparameter tuning
- Model Registry (Production stage)
- Target: F1-score > 0.75

---

## ⏳ Roadmap

**Semanas 7-8: ML Pipeline**
- Semana 7: Hybrid system (Rules + ML)
- Semana 8: SHAP explainability

**Semanas 9-12: Observability**
- Prometheus metrics
- Grafana dashboards
- Testes automatizados (>70% coverage)

**Semanas 13-16: Production**
- CI/CD pipeline
- Security audit
- Documentação final
- Apresentação final

---

## 🚀 Quick Start

### Pré-requisitos

```bash
# Necessário:
- Docker + Docker Compose
- Python 3.10+
- Git
```

### 1. Clone e Setup

```bash
# Clone repo
git clone <repo-url>
cd log-monitor-mlops

# Criar alias útil (opcional)
echo 'alias projetoLogs="cd ~/projects/log-monitor-mlops && source venv/bin/activate"' >> ~/.bashrc
source ~/.bashrc

# Ativar ambiente
projetoLogs
```

### 2. Iniciar Serviços

```bash
# PostgreSQL + TimescaleDB
docker compose -f docker/docker-compose.yml up -d

# Verificar
docker compose -f docker/docker-compose.yml ps
```

### 3. Setup Python

```bash
# Criar virtual environment
python -m venv venv
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
```

### 4. Ingerir Logs

```bash
# Carregar logs iniciais
python src/log_processor/ingester.py

# Verificar
docker compose -f docker/docker-compose.yml exec postgres psql -U postgres -d logmonitor -c "SELECT COUNT(*) FROM raw_logs;"
```

### 5. Executar Deteção

```bash
# Rule-based detection (últimos 7 dias)
python src/detection/rule_engine.py --mode historical --days 7

# Ver alertas criados
docker compose -f docker/docker-compose.yml exec postgres psql -U postgres -d logmonitor -c "SELECT alert_type, COUNT(*) FROM alerts GROUP BY alert_type;"
```

---

## 🏗️ Arquitetura do Sistema

```
┌──────────────────────────────────────────────────────────┐
│                      LOG SOURCES                         │
│  Flask App (6 rotas) → Traffic Generator (ataques)       │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                   INGESTION LAYER                        │
│  Python Script → 9,355 logs/segundo                      │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│              STORAGE: PostgreSQL + TimescaleDB           │
│  • raw_logs (hypertable)                                 │
│  • alerts, ml_predictions, model_runs, feedback          │
│  • 2,566 logs armazenados                                │
└────────────────────────┬─────────────────────────────────┘
                         │
                ┌────────┴────────┐
                │                 │
                ▼                 ▼
    ┌───────────────────┐  ┌──────────────────┐
    │  RULE ENGINE (6)  │  │  ML PIPELINE     │
    │  < 50ms/regra     │  │  (em dev)        │
    │  21 alertas       │  │  Isolation Forest│
    └───────────────────┘  └──────────────────┘
                │                 │
                └────────┬────────┘
                         │
                         ▼
              ┌────────────────────┐
              │  HYBRID SCORING    │
              │  (Rules + ML)      │
              │  (Semana 7)        │
              └────────────────────┘
```

---

## 🛠️ Stack Tecnológico

**Backend & Database:**
- Python 3.12
- PostgreSQL 16 + TimescaleDB extension
- Docker + Docker Compose

**Machine Learning:**
- Scikit-learn (Isolation Forest)
- Pandas + NumPy
- SciPy (entropy calculation)
- MLflow (experiment tracking - em setup)

**Em Desenvolvimento:**
- Prometheus (métricas)
- Grafana (dashboards)
- GitHub Actions (CI/CD)

---

## 📂 Estrutura do Projeto

```
log-monitor-mlops/
│
├── docker/
│   ├── docker-compose.yml      # PostgreSQL + TimescaleDB
│   └── init.sql                # Database schema & hypertable
│
├── src/
│   ├── log_processor/
│   │   └── ingester.py         # Log ingestion (9355 logs/s)
│   │
│   ├── detection/
│   │   └── rule_engine.py      # 6 regras SQL (<50ms cada)
│   │
│   └── ml/
│       ├── feature_engineering.py  # 18 features → 10 otimizadas
│       └── train_model.py      # Isolation Forest (em dev)
│
├── data/
│   ├── ml_dataset.pkl          # Dataset ML-ready (2326x13)
│   └── feature_summary.json    # Metadados features
│
├── models/
│   ├── scaler.pkl              # StandardScaler treinado
│   └── feature_selector.pkl    # RFE selector
│
├── logs/
│   └── app.log                 # Application logs
│
├── .env                        # Environment variables
├── requirements.txt            # Python dependencies
└── README.md                   # Este ficheiro
```

---

## 📈 Métricas Atuais

### Ingestão (Semana 3)
- **Performance:** 9,355 logs/segundo
- **Volume:** 2,566 logs armazenados
- **Período:** 20 dias de dados

### Rule-Based Detection (Semana 4)
- **Regras ativas:** 6
- **Latência:** < 50ms por regra
- **Alertas criados:** 21
- **Falsos positivos:** 0 (nos testes)
- **Distribuição:**
  - Suspicious User Agent: 9 alertas
  - Brute Force: 4 alertas
  - Time Anomaly: 4 alertas
  - SQL Injection: 2 alertas
  - Path Traversal: 2 alertas

### Feature Engineering (Semana 5)
- **Features extraídas:** 18
- **Features finais:** 10 (após correlation + RFE)
- **Dataset shape:** 2,326 logs × 10 features
- **Anomaly rate:** 17.45% (412 logs anómalos)
- **Label balance:** 82.55% normal / 17.45% anomalia (ideal 4:1)

---

## 🎯 Objetivos do Projeto

**Principais:**
1. ✅ Sistema híbrido: Regras (precisão) + ML (generalização)
2. 🔄 Pipeline reproduzível com MLflow tracking
3. ⏳ Observability completa (Prometheus + Grafana)
4. ⏳ Explainability via SHAP
5. ⏳ CI/CD automatizado

**Diferenciadores:**
- TimescaleDB para otimização de time-series
- Feature engineering com entropy (deteta obfuscation)
- RFE para seleção automática de features
- Ensemble híbrido (rules + ML)

---

## 📚 Documentação Adicional

**Tutoriais Completos:**
- Semana 3: PostgreSQL + TimescaleDB Setup
- Semana 4: Rule-Based Detection
- Semana 5: Feature Engineering
- Semana 6: Model Training (disponível em breve)

**Localizados em:** `/docs/` (a criar)

---

## 🔧 Comandos Úteis

### Docker

```bash
# Iniciar serviços
docker compose -f docker/docker-compose.yml up -d

# Ver logs
docker compose -f docker/docker-compose.yml logs -f postgres

# Parar serviços
docker compose -f docker/docker-compose.yml down

# Reset completo (apaga dados!)
docker compose -f docker/docker-compose.yml down -v
sudo rm -rf data/postgres
```

### PostgreSQL

```bash
# Entrar no psql
docker compose -f docker/docker-compose.yml exec postgres psql -U postgres -d logmonitor

# Queries úteis:
# SELECT COUNT(*) FROM raw_logs;
# SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10;
# \dt  (listar tabelas)
# \q   (sair)
```

### Python

```bash
# Ativar venv
source venv/bin/activate

# Ingerir logs
python src/log_processor/ingester.py

# Executar regras
python src/detection/rule_engine.py --mode historical --days 7

# Feature engineering
python src/ml/feature_engineering.py
```

---

## 🐛 Troubleshooting

### PostgreSQL não inicia

```bash
# Verificar porta 5432 livre
lsof -i :5432

# Se ocupada, matar processo
kill -9 <PID>

# Ou mudar porta no docker-compose.yml
```

### "No module named 'pandas'"

```bash
# Verificar venv ativo
which python  # Deve mostrar path do venv

# Reinstalar dependências
pip install -r requirements.txt
```

### TimescaleDB constraint errors

```bash
# Verificar init.sql está correto
# PRIMARY KEY deve ser (id, timestamp) - composto!
# Não pode ter UNIQUE(id) sozinho

# Reset database se necessário
docker compose -f docker/docker-compose.yml down -v
sudo rm -rf data/postgres
docker compose -f docker/docker-compose.yml up -d
```

---

## 🤝 Contribuição

Este é um projeto académico individual.

**Autor:** Raúl Brito
**Instituição:** IPLUSO  
**Curso:** Licenciatura em Engenharia Informática e Aplicações
**Ano Letivo:** 2025/2026  
**Orientador:** Acácio Carmona

---

## 📝 Licença

Projeto académico - Todos os direitos reservados.

---

## 📅 Changelog

**2026-03-16:**
- ✅ README completo adicionado
- ✅ Documentação estruturada (Quick Start, Troubleshooting)
- ✅ Projeto 40% completo

**2026-03-12:**
- ✅ Semana 5 completa: Feature Engineering
- ✅ 10 features otimizadas selecionadas via RFE
- ✅ Dataset ML-ready criado (2,326 logs, 17.45% anomaly rate)

**2026-03-09:**
- ✅ Semana 4 completa: Rule-Based Detection
- ✅ 6 regras implementadas com <50ms latência
- ✅ 21 alertas criados em 2,566 logs

**2026-03-05:**
- ✅ Semana 3 completa: PostgreSQL + TimescaleDB
- ✅ Hypertable funcional com PRIMARY KEY composto
- ✅ 2,566 logs ingeridos a 9,355 logs/segundo

---

**Status:** 🚧 Em desenvolvimento ativo  
**Última atualização:** 16 Março 2026  
**Próxima milestone:** Semana 6 - Model Training (Isolation Forest + MLflow)
