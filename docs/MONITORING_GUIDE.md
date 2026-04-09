# Monitoring Guide

## Stack

- Prometheus em `http://localhost:9090`
- Grafana em `http://localhost:3000`
- Alertmanager em `http://localhost:9093`

## Dashboards

1. `Log Monitor - System Overview`
2. `Log Monitor - ML Performance`
3. `Log Monitor - Security Alerts`

## SLOs

- Availability: `99.5%`
- p95 latency: `< 200ms`
- ML F1 score: `> 0.75`
- Data freshness: `< 5 minutos`

## Rotina

1. Confirmar `docker compose -f docker/docker-compose.yml ps`
2. Ver targets em `http://localhost:9090/targets`
3. Ver alerts em `http://localhost:9090/alerts`
4. Abrir dashboards no Grafana

## Atualizar F1 operacional

```bash
python scripts/generate_test_metrics.py --f1 0.783 --model hybrid_ensemble --dataset holdout
```

Isto atualiza o gauge `logmonitor_ml_model_f1_score`, usado no dashboard e nas regras de alerta.
