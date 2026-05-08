# Revisão de Conteúdo do Relatório Intermédio v2

Data da revisão: 2026-04-28

## Objetivo

Avaliar o conteúdo de `Relatorio_Intermedio_Log_Monitor_MLOps_v2.docx` à luz do estado real do projeto em código e testes, com foco em:

- fidelidade ao que está implementado
- claims que precisam de ser corrigidas
- claims que devem ser removidas
- informação nova, suportada por testes, que vale a pena acrescentar ao relatório/projeto

## Base factual usada

### Testes executados

Comando:

```bash
./venv/bin/pytest -q
```

Resultado:

- 102 testes recolhidos
- 87 passaram
- 1 skipped
- 2 falharam
- 12 errors
- cobertura total: `70.97%`

Resumo relevante:

- O projeto passa a maioria da suite.
- O principal foco de falha está em `src/ml/hybrid_pipeline.py`.
- A cobertura global continua acima do threshold mínimo de CI (`70%`), mas está longe de justificar claims agressivas sobre robustez total do pipeline híbrido.

### Falhas reais identificadas pelos testes

1. `HybridPipeline` ficou mais seguro, mas rebentou a testabilidade:

- `src/ml/hybrid_pipeline.py` agora só aceita artefactos `.pkl` dentro de `models/`
- os testes unitários e de integração criam artefactos temporários em `/tmp/...`
- isso gera 12 errors + 1 falha de integração

2. Há mismatch entre testes e implementação:

- `test_weights_sum_validation` espera `AssertionError`
- a implementação lança `ValueError`

Isto significa que, neste momento, o relatório não deve sugerir que o pipeline híbrido está totalmente estabilizado do ponto de vista de QA.

### Cobertura por módulos

Fortes:

- `src/flask_app/app.py`: `88%`
- `src/flask_app/config.py`: `94%`
- `src/flask_app/security.py`: `100%`
- `src/flask_app/validators.py`: `94%`
- `src/monitoring/metrics.py`: `86%`

Médios:

- `src/log_processor/ingester.py`: `72%`
- `src/dashboard/pages_impl.py`: `78%`

Fracos:

- `src/ml/hybrid_pipeline.py`: `38%`
- `src/dashboard/data.py`: `51%`
- `src/dashboard/auth.py`: `47%`
- `src/dashboard/ui.py`: `52%`
- `src/detection/rule_engine.py`: `54%`

## O que o projeto suporta hoje com segurança

Com base no código atual, estas afirmações estão alinhadas com o projeto:

- existe um dashboard Streamlit de operador com páginas `Overview`, `Alerts`, `Log Explorer` e `Model Monitoring`
- existe stack de monitorização com Prometheus, Grafana e Alertmanager
- existe CI com GitHub Actions, incluindo `Pylint`, `Bandit`, testes e `Trivy`
- existe hardening de segurança no Flask e nos containers
- existe scoring híbrido com severidades `CRITICAL/HIGH/MEDIUM/NORMAL`
- existe explainability com SHAP ao nível de artefactos experimentais
- existe pipeline de treino com `IsolationForest` e `RandomForest`

## Frases do v2 a manter

### Manter quase como está

1. "Deteção de 6 tipos de ataque via regras SQL determinísticas."

Razão:

- o `rule_engine` implementa 6 regras

2. "Deteção de anomalias desconhecidas com Isolation Forest."

Razão:

- isso está alinhado com o pipeline de ML atual

3. "Pipeline híbrido com scoring combinado e classificação CRITICAL/HIGH/MEDIUM/NORMAL."

Razão:

- corresponde ao comportamento de `src/ml/hybrid_pipeline.py`

4. "Explicabilidade das decisões ML via SHAP values."

Razão:

- o projeto tem artefactos SHAP gerados e esse claim é realista

5. "Stack de monitorização com Prometheus e Grafana."

Razão:

- está implementado no compose e na camada de monitorização

6. "Dashboard de operador em Streamlit com autenticação."

Razão:

- existe dashboard com login de sessão

7. "CI/CD com GitHub Actions, Bandit, Trivy e Dependabot."

Razão:

- está alinhado com `.github/workflows/ci.yml` e `.github/dependabot.yml`

8. "Security hardening (containers non-root, rate limiting, input validation, security headers)."

Razão:

- está alinhado com a branch atual e os testes de segurança passam

## Frases do v2 a corrigir

### Corrigir por excesso, imprecisão ou linguagem demasiado forte

1. "The architecture consists of six containerised services orchestrated with Docker Compose"

Problema:

- o `docker-compose` atual tem `10` serviços no total

Sugestão:

- "A stack de desenvolvimento usa 10 serviços em Docker Compose, incluindo aplicação, pipeline ML, base de dados e observabilidade."

2. "At the midpoint of the project (Semanas 1–14), the core system is fully operational."

Problema:

- Semana 14 de 16 não é "midpoint"
- "fully operational" é demasiado forte face ao estado dos testes do `hybrid_pipeline`

Sugestão:

- "Na fase final do desenvolvimento (Semana 14/16), o core do sistema encontra-se operacional, com lacunas pontuais ainda abertas no pipeline híbrido e em funcionalidades avançadas."

3. "The Isolation Forest achieves F1 > 0.75 on the internal dataset."

Problema:

- aceitável como resumo, mas deve ficar explicitamente ligado ao dataset interno e/ou ao último experimento registado

Sugestão:

- "Nos experimentos internos mais recentes, o Isolation Forest ultrapassou F1 > 0.75 no dataset sintético/interno."

4. "Feedback de FP/FN via dashboard implementado (S11). Retraining automático diferido para pós-apresentação."

Problema:

- a tabela `feedback` existe, mas o fluxo funcional completo via dashboard não está claramente suportado pelo código atual

Sugestão:

- "A estrutura de persistência de feedback está preparada na base de dados; a recolha operacional completa via dashboard e o retraining automático ficam como evolução futura."

5. "Todas as funcionalidades do Goal A e Goal B foram concluídas."

Problema:

- demasiado forte face às lacunas reais em feedback operacional, incident workflow, LIME/counterfactuals e estabilização do hybrid pipeline

Sugestão:

- "A maioria das funcionalidades dos Goals A e B foi concluída, com algumas capacidades avançadas ou operacionais a permanecerem parciais ou diferidas."

6. "Rule engine with 6 rules SQL (brute force, SQLi, scanning, rate abuse, path traversal, XSS)"

Problema:

- a lista não corresponde ao rule engine atual

Sugestão:

- "Rule engine com 6 regras SQL: brute force, SQL injection, port scanning, path traversal, suspicious user agent e time-based anomaly."

7. "Flask app e gerador de tráfego sintético (10 tipos de ataque simulados)"

Problema:

- o gerador atual não expõe 10 tipos de ataque

Sugestão:

- "Flask app e gerador de tráfego com modos normal e ataques como brute force, scanning, SQL injection, rate abuse e mixed traffic."

8. "Test coverage: 74% (critério >70% cumprido)."

Problema:

- no teste corrido nesta revisão, a cobertura foi `70.97%`
- se quiseres manter `74%`, tens de citar a origem exata e a data desse valor

Sugestão:

- "A cobertura global de testes mantém-se acima do threshold de 70% do CI; nesta revisão local foi medida em 70.97%."

9. "O dashboard permite ao analyst marcar alertas como False Positive ou True Positive."

Problema:

- não encontrei esse fluxo de UI claramente implementado nas páginas atuais

Sugestão:

- "O dashboard atual é focado em observação e investigação; a marcação operacional de feedback estruturado permanece uma extensão natural do projeto."

10. "Isto permite afirmar com confiança: 'O sistema tem performance comparável a métodos publicados em papers académicos'."

Problema:

- frase demasiado forte sem benchmark externo fechado, nomeadamente CICIDS

Sugestão:

- "Os resultados internos são encorajadores, mas a comparação rigorosa com literatura depende ainda de benchmark externo consistente, como CICIDS-2017."

## Frases do v2 a cortar

### Cortar ou mover para “trabalho futuro”

1. "Workflow completo NEW→RESOLVED"

Razão:

- não está claramente suportado no schema/UI operacional atual

2. "Feedback de FP/FN via dashboard implementado" (na forma assertiva atual)

Razão:

- o claim está acima do que o código demonstra hoje

3. "Retraining semanal incorpora feedback"

Razão:

- isso não está implementado ponta a ponta

4. "XSS" como regra implementada

Razão:

- não corresponde ao `rule_engine` atual

5. "Geolocation" como regra implementada

Razão:

- não corresponde ao `rule_engine` atual

6. "CICIDS-2017 ... Pendente (P2 — diferido) ... Isto permite afirmar com confiança ..."

Razão:

- a segunda parte contradiz a primeira
- se CICIDS está diferido, não pode servir como base de confiança factual agora

7. "Implementado: Docker container logs (CPU, memory, eventos)"

Razão:

- o projeto está sólido em web logs; multi-source/container logs não estão demonstrados ao mesmo nível

8. "Bandit findings HIGH reduzidos em >50% após S14."

Razão:

- não vi neste ciclo de validação uma evidência fechada e reproduzível dessa percentagem

## Informação nova, suportada por testes, que vale a pena acrescentar ao projeto/relatório

### 1. Estado real de QA

Adicionar uma pequena subseção tipo:

- "Validação atual da suite de testes: 87 testes passaram, 1 ficou skipped e 14 não passaram (2 falhas + 12 erros), com cobertura global de 70.97%."

Valor:

- mostra honestidade metodológica
- dá maturidade ao relatório

### 2. Hotspot técnico identificado

Adicionar uma nota de limitação:

- "As falhas atuais concentram-se no `hybrid_pipeline`, onde o endurecimento da carga segura de artefactos `.pkl` introduziu regressões de testabilidade e integração."

Valor:

- transforma uma fraqueza em evidência de engenharia responsável

### 3. Cobertura por áreas

Adicionar algo como:

- "As áreas mais estáveis em testes são Flask/security/monitoring; as áreas a reforçar são `hybrid_pipeline`, `dashboard/data` e `rule_engine`."

Valor:

- mostra visão crítica e plano de melhoria

### 4. Reescrever “production-ready”

Substituir claims fortes por formulação mais séria:

- "production-oriented"
- "demo-ready and operational in local containerized environment"
- "ready for controlled demonstration and further hardening"

Valor:

- evita sobrepromessa

### 5. Fecho metodológico melhor

Adicionar uma frase deste género:

- "O projeto encontra-se funcional e demonstrável, mas várias capacidades avançadas previstas no plano original foram conscientemente diferidas para privilegiar robustez do core, monitorização e segurança."

Valor:

- encaixa melhor com o trabalho real

## Conclusão

O `v2` é a melhor base porque está mais próximo do projeto real do que a versão original. Ainda assim, precisa de:

- baixar claims sobre feedback operacional e incident workflow
- alinhar a lista de regras com o código real
- deixar claro que CICIDS, LIME, counterfactuals, retraining automático e ensemble avançado são trabalho futuro
- incorporar o estado real dos testes, sobretudo o problema atual no `hybrid_pipeline`

Se estas correções forem feitas, o `v2` fica bastante mais credível e tecnicamente mais forte.
