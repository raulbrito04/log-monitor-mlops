# Startup & Screenshot Guide — Log Monitor MLOps

Ficheiro de referência rápida para inicializar o sistema, verificar o que está a correr
e tirar os screenshots que serão adicionados à apresentação.

---


,Q_>r;zW]-5A5$q





## 1. Inicialização

> **Tempos esperados:** build com cache ~4 min · build sem cache (1ª vez) ~8–10 min · só arranque (imagens existentes) ~30–60 s

```bash
cd /home/raulb/projects/log-monitor-mlops

# 1. Subir o stack completo (10 serviços)
docker compose -f docker/docker-compose.yml up -d --build

# 2. Aguardar o flask ficar healthy antes de continuar
#    (outros serviços dependem dele; sem esta espera o traffic generator falha)
curl --retry 15 --retry-delay 3 --retry-connrefused --silent --fail \
  http://localhost:5001/health && echo "Flask OK"

# 3. Confirmar que todos os serviços estão Up
docker compose -f docker/docker-compose.yml ps

# 4. Activar venv e popular dados históricos (21 dias sintéticos + rule engine)
source venv/bin/activate
python scripts/backfill_historical_logs.py --days 21 --apply --truncate-existing --run-rule-engine

# 5. Gerar tráfego de ataque para ter alertas visíveis
python src/flask_app/traffic_generator.py --mode attack --type sql_injection --num-requests 30

# 6. Treinar modelos (gera artefactos MLflow + confusion matrices)
python src/ml/train_model.py
```

> **Nota MLflow (localhost:5000):** a UI é uma SPA React — se aparecer em branco na primeira abertura, aguarda 5 s e faz F5.

---

## 2. Mapa de Portos e Credenciais

| Serviço | URL | Credenciais | Slide |
|---------|-----|-------------|-------|
| Flask App (API + health) | `http://localhost:5001/health` | — | — |
| MLflow (tracking de experimentos) | `http://localhost:5000` | — (sem auth) | 6 Pipeline ML |
| Streamlit Dashboard | `http://localhost:8501` | `admin / admin` | 10 Monitorização |
| Prometheus | `http://localhost:9090` | — | 10 Monitorização |
| Alertmanager | `http://localhost:9093` | — | 10 Monitorização |
| Grafana | `http://localhost:3000` | `admin / admin` | 10 Monitorização |
| PostgreSQL (interno) | `localhost:5432` | `postgres / (ver .env)` | — |

---

## 3. Screenshots a Tirar

Guardar todos em `docs/report_media/` com os nomes indicados.

### SS-01 — Stack a correr (docker compose ps)
**Ficheiro:** `docs/report_media/ss_docker_ps.png`
**Como tirar:** captura do terminal após `docker compose ... ps`
**Slide destino:** Slide 5 — Arquitectura (confirma 10 microserviços)
**O que mostrar:** todos os serviços com status `Up` ou `Up (healthy)`

```bash
docker compose -f docker/docker-compose.yml ps
```

---

### SS-02 — Streamlit Dashboard — Overview
**Ficheiro:** `docs/report_media/ss_streamlit_overview.png`
**Como tirar:** `http://localhost:8501` → login → página Overview
**Slide destino:** Slide 10 — Monitorização & Observabilidade
**O que mostrar:** métricas de saúde, contador de alertas, F1 operacional, freshness

---

### SS-03 — Streamlit Dashboard — Alerts
**Ficheiro:** `docs/report_media/ss_streamlit_alerts.png`
**Como tirar:** `http://localhost:8501` → página Alerts
**Slide destino:** Slide 10 — Monitorização & Observabilidade
**O que mostrar:** lista de alertas com severidade (idealmente com CRITICAL/HIGH visíveis)

---

### SS-04 — Grafana Dashboard
**Ficheiro:** `docs/report_media/ss_grafana.png`
**Como tirar:** `http://localhost:3000` → login → abrir um dos 3 dashboards auto-provisionados
**Slide destino:** Slide 10 — Monitorização & Observabilidade
**O que mostrar:** painel com métricas logmonitor_* em tempo real

---

### SS-05 — MLflow Experiments
**Ficheiro:** `docs/report_media/ss_mlflow.png`
**Como tirar:** `http://localhost:5000` → selecionar experiment com runs
**Slide destino:** Slide 6 — Pipeline ML Híbrido
**O que mostrar:** lista de runs com métricas F1, precision, recall visíveis

---

### SS-06 — Prometheus Targets
**Ficheiro:** `docs/report_media/ss_prometheus_targets.png`
**Como tirar:** `http://localhost:9090/targets`
**Slide destino:** Slide 10 — Monitorização
**O que mostrar:** targets com estado UP (flask-app, etc.)

---

### SS-07 — Terminal: Ingestão ao Vivo (opcional)
**Ficheiro:** `docs/report_media/ss_ingestao_live.png`
**Como tirar:** captura do terminal durante o `traffic_generator.py`
**Slide destino:** Slide 7 — Resultados de Performance
**O que mostrar:** logs a ser ingeridos com throughput visível

---

## 4. Depois de tirar os screenshots

Avisa o Claude Code com a mensagem:

> "Já tirei os screenshots, guarda-os em docs/report_media/ e adiciona-os à apresentação v2"

O script vai adicionar cada imagem ao slide correcto com legenda adequada.

---

## 5. Verificações rápidas antes da demo

```bash
# Health checks
curl http://localhost:5001/health
curl http://localhost:8501/_stcore/health
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:9090/-/healthy

# Contagem de dados
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c "SELECT COUNT(*) FROM raw_logs;"

docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT alert_type, severity, COUNT(*) FROM alerts GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10;"
```

---

## 6. Se algo falhar

| Problema | Solução |
|----------|---------|
| `flask` fica `unhealthy` / `PermissionError app.log` | `docker compose down` → `docker volume rm log-monitor-mlops_logs_data` → `docker compose up -d --build` |
| Dashboard Streamlit vazio | Correr novamente o backfill; confirmar que `postgres` e `flask-app` estão Up |
| MLflow sem runs | `MLFLOW_TRACKING_URI=http://localhost:5000 python src/ml/train_model.py` |
| Alertas não aparecem no Prometheus | Verificar `http://localhost:9090/targets`; aguardar scrape (15s) |
| Grafana sem dados | Login `admin/admin`; abrir "Log Monitor — Overview" no menu Dashboards |
