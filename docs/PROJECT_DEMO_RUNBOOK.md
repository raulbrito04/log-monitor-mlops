# Guia de Demonstração do Projeto

## Objetivo

Este guia serve para fazer uma demonstração end-to-end do projeto, desde a geração/ingestão de logs até à deteção por regras, pipeline de ML, MLflow, explainability com SHAP, monitorização operacional e dashboard em Streamlit.

O objetivo da apresentação é mostrar uma narrativa coerente:

1. O sistema recebe tráfego e gera logs.
2. Os logs são ingeridos e persistidos em PostgreSQL/TimescaleDB.
3. O motor de regras gera alertas de segurança.
4. A pipeline de ML constrói features, treina modelos e regista experiências no MLflow.
5. A explicabilidade mostra quais as features que mais influenciam o modelo supervisionado.
6. O stack de monitorização acompanha saúde, métricas, F1 operacional e alertas.
7. O dashboard junta tudo num ponto único de observação para o operador.

## Duração Recomendada

- Demo curta: 10 a 12 minutos
- Demo completa: 20 a 30 minutos

## Pré-Demo

Antes da apresentação, preparar:

1. Um terminal no root do projeto.
2. O `venv` ativo.
3. Docker Desktop / Docker Engine a correr.
4. Browser com estes separadores preparados:
   - `http://localhost:5001/health`
   - `http://localhost:5000`
   - `http://localhost:8501`
   - `http://localhost:9090`
   - `http://localhost:9093`
   - `http://localhost:3000`

## Setup Inicial

No terminal principal:

```bash
cd /home/raulb/projects/log-monitor-mlops
source venv/bin/activate
set -a
source docker/.env
set +a
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=logmonitor
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD}"
export MLFLOW_TRACKING_URI=http://localhost:5000
```

Subir o stack:

```bash
docker compose -f docker/docker-compose.yml up -d --build
docker compose -f docker/docker-compose.yml ps
```

Checks rápidos:

```bash
curl http://localhost:5001/health
curl http://localhost:8501/_stcore/health
curl http://localhost:9090/-/healthy
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9093/-/healthy
```

Credenciais úteis:

- Flask demo login: `admin / admin123`
- Streamlit dashboard: `admin / admin`
- Grafana: `admin / admin`

## Estrutura da Apresentação

### 1. Introdução Rápida da Arquitetura

O que dizer:

- A aplicação Flask simula tráfego e gera logs.
- O ingester lê esses logs e persiste-os em `raw_logs`.
- O rule engine deteta padrões suspeitos e escreve em `alerts`.
- A pipeline de ML constrói datasets, treina modelos e guarda artefactos.
- O MLflow faz tracking de experiências.
- Prometheus, Alertmanager e Grafana monitorizam a operação.
- O dashboard Streamlit junta visão operacional, alertas, logs e performance do modelo.

Se quiseres mostrar rapidamente os serviços ativos:

```bash
docker compose -f docker/docker-compose.yml ps
```

## Demo Principal

### 2. Preparar Dados para uma Demo Estável

Esta etapa cria histórico sintético para a demo não depender apenas de poucos logs recentes.

Comando:

```bash
./venv/bin/python scripts/backfill_historical_logs.py --days 21 --apply --truncate-existing --run-rule-engine
```

O que dizer:

- Estou a popular 21 dias sintéticos de atividade para dar contexto temporal ao sistema.
- Isto melhora a consistência da demo e evita mostrar um sistema “vazio”.
- No fim já tenho logs históricos e alertas iniciais gerados.

Confirmar na base de dados:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c "SELECT COUNT(*) AS raw_logs FROM raw_logs;"

docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c "SELECT COUNT(*) AS alerts FROM alerts;"
```

### 3. Mostrar Geração de Tráfego e Ingestão de Logs

Primeiro gerar tráfego normal:

```bash
./venv/bin/python src/flask_app/traffic_generator.py --mode normal --duration 15
```

Depois gerar um ataque visível:

```bash
./venv/bin/python src/flask_app/traffic_generator.py --mode attack --type sql_injection --num-requests 20
```

Alternativas úteis:

```bash
./venv/bin/python src/flask_app/traffic_generator.py --mode attack --type brute_force --num-requests 30
./venv/bin/python src/flask_app/traffic_generator.py --mode attack --type mixed --duration 30
```

O que dizer:

- Aqui estou a injetar tráfego na aplicação Flask.
- O sistema distingue carga normal de comportamentos claramente suspeitos.
- O ingester corre no stack Docker e vai transferindo estes eventos para a base de dados.

Mostrar os logs mais recentes já ingeridos:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT timestamp, ip, method, endpoint, status FROM raw_logs ORDER BY timestamp DESC LIMIT 10;"
```

### 4. Mostrar Deteção por Regras

Executar uma análise histórica explícita:

```bash
./venv/bin/python src/detection/rule_engine.py --mode historical --days 7
```

O que dizer:

- O motor de regras procura assinaturas e padrões operacionais suspeitos.
- Isto cobre cenários onde queremos deteção determinística e interpretável.
- No projeto atual existem regras para brute force, SQL injection, scanning, path traversal, user agents suspeitos e anomalias temporais.

Mostrar resumo dos alertas:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT alert_type, severity, source, COUNT(*) FROM alerts GROUP BY 1,2,3 ORDER BY COUNT(*) DESC;"
```

Mostrar detalhe recente:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT timestamp, alert_type, severity, source, ip FROM alerts ORDER BY timestamp DESC LIMIT 15;"
```

### 5. Mostrar Feature Engineering para ML

Executar o pipeline de features:

```bash
./venv/bin/python src/ml/feature_engineering.py
```

O que dizer:

- Esta fase transforma logs e contexto operacional em variáveis úteis para os modelos.
- O projeto guarda datasets e artefactos intermédios para reutilização e repetibilidade.
- Também separa features específicas para o caso do Isolation Forest.

Mostrar artefactos gerados:

```bash
ls -1 data/ml_dataset*.pkl
ls -1 models/scaler.pkl models/iforest_scaler.pkl models/feature_selector.pkl
sed -n '1,20p' data/selected_features.txt
sed -n '1,20p' data/iforest_features.txt
```

### 6. Mostrar Treino, Comparação de Modelos e MLflow

Executar o treino:

```bash
./venv/bin/python src/ml/train_model.py
```

O que dizer:

- Aqui mostramos o treino e comparação entre abordagens supervisionadas, não supervisionadas e híbridas.
- O MLflow regista parâmetros, métricas e artefactos do treino.
- Na demo convém explicar que o F1 mais importante para “qualidade de deteção” é o F1 em holdout do modelo que queremos operar, não qualquer métrica intermédia isolada.

Depois abrir:

- MLflow: `http://localhost:5000`

O que mostrar no MLflow:

- Nome da experiência
- Runs geradas
- Hiperparâmetros
- Métricas
- Artefactos

Mostrar artefactos no disco:

```bash
ls -1 models/*latest.pkl
ls -1 experiments/confusion_matrix*.png
ls -1 experiments/roc_pr_curves.png experiments/score_distributions.png
```

### 7. Mostrar Explainability com SHAP

Estado real do projeto:

- Neste momento a forma mais sólida de mostrar SHAP é através dos artefactos já gerados na pasta `experiments/`.
- Isto é adequado para demo e relatório.
- Não é correto vender isto como explicabilidade online em tempo real dentro do dashboard, porque essa integração não está atualmente implementada.

Mostrar os artefactos disponíveis:

```bash
ls -1 experiments/shap_*.png
```

Se quiseres abrir rapidamente num browser:

```bash
./venv/bin/python -m http.server 8010 --directory experiments
```

Depois abrir:

- `http://localhost:8010/shap_summary.png`
- `http://localhost:8010/shap_importance.png`
- `http://localhost:8010/shap_waterfall.png`

O que dizer:

- O SHAP ajuda a explicar porque é que o modelo supervisionado classificou certos padrões como suspeitos.
- O `summary` mostra impacto global das features.
- O `waterfall` ajuda a explicar um caso individual.
- Isto é explainability, não causalidade.

### 8. Mostrar Monitorização Operacional com Prometheus e Alertmanager

Ver métricas exportadas pela app:

```bash
curl http://localhost:5001/metrics | grep logmonitor_
```

Abrir:

- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`
- Grafana: `http://localhost:3000`

O que mostrar:

- Targets do Prometheus
- Regras e alertas ativos
- Dashboards Grafana

Comandos úteis:

```bash
curl -s http://localhost:9090/api/v1/alerts
curl -s http://localhost:9090/api/v1/rules
```

### 9. Mostrar Monitorização da Qualidade do Modelo

Forçar publicação de uma métrica F1 operacional:

```bash
./venv/bin/python scripts/generate_test_metrics.py --f1 0.783 --model hybrid_ensemble --dataset holdout
```

Confirmar no endpoint de métricas:

```bash
curl -s http://localhost:5001/metrics | grep logmonitor_ml_model_f1_score -A 2
```

Se quiseres mostrar um cenário de degradação:

```bash
./venv/bin/python scripts/generate_test_metrics.py --f1 0.60 --model hybrid_ensemble --dataset holdout
curl -s http://localhost:5001/metrics | grep logmonitor_ml_model_f1_score -A 2
curl -s http://localhost:9090/api/v1/alerts
```

Depois repor um valor aceitável:

```bash
./venv/bin/python scripts/generate_test_metrics.py --f1 0.783 --model hybrid_ensemble --dataset holdout
```

O que dizer:

- Não basta treinar modelos; é preciso observar qualidade operacional.
- Aqui mostramos como uma métrica de performance do modelo entra no stack de monitorização.
- O Prometheus e o Alertmanager conseguem reagir a degradações do F1.

### 10. Mostrar o Dashboard Streamlit

Abrir:

- Dashboard: `http://localhost:8501`

Login:

- Username: `admin`
- Password: `admin`

Fluxo recomendado no dashboard:

1. `Overview`
2. `Alerts`
3. `Log Explorer`
4. `Model Monitoring`

O que mostrar em cada página:

- `Overview`: saúde dos serviços, total de alertas, F1 operacional, freshness dos dados.
- `Alerts`: fila de alertas, filtros, detalhe do alerta, playbook associado.
- `Log Explorer`: pesquisa por IP, endpoint, método, status e texto livre.
- `Model Monitoring`: F1 atual, split normal/anomaly, tendência temporal e contexto operacional.

O que dizer:

- O dashboard é read-only e foi pensado para operação e investigação.
- Não substitui o backend; agrega sinais vindos de PostgreSQL e Prometheus.

## Demo Curta de 10 Minutos

Se tiveres pouco tempo, mostra apenas isto:

1. `docker compose -f docker/docker-compose.yml ps`
2. `./venv/bin/python scripts/backfill_historical_logs.py --days 21 --apply --truncate-existing --run-rule-engine`
3. `./venv/bin/python src/flask_app/traffic_generator.py --mode attack --type sql_injection --num-requests 20`
4. `./venv/bin/python src/ml/train_model.py`
5. Abrir `MLflow`, `Prometheus`, `Grafana` e `Streamlit`

## Queries SQL Úteis Durante a Demo

Total de logs:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c "SELECT COUNT(*) FROM raw_logs;"
```

Últimos logs:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT timestamp, ip, method, endpoint, status FROM raw_logs ORDER BY timestamp DESC LIMIT 20;"
```

Resumo de alertas:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT alert_type, severity, source, COUNT(*) FROM alerts GROUP BY 1,2,3 ORDER BY COUNT(*) DESC;"
```

Anomalias híbridas recentes:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT log_id, final_score, severity, is_anomaly, created_at FROM hybrid_scores ORDER BY created_at DESC LIMIT 20;"
```

Previsões ML recentes:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT log_id, model_name, anomaly_score, is_anomaly, created_at FROM ml_predictions ORDER BY created_at DESC LIMIT 20;"
```

## Se Alguma Parte Falhar

Se o dashboard estiver vazio:

- confirmar que `postgres`, `prometheus`, `flask-app` e `dashboard` estão `Up`
- correr novamente o backfill
- esperar alguns segundos pelo scrape do Prometheus

Se o MLflow não mostrar runs:

- confirmar `MLFLOW_TRACKING_URI=http://localhost:5000`
- voltar a correr `./venv/bin/python src/ml/train_model.py`

Se os alertas não aparecerem logo no Prometheus:

- abrir `http://localhost:9090/targets`
- confirmar que o target do Flask está `UP`
- abrir `http://localhost:9090/api/v1/rules`
- lembrar que alguns alertas têm janela temporal e podem ficar primeiro em `pending`

Se os ficheiros SHAP não existirem:

- confirmar a presença de `experiments/shap_summary.png`, `experiments/shap_importance.png` e `experiments/shap_waterfall.png`
- se não existirem, não improvisar uma demo “live” de SHAP; é melhor assumir essa limitação e mostrar os restantes artefactos de ML

## Mensagem Final da Apresentação

Mensagem recomendada para fechar:

- O projeto cobre o fluxo completo desde observabilidade aplicacional até deteção híbrida e operação assistida.
- A parte forte do sistema não é apenas “detetar”, mas também guardar contexto, medir qualidade, explicar decisões e expor isso numa interface operacional.
- Em termos de maturidade, o stack já demonstra ingestão, regras, ML, tracking, monitorização e dashboard de operação num fluxo único e coerente.
