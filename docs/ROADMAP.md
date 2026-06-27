# Roadmap — Log Monitor MLOps
**Raúl Brito · A22309632 · IPLUSO 2026**
**Atualizado: 25/06/2026 · Estado: Goal D em curso**

---

## Visão Geral

| Goal | Semanas | Período | Estado |
|------|---------|---------|--------|
| **A** — Core: ingestão, rule engine, ML, XAI | S1–S8 | Jan–Mar | ✅ Concluído |
| **B** — Infraestrutura: Docker, monitorização, testes, CI/CD | S9–S13 | Mar–Abr | ✅ Concluído |
| **C** — Hardening, demo, documentação intercalar | S14–S16 | Abr–Mai | 🔄 Em curso |
| **D** — API pública, human-in-loop, XAI avançado, relatório final | S17–S23 | Mai–Jul | 📅 Planeado |
| **Pós-entrega** — Cloud POC, preparação da discussão | Jul–Ago | — | 📅 Planeado |

**Milestone de entrega:** 11 Jul 2026 — Relatório Final
**Discussão:** 01 Ago 2026

---

## Ambiente de Desenvolvimento — Fonte de Logs

### Fonte utilizada no desenvolvimento

O ambiente de desenvolvimento não dispõe de uma fonte de logs global/centralizada externa. Os logs processados durante o desenvolvimento foram gerados sinteticamente pela própria aplicação Flask (`logs/app.log`), com os seguintes tipos de eventos:

- Pedidos HTTP com campos `ip`, `timestamp`, `method`, `endpoint`, `status_code`, `bytes`, `response_time`
- Eventos de autenticação (login normal, brute-force simulado, falhas repetidas)
- Anomalias injectadas manualmente para treino e validação do modelo (port scans, exfiltração simulada, padrões de acesso irregular)

O gerador de logs sintéticos (`scripts/generate_logs.py`) permite reproduzir cenários de ataque controlados, o que é necessário para avaliar o modelo em condições conhecidas.

### Logs que a ferramenta poderia processar em contexto real

Caso esta ferramenta seja adoptada num ambiente de produção, está preparada para processar qualquer fonte de logs que seja adaptada ao schema de ingestão:

| Tipo de fonte | Formato | Adaptação necessária |
|---------------|---------|---------------------|
| Apache / Nginx (access log) | Combined Log Format | Parser de linha para extrair campos HTTP |
| Logs de autenticação Linux | `/var/log/auth.log` (syslog) | Extracção de eventos SSH/PAM |
| Logs de containers (Docker/k8s) | JSON (stdout) | Mapeamento de campos para o schema interno |
| Logs de aplicação genérica | JSON estruturado | Configuração do mapeamento de campos |
| Logs de firewalls/IDS | Syslog / CEF | Adaptador de formato (a desenvolver) |

Se existir uma fonte de logs global no ambiente institucional (e.g. servidor syslog centralizado, ELK Stack, ou SIEM existente), esta ferramenta pode ser integrada como camada de análise ML adicional, recebendo os logs via API de ingestão.

### Implicação para o Goal D

O feedback recebido após a apresentação intercalar clarificou um ponto importante: **benchmark externo não substitui validação com logs reais**. O projeto precisa de demonstrar não só que o modelo generaliza para um dataset externo, mas também que a pipeline completa consegue ingerir, normalizar, persistir e analisar **uma fonte real de logs** de ponta a ponta.

Assim, no Goal D, a prioridade de validação passa a ser:

1. **Teste end-to-end com logs reais externos** (preferência: Apache/Nginx access logs, por estarem mais próximos do schema actual)
2. **Benchmark técnico com CICIDS-2017** como validação complementar do modelo

---

## GOAL C — Hardening, Demo & Documentação Intercalar

### ✅ S14 · 27 Abr – 03 Mai · CONCLUÍDO
**Objectivo: Security Hardening em toda a stack**

- 5 containers migrados para utilizador non-root (`appuser`)
- Rate limiting activo em rotas sensíveis (`/login`, `/admin`, `/api`)
- Validação de inputs com Pydantic em todos os endpoints de ingestão
- `_safe_load_pickle` — trust boundary para carregamento de modelos `.pkl`
- Bandit: 0 findings HIGH/MEDIUM · Trivy scanning no CI · Dependabot activo
- 54 testes de segurança automatizados a verde
- Cobertura de testes: 70,97% (threshold CI ≥70% ✅)

---

### 🔄 S15 · 04 Mai – 10 Mai · EM CURSO
**Objectivo: Qualidade de testes e documentação intercalar**

- Corrigir os 15 fixtures de teste com regressão de configuração de `.pkl`
- Expandir cobertura de testes para ≥75% (threshold CI actualizado)
- Novos testes para os módulos de security (`validators.py`, `limiter.py`, `security.py`)
- Finalizar relatório intermédio v6 para entrega
- Preparar guião e materiais de suporte para a apresentação intercalar

**Critério de saída:** cobertura ≥75% no CI · relatório submetido

---

### 📅 S16 · 11 Mai – 17 Mai · APRESENTAÇÃO INTERCALAR
**Objectivo: Demo ao vivo e apresentação intercalar**

- Ensaio final da apresentação (14 min + Q&A)
- Validar que `docker compose up` arranca o sistema completo sem intervenção manual
- Preparar demo ao vivo: ingestão de logs, deteção de ataque, SHAP, dashboards Grafana e Streamlit
- Apresentação Intercalar ao júri
- Recolher feedback e documentar para incorporar no relatório final

**Critério de saída:** apresentação concluída · feedback recolhido

---

## GOAL D — API Pública, Human-in-Loop, XAI Avançado & Relatório Final

### 📅 S17 · 18 Mai – 24 Mai
**Objectivo: Human-in-loop — Interface de marcação de falsos positivos/negativos**

O analista de segurança precisa de conseguir validar ou refutar alertas directamente no dashboard — o feedback humano alimenta o ciclo de melhoria do modelo.

- Nova página no Streamlit: lista de alertas com acção de marcação (FP / FN / Confirmado)
- Esquema de BD para armazenar feedback humano por alerta
- API endpoint interno para receber marcações do dashboard
- Visualização do histórico de feedback no dashboard
- Testes unitários e de integração para o fluxo de marcação

**Critério de saída:** analista consegue marcar um alerta e o feedback fica persistido

---

### 📅 S18 · 25 Mai – 31 Mai
**Objectivo: Human-in-loop — Pipeline de retraining automático**

Com feedback humano acumulado, o sistema deve ser capaz de retreinar o modelo de forma assistida — não automática — e registar o novo run no MLflow.

- Script de retraining que incorpora os exemplos marcados como FP/FN no dataset de treino
- Trigger manual via comando ou botão no dashboard (não automático nesta fase)
- Run de retraining registado no MLflow com os parâmetros e métricas do novo modelo
- Comparação automática entre modelo anterior e novo (F1, ROC-AUC)
- Alerta no Alertmanager se o novo modelo degradar face ao anterior

**Critério de saída:** retraining executado com dados de feedback · run no MLflow · F1 comparado

---

### 📅 S19 · 01 Jun – 07 Jun
**Objectivo: Validação com logs reais externos + benchmark técnico**

Semana de validação em duas frentes complementares: (1) provar que a plataforma consegue processar **logs reais** de ponta a ponta; (2) complementar essa prova com benchmark externo do modelo e posicionamento funcional face às ferramentas já identificadas no relatório intermédio (Wazuh, Elastic SIEM, Splunk SIEM, IBM QRadar, Azure Sentinel).

**2.1 — Teste end-to-end com logs reais externos**
- Escolher uma fonte real alinhada com o projecto: preferência por **Apache/Nginx access logs**; alternativa: `auth.log`
- Implementar parser/adaptador da fonte escolhida para o schema interno de ingestão
- Correr ingestão completa com um conjunto real de logs e validar persistência na base de dados
- Medir taxa de parsing com sucesso, campos em falta e limitações encontradas
- Verificar comportamento das regras, scoring ML e visualização no dashboard com essa fonte real
- Documentar diferenças entre logs sintéticos e logs reais (ruído, formatos, timestamps, campos ausentes)

**2.2 — Validação com CICIDS-2017**
- Download e pré-processamento do CICIDS-2017 (Sharafaldin et al., 2018)
- Adaptação do feature engineering para o formato do dataset
- Avaliação do Isolation Forest e do ensemble no CICIDS-2017
- Comparação de métricas: dados sintéticos vs CICIDS-2017
- Documentação dos resultados e análise de diferenças

**2.3 — Benchmarking funcional face às soluções existentes**

O relatório intermédio já cobriu a dimensão de custos. Esta fase cobre a dimensão funcional: o que faz esta solução que as alternativas não fazem, e onde fica aquém.

| Dimensão funcional | Wazuh | Elastic SIEM | Splunk SIEM | **Log Monitor MLOps** |
|--------------------|-------|-------------|-------------|----------------------|
| Detecção rule-based | ✅ | ✅ | ✅ | ✅ |
| Detecção ML (Isolation Forest) | ❌ | Parcial | Parcial | ✅ |
| Ensemble ML (IF + RF) | ❌ | ❌ | ❌ | ✅ |
| Explicabilidade XAI (SHAP) | ❌ | ❌ | ❌ | ✅ |
| Pipeline MLOps (MLflow) | ❌ | ❌ | ❌ | ✅ |
| Human-in-loop / feedback | ❌ | Limitado | Limitado | ✅ (S17–S18) |
| Open-source, sem licença | ✅ | Parcial | ❌ | ✅ |
| Deployment local via Docker | ✅ | ✅ | Limitado | ✅ |

- Documentar a tabela comparativa com referências às fontes utilizadas no relatório intermédio
- Identificar e documentar os gaps desta solução face às alternativas (e.g. escala, correlação multi-fonte, threat intelligence integrada)
- Análise de onde a solução se diferencia (XAI, MLOps pipeline, open-source) e para que perfil de utilizador/organização é mais adequada

**Critério de saída:** pelo menos uma fonte real de logs ingerida de ponta a ponta · limitações documentadas · F1 e ROC-AUC do benchmark externo registados se a adaptação ao CICIDS-2017 ficar concluída

---

### 📅 S20 · 08 Jun – 14 Jun
**Objectivo: LIME — Explicabilidade complementar**

O SHAP está implementado e cobre o GDPR artigo 22. O LIME acrescenta uma perspectiva local complementar — útil para validação cruzada das explicações e para analistas menos familiarizados com valores SHAP.

- Implementação do LIME para o Isolation Forest e Random Forest
- Página no Streamlit: explicação LIME lado a lado com SHAP para o mesmo alerta
- Análise de concordância/divergência entre SHAP e LIME para os alertas críticos
- Testes para o módulo de explicabilidade LIME

**Critério de saída:** LIME funcional · comparação SHAP/LIME visível no dashboard

---

### 📅 S21–S22 · 15 Jun – 28 Jun
**Objectivo: Incident Workflow — ciclo de vida do incidente**

Os alertas precisam de um ciclo de vida gerível: um incidente deve poder ser aberto, investigado e resolvido — com histórico auditável. Isto é o que distingue uma ferramenta de deteção de um sistema de gestão de incidentes.

- Estados de alerta: `NEW → INVESTIGATING → RESOLVED` (com timestamps e utilizador)
- Transições de estado disponíveis no dashboard Streamlit
- Histórico de estado por alerta (quem mudou, quando, porquê)
- Actualização do esquema de BD para suportar estados e auditoria
- Métrica Prometheus para alertas por estado
- Testes do fluxo completo de ciclo de vida

**Critério de saída:** incidente consegue ser aberto, investigado e resolvido com histórico

---

### 📅 S23 · 29 Jun – 05 Jul
**Objectivo: Buffer, polimento e documentação final**

Semana de fecho — não de novas features. Qualquer tarefa das semanas anteriores que tenha escorregado aterra aqui. O foco principal é garantir que o sistema e o relatório estão prontos para entrega a 11 Jul.

- Correcção de bugs e regressões identificadas em S17–S22
- Cobertura de testes ≥85% (objectivo incremental de cada semana anterior)
- Revisão final do relatório: resultados, apêndices, abstract
- Validação de reprodutibilidade: `docker compose up` num ambiente limpo
- README actualizado com instruções de instalação e demo

**Critério de saída:** sistema estável · cobertura ≥85% · relatório pronto para entrega

---

## Pós-Entrega (Jul–Ago)

### 📅 11 Jul — Entrega do Relatório Final

---

### 📅 Jul (best-effort) — Cloud Deployment POC
**Objectivo: Demonstração de deployment externo**

Movido para depois da entrega para não criar risco sobre o relatório. Se funcionar, enriquece a discussão; se não funcionar, não tem impacto na nota.

- Deploy do stack completo numa VPS ou serviço cloud (Hetzner, DigitalOcean, ou similar)
- Validação dos SLOs em ambiente externo
- Documentação do processo de deployment como apêndice ou nota técnica

---

### 📅 01 Ago — Discussão Final

---

## Métricas de Qualidade por Semana

| Métrica | Actual (S14) | S15 | S16 | S23 |
|---------|-------------|-----|-----|-----|
| Cobertura de testes | 70,97% | ≥75% | ≥75% | ≥85% |
| Testes a passar | 87/102 | 102/102 | 102/102 | — |
| Pylint | 9,18/10 | ≥9,0 | ≥9,0 | ≥9,0 |
| Bandit findings HIGH/MED | 0 | 0 | 0 | 0 |
| F1 modelo (IF) | 0,838 | 0,838 | 0,838 | ≥0,838 |

---

## Dependências Críticas

```
S17 (UI feedback) → S18 (retraining) — o retraining só faz sentido com dados de feedback
S19 (logs reais) → relatório final — a prova de ingestão real sustenta a aplicabilidade da solução
S19 (CICIDS) → relatório final — o benchmark externo complementa, mas não substitui, a validação com logs reais
S20 (LIME) → S21 (incident workflow) — podem ser paralelos se necessário
S21-S22 (incident) → S23 (polimento) — o workflow tem de estar estável antes do fecho
```

---

## Riscos

| Risco | Probabilidade | Mitigação |
|-------|--------------|-----------|
| Fonte real de logs indisponível ou demasiado heterogénea | Média | Priorizar Apache/Nginx access logs; preparar amostra offline para teste controlado |
| CICIDS-2017 com formato incompatível | Média | Feature engineering adaptável; 1 semana dedicada |
| Retraining degrada o modelo | Baixa | MLflow permite rollback imediato para versão anterior |
| Incident workflow exige mais de 2 semanas | Média | Simplificar para 2 estados (OPEN/CLOSED) se necessário |
| Cobertura ≥85% não atingida em S23 | Média | Incremento gradual S17–S22; S23 é buffer, não sprint |
| Cloud POC com problemas de rede/configuração | Alta | Movido para pós-entrega — sem impacto no relatório |


