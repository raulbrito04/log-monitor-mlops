# Guião de Apresentação — Log Monitor MLOps
**Raúl Brito · A22309632 · IPLUSO 2026**
**Duração total: ~14 minutos · 19 slides**

---

## SLIDE 1 — Capa

> *[Aguardar silêncio. Olhar para a sala antes de falar.]*

"Imaginem que a vossa empresa foi atacada ontem à noite. Os logs estavam todos lá — o ataque estava registado — mas ninguém conseguiu ver a tempo porque havia demasiada informação para processar manualmente.

Este projeto resolve exatamente esse problema.

Chamo-me Raúl Brito, número de aluno A22309632. O que vos vou mostrar hoje é o **Log Monitor MLOps** — um sistema que deteta ataques em tempo real, explica as suas decisões, e pode correr na máquina de qualquer PME sem custos de licença."

*[~30 segundos]*

---

## SLIDE 2 — Agenda

"O slide tem os tópicos todos detalhados — vou guiar-vos pelos quatro blocos principais.

Começo pelo **problema e a solução** — o porquê do projeto. Depois entro na **tecnologia** — arquitectura, ML e explicabilidade. A seguir mostro **evidência** — resultados, monitorização, segurança e CI/CD. E termino com **posicionamento e futuro** — benchmarking, viabilidade e próximos passos.

As questões podem ficar para o final."

*[~20 segundos]*

---

## SLIDE 3 — O Problema

"O problema tem três camadas.

A primeira é de **escala**: organizações geram milhões de logs por dia. A análise manual é inviável. Os ataques acontecem em milissegundos — a resposta humana não acompanha.

A segunda é **regulatória**: a legislação europeia — GDPR artigo 22, AI Act de 2024 e NIS2 — exige que qualquer decisão automática seja explicável e auditável. A lei já não aceita caixas-negras.

A terceira é **económica**: as soluções maduras do mercado — Splunk, IBM QRadar — custam entre 30 e 100 mil euros por ano e foram concebidas para grandes organizações. Regras estáticas, sem ML adaptativo, sem explicabilidade.

O resultado: PMEs e o contexto académico ficam sem alternativa viável."

*[~50 segundos]*

---

## SLIDE 4 — Solução Proposta

"A diferença deste sistema face ao que existe é simples: **deteta ataques que nunca viu antes e explica porquê os classificou como tal.**

O sistema tem três componentes que se complementam.

Um **rule engine SQL determinístico** — seis padrões de ataque, zero falsos positivos, latência abaixo de 41 ms por regra. SQL nativo — qualquer engenheiro consegue auditar.

**Isolation Forest**, um modelo não-supervisionado — treinado apenas com tráfego normal. Quando aparece um padrão anómalo, mesmo de um ataque nunca visto, é sinalizado automaticamente.

**Explicabilidade com SHAP** — para cada anomalia detetada, o sistema mostra quais as variáveis que pesaram na decisão. É o que o GDPR artigo 22 e o AI Act exigem a qualquer sistema de decisão automática."

*[~50 segundos]*

---

## SLIDE 5 — Arquitectura

"A arquitectura tem **10 microserviços em 5 camadas**, todos a correr em Docker Compose.

O fluxo de dados segue um percurso claro: os logs entram pela Flask app, ficam em PostgreSQL com TimescaleDB para séries temporais, são analisados em paralelo pelo Rule Engine e pelo pipeline ML, o resultado é explicado via SHAP, e tudo é visível em tempo real no Prometheus e Grafana.

Dois detalhes que importam para produção: os Dockerfiles usam multi-stage builds — as imagens passaram de 1,2 GB para cerca de 180 MB. E cada componente é substituível de forma independente, sem derrubar o sistema."

*[~40 segundos]*

---

## SLIDE 6 — Pipeline ML Híbrido

"Entrando no detalhe da camada de deteção — o pipeline híbrido.

O **Isolation Forest** usa *novelty detection*: treinámos o modelo exclusivamente com logs normais — nunca viu um ataque durante o treino. Qualquer padrão que se desvie desse baseline é sinalizado, independentemente do tipo de ataque. É o que permite detetar zero-days. F1 de 0,838, Precision@1% de 0,941, ROC-AUC de 0,950.

O **Random Forest** é supervisionado, com labels de ataque conhecidos. F1 de 0,783 — inferior ao IF em isolado, mas o ablation study mostra que os dois juntos superam qualquer um deles sozinho: o IF captura ataques desconhecidos, o RF é mais preciso nos padrões já vistos.

O **MLflow** — que vemos no próximo slide — garante que cada experimento fica registado e cada modelo é versionado."

*[~55 segundos]*

---

## SLIDE 7 — MLflow (screenshot)

> *[Apontar para as linhas da tabela de runs.]*

"Cada linha aqui é um run de treino — parâmetros, métricas e artefactos registados automaticamente.

O que isto permite em prática: se amanhã o modelo degradar em produção, consigo identificar qual foi o último run estável, compará-lo com o atual, e fazer rollback em minutos.

Sem isto, MLOps é só um buzzword. Com isto, é engenharia real."

*[~25 segundos]*

---

## SLIDE 8 — Explicabilidade SHAP

> *[Apontar para o gráfico à esquerda, depois para o ablation study à direita.]*

"Aqui vemos quanto cada variável pesou na decisão de classificar um log como anomalia — e em que direção. Quando o sistema sinaliza um ataque, não diz apenas 'é suspeito' — diz *porquê*, feature a feature.

Do lado direito, o ablation study: só regras, só ML, e o híbrido. O híbrido vence em todas as métricas — não foi uma escolha de arquitectura arbitrária, foi a que os dados confirmaram.

Esta combinação de XAI com deteção de anomalias em segurança é um contributo metodológico concreto, num espaço que a literatura ainda não explorou extensivamente."

*[~45 segundos]*

---

## SLIDE 9 — Resultados de Performance

"Os três números que importam reter deste slide — os de qualidade de código estão no slide de CI/CD.

**10.933 logs por segundo** com batch de 500 — em prática, 100 mil logs em 9 segundos. Escala de produção.

**Latência mediana de 3 ms** sob carga de 50 utilizadores simultâneos, com zero erros em 30 segundos de stress test com Locust. O sistema não degradou.

**Rule Engine: 7 a 41 ms por regra, zero falsos positivos** — seis padrões de ataque a detetar em tempo real, incluindo SQL injection, brute force e DDoS.

Estes não são resultados de laboratório controlado — foram medidos com o sistema containerizado completo a correr."

*[~45 segundos]*

---

## SLIDE 10 — Monitorização & Observabilidade

"Uma coisa é o sistema funcionar. Outra é sabermos *que* está a funcionar — e quando deixa de estar.

O **Prometheus** recolhe 9 métricas custom a cada 15 segundos. O **Grafana** organiza-as em 3 dashboards provisionados automaticamente no startup — Overview, ML e Security.

Os **SLOs** estão definidos de forma mensurável: disponibilidade ≥ 99,5%, latência p95 < 200 ms, F1 do modelo ≥ 0,75.

Qualquer desvio é visível imediatamente — não quando o utilizador reporta um problema."

*[~40 segundos]*

---

## SLIDE 11 — Grafana Dashboards (screenshot)

> *[Apontar para os painéis visíveis.]*

"Estes dashboards arrancam sem configuração manual — são provisionados via YAML no startup do Docker Compose.

O que vemos aqui em tempo real: taxa de ingestão, deteções por regra, e estado do modelo. Se um SLO for violado, aparece neste ecrã antes de qualquer utilizador dar conta."

*[~20 segundos]*

---

## SLIDE 12 — Streamlit & Alertmanager (screenshot)

"O Grafana é para operações. O **Streamlit** é para quem não é DevOps — um analista de segurança consegue ver aqui os serviços observados, o volume de anomalias nas últimas 24 horas, e o estado dos alertas por severidade.

> *[Apontar para o Alertmanager à direita.]*

E aqui no Alertmanager podem ver um alerta de **DataFreshnessHigh** ativo — o sistema detetou que os dados estavam a exceder o tempo de frescura definido no SLO e disparou o alerta automaticamente, sem intervenção humana. É exatamente para isto que serve o alerting."

*[~35 segundos]*

---

## SLIDE 13 — Security Hardening

"A Semana 14 foi dedicada a aplicar segurança em profundidade — não como camada final, mas como revisão de toda a stack.

O princípio orientador foi o **menor privilégio**: os 5 containers de runtime correm como utilizador `appuser`, sem acesso root. Todos os secrets estão em variáveis de ambiente, nunca em código.

Na **fronteira da API**: rate limiting ativo, validação de inputs com Pydantic em todos os endpoints de ingestão.

Na **cadeia de desenvolvimento**: Bandit no CI com zero findings HIGH ou MEDIUM, Trivy a fazer scanning automático das imagens, Dependabot a gerir dependências, e 54 testes de segurança automatizados, todos verdes.

O resultado: o sistema cobre OWASP Top 10, GDPR artigo 22, AI Act e NIS2 — não por acidente, mas por design."

*[~55 segundos]*

---

## SLIDE 14 — CI/CD & Qualidade

"O pipeline de CI/CD garante que nenhum código chega ao repositório sem passar por uma sequência de verificações automáticas.

Em cada push: Pylint, Bandit, Trivy, testes unitários, teste de carga, e deploy local — tudo sequencial, tudo automatizado desde a Semana 13.

Dos 102 testes escritos, 87 passam hoje. Os 15 restantes estão documentados e no backlog da Semana 15 — nada bloqueante para o sistema funcionar.

A cobertura é 70,97% — acima do threshold de 70% que o CI rejeita automaticamente. Não é possível fazer merge com menos do que isso."

*[~45 segundos]*

---

## SLIDE 15 — Benchmarking & Gap Analysis

"Coloquei os números lado a lado com as soluções comerciais.

As soluções enterprise — Splunk, QRadar, Datadog — ficam entre 20 e 100 mil euros por ano. Mesmo o Elastic, que é parcialmente open-source, custa entre 10 e 30 mil. Nenhuma tem explicabilidade nativa. Nenhuma tem ML adaptativo open-source.

**Log Monitor MLOps: zero euros.** Com SHAP, com ML que deteta ataques nunca vistos, completamente open-source.

O gap que o slide 3 identificou está aqui preenchido, linha a linha."

*[~40 segundos]*

---

## SLIDE 16 — Pertinência e Viabilidade

"A viabilidade do projeto assenta em três dimensões.

**Regulatória**: a conformidade com GDPR artigo 22, AI Act e NIS2 está no design do sistema, não adicionada depois. O sistema pode evoluir sem reescrever a fundação.

**Científica**: a combinação de novelty detection com ablation study em logs de segurança é um contributo metodológico concreto — não é ML aplicado de forma genérica, há escolhas justificadas experimentalmente.

**Económica**: 254 horas de desenvolvimento individual, custo zero em ferramentas, funcionalidade equivalente a um SIEM de 30 a 100 mil euros por ano. Qualquer PME ou instituição académica pode adotar isto amanhã."

*[~40 segundos]*

---

## SLIDE 17 — Planeamento Goals A–D

"O projeto está estruturado em **4 fases ao longo de 27 semanas**.

**Goals A e B** — Semanas 1 a 13: toda a infraestrutura, ML, monitorização e CI/CD. **Concluídos.**

**Goal C** — Semanas 14 a 16: security hardening, demo e documentação intercalar. **Em curso** — S14 entregue, estamos a 33% do Goal C.

**Goal D** — Semanas 17 a 23: API REST pública, alerting avançado, dashboard avançado, relatório final. **Planeado.**

O cronograma está a ser cumprido — não há tarefas em atraso face ao plano original."

*[~40 segundos]*

---

## SLIDE 18 — Estado Atual & Próximos Passos

"A situação hoje: o sistema está operacional e pode ser demonstrado ao vivo.

Os Goals A e B estão completos. O Goal C está a 33% — a S14 entregue, a S15 foca em cobertura de testes para 75% e na documentação intercalar, e a S16 prepara a demo final e revê o relatório.

A partir da S17, o Goal D: API REST pública, alerting avançado e dashboard para utilizadores finais.

O sistema não é um protótipo — é um produto funcional com métricas de produção medidas, segurança em profundidade, e CI/CD a correr em cada commit."

*[~40 segundos]*

---

## SLIDE 19 — Conclusão

> *[Pausar. Olhar para a sala. Tom direto, sem pressa.]*

"Em 14 semanas, a solo, construí uma alternativa funcional ao que as empresas cobram 30 a 100 mil euros por ano.

A diferença central: este sistema explica as suas decisões. Não é uma caixa-negra — é auditável, é mensurável, e está a correr agora.

**Obrigado. Estou disponível para questões.**"

*[~30 segundos]*

---

## Notas de Apresentação

**Tempo total estimado: ~13–14 minutos** *(margem para questões ou demo ao vivo)*

| Slide | Tópico | Tempo |
|-------|--------|-------|
| 1 | Capa | 30 s |
| 2 | Agenda | 20 s |
| 3 | Problema | 50 s |
| 4 | Solução | 50 s |
| 5 | Arquitectura | 40 s |
| 6 | Pipeline ML | 55 s |
| 7 | MLflow | 25 s |
| 8 | SHAP | 45 s |
| 9 | Performance | 45 s |
| 10 | Monitorização | 40 s |
| 11 | Grafana | 20 s |
| 12 | Streamlit | 35 s |
| 13 | Security | 55 s |
| 14 | CI/CD | 45 s |
| 15 | Benchmarking | 40 s |
| 16 | Pertinência | 40 s |
| 17 | Planeamento | 40 s |
| 18 | Estado Atual | 40 s |
| 19 | Conclusão | 30 s |
| **Total** | | **~13 min 45 s** |

---

## Questões prováveis do júri — preparação

**"Porquê Random Forest se tem F1 mais baixo que o Isolation Forest?"**
O RF não é melhor em isolado — é melhor no ensemble. O IF deteta padrões desconhecidos (zero-days), o RF é mais preciso em padrões com histórico. O ablation study no slide 8 confirma que os dois juntos superam qualquer um sozinho.

**"Os 15 testes que falham não são um problema?"**
Não são bloqueantes — o sistema está operacional e a cobertura de 70,97% cumpre o threshold do CI. Os 15 casos estão documentados e no backlog da S15.

**"Como garantes que o F1=0,838 é reproduzível?"**
O MLflow regista cada run com os parâmetros exatos, o dataset e os artefactos do modelo. Qualquer run pode ser reproduzido a partir do histórico.

**"O LIME está implementado?"**
O SHAP está implementado e operacional. O LIME está planeado para o Goal D — a decisão foi priorizar o SHAP primeiro porque cobre o requisito do GDPR artigo 22 e tem maior adoção na literatura de cibersegurança.

**"O sistema está pronto para produção real?"**
Está demonstrável em ambiente containerizado local com métricas de produção medidas. O Goal D — API REST pública, alerting avançado — é o passo seguinte para deployment externo.
