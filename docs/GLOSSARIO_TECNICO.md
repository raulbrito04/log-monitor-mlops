# Glossário Técnico — Log Monitor MLOps

Documento de referência para os termos técnicos do projeto, organizados por área temática.

---

## Arquitectura

### Microserviços

Um **microserviço** é um processo independente que corre em isolamento e é responsável por uma função específica do sistema. Em vez de ter uma aplicação monolítica que faz tudo (ingestão + deteção + ML + dashboard + alertas numa só peça de código), o sistema é dividido em componentes separados que comunicam entre si por rede (HTTP, sockets).

**No projeto existem 10 microserviços:**

| Container | Responsabilidade |
|-----------|-----------------|
| `flask-app` | Recebe logs via HTTP, serve as rotas da aplicação |
| `ingester` | Lê logs e insere-os no PostgreSQL |
| `rule-engine` | Corre as 6 regras SQL de deteção determinística |
| `ml-pipeline` | Corre o Isolation Forest + Random Forest em tempo real |
| `dashboard` | Interface Streamlit para analistas de segurança |
| `grafana` | Dashboards operacionais para DevOps |
| `prometheus` | Recolhe e armazena métricas de todos os serviços |
| `alertmanager` | Gere e envia alertas quando SLOs são violados |
| `mlflow` | Registo de experimentos e versões de modelos ML |
| `postgres` | Base de dados relacional com TimescaleDB |

**Vantagem prática:** se o `ml-pipeline` ficar lento, o `flask-app` continua a receber logs sem interrupção. Cada componente é substituível e escalável de forma independente.

---

### Multi-stage Builds (Docker)

Um **multi-stage build** é uma técnica de Dockerfile que usa múltiplas fases de construção para produzir uma imagem final mais pequena e segura.

**Problema sem multi-stage:** a imagem final incluiria compiladores, ferramentas de build, cache de pip, e outros artefactos de desenvolvimento — resultando em imagens de 1+ GB.

**Como funciona:**

```dockerfile
# Fase 1 — build: instala dependências e compila
FROM python:3.12 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Fase 2 — runtime: copia apenas o resultado final
FROM python:3.12-slim
COPY --from=builder /root/.local /root/.local
COPY src/ ./src/
```

**Resultado no projeto:** imagens passaram de ~1,2 GB para ~180 MB. Menos superfície de ataque, pull mais rápido em CI/CD, menos CVEs expostos ao Trivy.

---

### O que mostra o slide 5 da apresentação

O slide 5 (Arquitectura) mostra dois elementos:

1. **Diagrama de arquitectura em 5 camadas:** entrada de logs → armazenamento → deteção (regras + ML) → explicabilidade (SHAP) → observabilidade (Prometheus/Grafana).

2. **Output do comando `docker compose -f docker/docker-compose.yml ps`:** prova ao vivo que os 10 microserviços estão a correr e saudáveis.

**O que o comando mostra:**

```
NAME                    IMAGE                           STATUS              PORTS
logmonitor-alertmanager prom/alertmanager:v0.27.0       Up 2 hours (healthy) :9093
logmonitor-dashboard    docker-dashboard                Up 31 min (healthy)  :8501
logmonitor-flask        docker-flask-app                Up 31 min (healthy)  :5001
logmonitor-grafana      grafana/grafana:10.4.0          Up 2 hours           :3000
logmonitor-ingester     docker-ingester                 Up 30 min (healthy)  :—
logmonitor-ml-pipeline  docker-ml-pipeline              Up 31 min (healthy)  :5000
logmonitor-mlflow       python:3.12-slim                Up 33 min (healthy)  :—
logmonitor-postgres     timescale/timescaledb:latest-pg16 Up 2 hours         :5432
logmonitor-prometheus   prom/prometheus:v2.51.0         Up 2 hours           :9090
logmonitor-rule-engine  docker-rule-engine              Up 31 min (healthy)  :—
```

Cada linha é um microserviço. A coluna `STATUS` com `(healthy)` significa que o healthcheck definido no `docker-compose.yml` passou — o container não está só a correr, está a responder corretamente.

---

## Armazenamento

### Séries Temporais (Time-series)

Uma **série temporal** é um conjunto de dados onde cada registo tem um timestamp e o tempo é a dimensão principal de consulta. Em vez de perguntar "qual é o status do log 42?", pergunta-se "quantos logs de erro houve entre as 14h e as 15h?".

**No projeto:** cada log Web tem um `timestamp`. As consultas mais comuns são:
- "quantos ataques nas últimas 5 minutos?"
- "qual a latência média por hora nas últimas 24h?"
- "quando é que o modelo começou a degradar?"

Estas consultas são ineficientes em bases de dados relacionais normais com dados de meses — o TimescaleDB resolve isso.

---

### PostgreSQL

**PostgreSQL** é uma base de dados relacional open-source, robusta e ACID-compliant. É o motor de base de dados principal do projeto.

No projeto armazena 5 tabelas:
- `raw_logs` — todos os logs ingeridos
- `alerts` — alertas gerados pelas regras e pelo ML
- `ml_predictions` — predições do modelo com score de anomalia
- `model_runs` — histórico de treino (complementa MLflow)
- `feedback` — marcações humanas de FP/FN (Goal D)

---

### ACID

**ACID** é o conjunto de propriedades que garantem que uma base de dados é confiável, mesmo em caso de falha:

| Propriedade | Significado | Exemplo prático |
|-------------|-------------|-----------------|
| **A**tomicity | Uma transação ou é toda executada ou é toda revertida | Inserir log + criar alerta: se um falhar, nenhum fica |
| **C**onsistency | A BD passa de um estado válido para outro estado válido | Nunca fica um alerta sem o log correspondente |
| **I**solation | Transações concorrentes não interferem entre si | Dois ingesters a inserir ao mesmo tempo não corrompem dados |
| **D**urability | Dados confirmados sobrevivem a falhas de sistema | Um `COMMIT` sobrevive a um crash do servidor |

O PostgreSQL é totalmente ACID — é uma das razões pela qual foi escolhido face a alternativas como MongoDB.

---

### TimescaleDB

**TimescaleDB** é uma extensão do PostgreSQL que adiciona suporte nativo a séries temporais, mantendo toda a compatibilidade SQL.

**O que acrescenta ao PostgreSQL:**

- **Hypertables:** particiona automaticamente tabelas por intervalo de tempo (ex: uma partição por semana). Consultas por range de tempo só leem as partições relevantes — muito mais rápido.
- **Compressão automática:** dados antigos são comprimidos, poupando espaço.
- **Funções temporais:** `time_bucket()`, `first()`, `last()` — agregações temporais nativas.

**Resultado no projeto:** 9.355 logs/segundo de ingestão com TimescaleDB.

---

## Infraestrutura e CI/CD

### GitHub Actions CI/CD

**CI (Continuous Integration)** e **CD (Continuous Delivery/Deployment)** são conceitos distintos que são frequentemente agrupados sob o mesmo termo "CI/CD".

**CI — Continuous Integration**
Verificação automática de cada alteração ao repositório antes de ser aceite. O objetivo é detetar problemas o mais cedo possível — não quando já está em produção. Corre em cada `git push` ou Pull Request. **Não publica nada** — só verifica.

O repositório não contém só código — contém também `requirements.txt`, `Dockerfile`, ficheiros YAML de configuração, etc. Uma alteração a um `Dockerfile` sem tocar em nenhum `.py` também dispara o CI e pode falhar. O Trivy é um exemplo disso: não verifica código Python, verifica a imagem Docker que resulta do estado atual do repositório. É CI legítimo porque responde à pergunta "esta versão do repositório produz algo seguro?".

O CI inclui tipicamente: linting, testes automatizados, análise de segurança, e build de artefactos (imagens Docker, binários). Se qualquer etapa falhar, o merge é bloqueado.

**CD — Continuous Delivery / Deployment**
Publicação automática do código que passou no CI. Há duas variantes:
- **Continuous Delivery:** o artefacto validado fica pronto para deploy, mas um humano decide quando publicar (aprovação manual).
- **Continuous Deployment:** o deploy acontece automaticamente após o CI passar, sem intervenção humana.

**A diferença prática:**

| | CI | CD |
|---|---|---|
| Pergunta que responde | "Este código está correto?" | "Como chega ao utilizador?" |
| Quando corre | Em cada push / PR | Após CI passar, em branches específicas |
| Publica algo? | Não | Sim |
| Exemplo | Pylint + pytest + Trivy | Deploy para servidor, push de imagem para registry |

**No projeto:** o CI está implementado e funcional (`.github/workflows/ci.yml`). O CD não está implementado — o deploy continua a ser feito manualmente com `docker compose up`. Usar o termo "CI/CD" no projeto refere-se ao pipeline de CI com capacidade de CD futura, não a um deploy automatizado já em produção. É uma distinção honesta a fazer se o júri perguntar.

**No projeto, o pipeline CI corre em cada push:**

```
push para qualquer branch
        │
        ▼
  ┌─────────────┐
  │  Code Quality│  → Pylint (qualidade) + Bandit (segurança)
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │    Tests    │  → pytest + cobertura ≥70%
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │    Build    │  → constrói 5 imagens Docker + Trivy scan
  └─────────────┘
        │
        ▼
  ┌─────────────┐
  │   Summary   │  → relatório final no GitHub
  └─────────────┘
```

O ficheiro que define tudo isto é `.github/workflows/ci.yml`. O GitHub executa-o nos seus próprios servidores (runners `ubuntu-latest`) sem precisar de infraestrutura local.

**Valor prático:** nenhum código chega ao `main` sem passar por todas as verificações. Se os testes falharem, o CI falha e o PR não pode fazer merge.

---

## Segurança

### Bandit

**Bandit** é um linter de segurança estático para Python. Analisa o código-fonte sem o executar e identifica padrões inseguros conhecidos.

**Como funciona:** percorre a árvore AST (Abstract Syntax Tree) do código Python e compara com um catálogo de regras. Cada regra tem um código (B + número), uma severidade (LOW/MEDIUM/HIGH) e uma confiança (LOW/MEDIUM/HIGH).

**Exemplos de regras:**
- `B301` — uso de `pickle.loads()` (deserialização insegura)
- `B311` — uso de `random` em contexto de segurança
- `B608` — SQL construído por concatenação de strings

**No projeto:** após a S14, o resultado é `0 HIGH, 0 MEDIUM, 14 LOW`. Os LOW restantes são no `traffic_generator.py` (simulador de ataques) — falsos positivos aceites e documentados em `docs/security/bandit_exceptions.md`.

---

### Trivy

**Trivy** é um scanner de vulnerabilidades para containers Docker, sistemas de ficheiros e repositórios git. Em vez de analisar o código que o programador escreveu, analisa os **pacotes e bibliotecas** instalados dentro da imagem.

**Diferença fundamental face ao Bandit:**

| | Bandit | Trivy |
|---|---|---|
| Analisa | Código Python escrito pelo programador | Pacotes instalados dentro do container |
| Detecta | Padrões inseguros no código | CVEs (vulnerabilidades públicas conhecidas) |
| Exemplo | `pickle.loads()` com input externo | `openssl 1.1.1` com CVE-2023-XXXX |

**No projeto:** o CI constrói as 5 imagens Docker e depois corre o Trivy em cada uma, com `severity: CRITICAL,HIGH`. O resultado é exportado em formato SARIF para o GitHub Security tab.

```
Trivy scan - flask-app
  exit-code: 0   ← não falha o CI, apenas reporta e regista
```

---

### Security findings: HIGH / MEDIUM

São os níveis de severidade usados pelo Bandit e pelo Trivy:

- **HIGH** — problema sério, potencialmente exploitável com consequências graves. Ex: hardcoded password em código de produção, SQL injection via input de utilizador, deserialização pickle a partir de fonte externa.
- **MEDIUM** — problema real mas com impacto ou exploitabilidade limitada. Ex: `subprocess` sem `shell=False`, geração de token com `random` em vez de `secrets`.
- **LOW** — impacto mínimo ou muito difícil de explorar. Ex: `random` num simulador de tráfego.

**Meta da S14:** `0 HIGH, 0 MEDIUM` nos módulos principais. Alcançada.

---

### Path Traversal

**Path traversal** é um ataque em que o utilizador manipula um caminho de ficheiro para aceder a ficheiros fora do diretório permitido.

**Exemplo clássico:**
```
GET /files?name=../../../../etc/passwd
```
Se a aplicação construir o caminho como `base_dir + filename` sem validação, o `../` permite "subir" na árvore de diretórios e ler qualquer ficheiro do sistema.

**No projeto:** o Rule Engine tem uma regra SQL específica que deteta padrões `../` e `/etc/passwd` nos URLs dos logs:
```sql
-- Regra: Path Traversal
WHERE url LIKE '%../%' OR url LIKE '%/etc/passwd%'
```

Quando um log com estes padrões é ingerido, é criado um alerta imediato.

---

### Non-root Containers (5 containers non-root)

Por defeito, os processos dentro de um container Docker correm como `root` — o utilizador com todos os privilégios do sistema. Se um atacante conseguir sair do container (container escape), tem acesso root ao servidor anfitrião.

**Solução:** criar um utilizador sem privilégios dentro do container:

```dockerfile
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser
```

**Os 5 containers hardened na S14:**
1. `flask-app`
2. `dashboard`
3. `ingester`
4. `ml-pipeline`
5. `rule-engine`

`postgres`, `grafana`, `prometheus`, `alertmanager`, e `mlflow` usam imagens oficiais que já gerem o seu próprio utilizador de runtime.

---

### Rotas sensíveis (Rate Limiting em rotas sensíveis)

Uma **rota sensível** é um endpoint HTTP que, se visitado demasiadas vezes ou de forma automatizada, cria risco de segurança.

**Não é simplesmente "rotas que não devem ser muito visitadas"** — é rotas onde tráfego excessivo tem uma consequência de segurança específica:

| Rota | Porquê é sensível | Risco sem rate limiting |
|------|-------------------|------------------------|
| `/login` | Autentica utilizadores | Brute force de passwords |
| `/admin` | Acesso a funções privilegiadas | Enumeração de funcionalidades admin |
| `/search` | Query na base de dados | Extração de dados por força bruta |
| `/api/upload` | Recebe ficheiros | Flood de uploads, esgotamento de disco |

**Rate limiting:** quando um IP faz demasiados pedidos num intervalo curto, o servidor responde com `429 Too Many Requests` e para de processar os pedidos desse IP por um período.

**No projeto:** implementado em `src/flask_app/limiter.py` com limites diferentes por rota (ex: `/login` tem limites mais agressivos que `/search`).

---

### Validação de inputs (Pydantic)

**Pydantic** é uma biblioteca Python que valida dados de entrada contra um schema definido em código. Em vez de confiar que o utilizador envia o que é esperado, o sistema verifica e rejeita inputs inválidos.

**Exemplo:**
```python
class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
```

Se o cliente enviar `username: ""` (string vazia) ou `password: None`, o Pydantic rejeita com `400 Bad Request` antes de o código chegar à base de dados.

**Porquê importa:** inputs não validados são a fonte de SQL injection, path traversal, buffer overflows e outros ataques. Validar na fronteira do sistema (onde o dado entra) é o princípio de segurança de "fail early, fail safe".

---

### Secrets em variáveis de ambiente

**Hardcoded secrets** são passwords, API keys, ou chaves de criptografia escritas diretamente no código fonte:

```python
# ERRADO — vai para o git, fica exposto
SECRET_KEY = "minha-password-123"
DB_PASSWORD = "changeme"
```

**Variáveis de ambiente** separam a configuração sensível do código:

```python
# CORRETO — valor vem do ambiente de execução
SECRET_KEY = os.environ["FLASK_SECRET_KEY"]
DB_PASSWORD = os.environ["POSTGRES_PASSWORD"]
```

O ficheiro `.env` (nunca commitado para o git, listado no `.gitignore`) ou as variáveis do Docker Compose fornecem os valores reais em runtime.

**No projeto:** após a S14, a `FLASK_SECRET_KEY` e todas as passwords de base de dados vêm de variáveis de ambiente. O app falha com erro explícito se a variável não estiver definida (fail-fast — melhor crashar em startup do que correr com defaults inseguros).

---

### Dependabot: dependências actualizadas

**Dependabot** é um serviço do GitHub que monitoriza as dependências do projeto (ficheiros `requirements.txt`, `package.json`, etc.) e abre automaticamente Pull Requests quando existem versões mais recentes, especialmente com patches de segurança.

**Porquê importa:** a maioria das vulnerabilidades exploradas em produção não vêm de código novo — vêm de bibliotecas antigas com CVEs conhecidos. O Dependabot garante que o `requirements.txt` não fica desatualizado sem aviso.

---

### Trivy container scanning no CI

Em cada execução do CI, depois de construir as imagens Docker, o pipeline corre o Trivy em cada imagem:

```yaml
- name: Trivy scan - flask-app
  uses: aquasecurity/trivy-action@0.24.0
  with:
    image-ref: logmonitor/flask-app:ci
    severity: CRITICAL,HIGH
    exit-code: 0   # não falha o CI — apenas reporta
```

O resultado é enviado para o GitHub Security tab em formato SARIF, onde fica visível como um relatório de segurança associado ao commit.

---

## Monitorização

### Dashboards Grafana provisionadas via YAML

Sim — as dashboards do Grafana **não são configuradas manualmente** no browser. São carregadas automaticamente no startup do Docker Compose a partir de ficheiros de configuração YAML e JSON.

**Como funciona:**

```
docker/
  grafana/
    provisioning/
      datasources/
        prometheus.yaml   ← define que o Prometheus é a fonte de dados
      dashboards/
        dashboards.yaml   ← diz ao Grafana onde procurar as dashboards
        overview.json     ← definição completa da dashboard Overview
        ml.json           ← dashboard ML
        security.json     ← dashboard Security
```

O `docker-compose.yml` monta estes ficheiros dentro do container Grafana. Quando o Grafana arranca, lê os ficheiros e cria tudo automaticamente — sem nenhuma interação manual.

**Vantagem:** se o container for destruído e recriado, as dashboards reaparecem exatamente iguais. É infraestrutura como código.

---

### Scrape interval vs Data freshness

São dois conceitos distintos que é fácil confundir:

**Scrape interval** — com que frequência o Prometheus vai buscar métricas aos serviços.

```yaml
# prometheus.yml
global:
  scrape_interval: 15s   # vai buscar métricas a cada 15 segundos
```

Cada serviço expõe métricas num endpoint `/metrics`. O Prometheus acede a esse endpoint de 15 em 15 segundos e guarda os valores.

**Data freshness** — há quanto tempo os dados mais recentes foram recebidos, do ponto de vista do sistema de monitorização.

Se o `ingester` deixar de enviar logs para a base de dados, o Prometheus pode continuar a fazer scrapes normalmente — mas os dados no PostgreSQL ficam "stale" (velhos). O alerta `DataFreshnessHigh` visible no Alertmanager no slide 12 disparou exactamente porque os dados na BD excederam o tempo máximo de frescura definido no SLO.

**Resumindo:**
- Scrape interval = cadência de recolha de métricas (Prometheus)
- Data freshness = frescura dos dados de negócio (logs no PostgreSQL)

São independentes: o Prometheus pode estar a funcionar perfeitamente (scrape OK) enquanto os dados estão velhos (freshness violada).

---

## Atores do sistema

### Quem usa o Streamlit

O **Streamlit** é o dashboard para **analistas de segurança** — utilizadores com conhecimento de cibersegurança mas sem obrigatoriedade de conhecimento de DevOps ou infraestrutura.

Mostra:
- Volume de anomalias nas últimas 24h
- Alertas por severidade
- Explicações SHAP para cada alerta
- (Goal D) Marcação de falsos positivos/negativos

Não requer acesso a ferramentas de linha de comando.

### Quem usa o Grafana

O **Grafana** é o dashboard para **operadores / DevOps / SRE** — quem monitoriza a saúde técnica do sistema.

Mostra:
- Taxa de ingestão de logs por segundo
- Latência dos serviços
- Estado dos SLOs (disponibilidade, latência p95, F1 do modelo)
- Contadores de eventos de segurança (rate limit hits, blocked auth)
- Métricas de deteção por regra

Requer conhecimento de PromQL para criar painéis personalizados.

---

## CI/CD — Resultados e Métricas

### "Pylint 102 testes, 87 passaram. CI threshold cumprido?"

Aqui há uma confusão de terminologia que vale a pena esclarecer:

**Pylint não tem "testes"** — tem **verificações de qualidade de código** (linting). O número 102/87 refere-se aos **testes pytest**, não ao Pylint.

**Pylint** avalia o código numa escala de 0 a 10. O CI tem `--fail-under=7.0` — se a pontuação cair abaixo de 7,0 o CI falha. Esta é uma verificação de qualidade, não uma contagem de testes.

**pytest (102 testes, 87 passaram):**
- 87 testes passaram — funcionalidade verificada
- 15 testes falharam — documentados, no backlog da S15, não bloqueantes
- Cobertura de 70,97%

**CI threshold de cobertura: cumprido.** O threshold está definido em 70% e o resultado foi 70,97%. O CI não falha por cobertura insuficiente.

Os 15 testes que falham são fixtures de configuração de `.pkl` que sofreram regressão com as mudanças de segurança da S14 — está identificado e será corrigido na S15.

---

### Load Test — 0 falhas

O load test foi executado com **Locust**, uma ferramenta de teste de carga Python.

**Configuração:** 50 utilizadores simultâneos durante 30 segundos.

**Resultado: 0 falhas** significa que nenhum pedido HTTP retornou um erro (5xx ou timeout) durante todo o teste. O sistema aguentou a carga simultânea sem degradar.

Métricas adicionais do teste:
- Latência mediana: 3 ms
- Latência p95: < 200 ms (dentro do SLO)
- Zero erros em toda a duração do teste

---

### Unit tests: 70,97%

**Cobertura de código** (code coverage) mede a percentagem de linhas de código que são executadas durante os testes automatizados. 70,97% significa que aproximadamente 71 de cada 100 linhas do código são exercidas pelos testes.

**Não significa que 70,97% do sistema está correto** — significa que 70,97% do código foi percorrido durante os testes. Linhas não cobertas são código que não tem teste associado.

**Threshold CI:** o CI está configurado para falhar se a cobertura cair abaixo de 70%. Com 70,97% está acima do limite por margem estreita — a S15 tem como objetivo elevar para ≥75%.

---

## Contexto Regulatório

### GDPR Art. 22 — Direito à explicação

O **Regulamento Geral de Proteção de Dados** (GDPR) no Artigo 22 estabelece que qualquer decisão automatizada com impacto significativo numa pessoa tem de ser explicável — o visado tem direito a saber *porquê* a decisão foi tomada.

**No projeto:** o SHAP (SHapley Additive exPlanations) implementa este direito. Para cada alerta gerado pelo ML, o sistema produz uma explicação que mostra quais as variáveis que mais pesaram na decisão (ex: "esta anomalia foi sinalizada principalmente porque a entropia do URL é muito alta e o número de pedidos por minuto deste IP é 40x acima do normal").

---

### AI Act (2024) — Sistemas de alto risco

O **AI Act** é a regulamentação europeia de inteligência artificial, aprovada em 2024. Classifica sistemas de IA por nível de risco e impõe obrigações proporcionais.

**Sistemas de alto risco** (entre outros) incluem IA usada em infraestruturas críticas e em segurança. Um sistema de deteção de ataques em rede pode ser classificado como alto risco se for usado em contextos críticos.

**Obrigações para alto risco:**
- documentação técnica detalhada
- explicabilidade das decisões
- supervisão humana (human oversight)
- testes de robustez e precisão

**No projeto:** o SHAP cobre explicabilidade, o human-in-loop (Goal D) cobre supervisão humana, e o MLflow cobre documentação e rastreabilidade.

---

### NIS2 — Cibersegurança obrigatória

**NIS2** (Network and Information Security Directive 2) é a diretiva europeia de cibersegurança, em vigor desde 2023, que obriga organizações em setores críticos a implementar medidas de segurança e a reportar incidentes.

**Exigências relevantes:**
- gestão de riscos de cibersegurança
- deteção e resposta a incidentes
- auditabilidade e logging
- medidas técnicas de proteção (autenticação, controlo de acesso, cifra)

**No projeto:** o sistema endereça NIS2 com rate limiting, validação de inputs, non-root containers, logging estruturado de eventos de segurança, e o incident workflow (Goal D) que documenta o ciclo de vida de cada incidente.

---

### Conformidade por design

**Conformidade por design** (compliance by design) significa que os requisitos regulatórios não são adicionados no final como uma camada de auditoria, mas estão integrados nas decisões de arquitectura desde o início.

No projeto: a escolha do SHAP não foi estética — foi porque o GDPR Art. 22 e o AI Act exigem explicabilidade. A arquitectura com logging estruturado foi desenhada para suportar auditoria NIS2. Os containers non-root foram implementados por requisito de menor privilégio (OWASP, NIS2), não por preferência.

---

## Posicionamento e Valor

### XAI aplicado a cibersegurança

**XAI (Explainable AI)** é a área de IA que desenvolve métodos para tornar as decisões dos modelos compreensíveis por humanos.

Em cibersegurança, a maioria dos sistemas de ML são "caixas negras" — dizem "é um ataque" sem explicar porquê. O projeto combina **novelty detection** (Isolation Forest) com **XAI** (SHAP), o que é pouco explorado na literatura. É um contributo metodológico concreto — não é só aplicar ML a logs, é fazê-lo de forma auditável e explicável.

---

### Novelty detection sem labels

O **Isolation Forest** é um modelo de **novelty detection** (deteção de novidade): é treinado **exclusivamente com dados normais** e aprende o que é "normal". Qualquer coisa que se desvie do padrão aprendido é sinalizada como anomalia.

Contrasta com **anomaly detection supervisionado**, que precisa de exemplos de ataques (labels) para treinar — o que é um problema porque ataques novos (zero-days) nunca aparecem nos dados de treino.

**Vantagem:** o Isolation Forest pode detetar ataques que nunca viu, porque o que está a medir é desvio do comportamento normal, não semelhança com ataques conhecidos.

---

### Publicável — contribuição real

A combinação de:
1. Isolation Forest para novelty detection em logs Web
2. SHAP para explicabilidade das anomalias detetadas
3. Ablation study comparando Rule engine, IF, RF, e híbrido

...num pipeline MLOps completo e open-source, é suficientemente original para submissão a uma conferência ou workshop de cibersegurança / MLOps. A literatura tem trabalhos em cada um destes tópicos separados — a combinação integrada com evidência empírica (ablation study) é o contributo.

---

### Equivale a €30k–€100k/ano SIEM

**SIEM (Security Information and Event Management)** é a categoria de software que agrega logs, deteta ameaças, e gere alertas de segurança. Soluções comerciais:

| Produto | Custo estimado/ano |
|---------|-------------------|
| Splunk Enterprise | €50k–€100k |
| IBM QRadar | €30k–€80k |
| Microsoft Sentinel | €20k–€60k |
| Elastic Security | €10k–€30k |
| **Log Monitor MLOps** | **€0** |

A diferença funcional: as soluções comerciais têm mais conectores e suporte enterprise. O Log Monitor tem algo que a maioria não tem nativamente: **explicabilidade por design** (SHAP) e **ML adaptativo open-source** (sem vendor lock-in).

---

## Goals do Projeto

### Goal D: API REST pública

Uma **API REST pública** é uma interface HTTP documentada, versionada e estável, desenhada para ser consumida por sistemas externos — não apenas pelo próprio dashboard interno.

**Diferença do que já existe:**
- As rotas Flask actuais (`/login`, `/admin`, `/api/upload`) são endpoints internos, não desenhados para consumo externo estável.
- A API pública do Goal D é uma camada separada, com versionamento (`/api/v1/`), documentação (OpenAPI/Swagger), autenticação por token, e contratos de resposta estáveis.

**Endpoints planeados:**
```
GET  /api/v1/alerts               → lista alertas com filtros
GET  /api/v1/alerts/{id}          → detalhe de um alerta
POST /api/v1/alerts/{id}/feedback → marcar FP/FN (human-in-loop)
GET  /api/v1/metrics/model        → métricas do modelo atual
GET  /api/v1/incidents            → incidentes por estado
```

**Para quê serve:** permite a um SIEM externo, um script de automação, ou uma ferramenta de orquestração consumir os dados e alertas do sistema sem depender do dashboard Streamlit.

---

### Alerting avançado (Goal D)

O Alertmanager já está a correr como microserviço. O que distingue o alerting atual do alerting avançado é o **tipo de evento** que dispara o alerta.

**O que já está integrado (S14 — operacional):**

| Alerta | Trigger | Visível em |
|---|---|---|
| `DataFreshnessHigh` | Dados no PostgreSQL mais velhos que o SLO (5 min) | Alertmanager + slide 12 da apresentação |
| `HighLatency` | Latência p95 acima de 200 ms | Alertmanager |
| `ServiceDown` | Healthcheck de um container falha | Alertmanager |
| Rate limit hits | IP excede limite numa rota sensível | Logs estruturados + contador Prometheus |
| Blocked auth | Tentativa de login bloqueada | Logs estruturados |

Estes alertas são todos **de infraestrutura e operações** — dizem que o sistema está em mau estado, não que o negócio (a deteção) está a degradar.

---

**O que o Goal D vai integrar (ainda não existe):**

| Alerta | Trigger | Sprint |
|---|---|---|
| `ModelDegradation` | F1 do modelo retrained inferior ao modelo em produção | S18 |
| `IncidentBacklog` | Muitos incidentes em estado `NEW` sem transição para `INVESTIGATING` | S21–S22 |
| `BenchmarkDrift` | Diferença significativa entre métricas no dataset sintético e no CICIDS-2017 | S19 |

Estes alertas são de **negócio e de modelo** — dizem que a qualidade da deteção está a degradar, não que o servidor caiu. É a diferença entre "o sistema está ligado" e "o sistema está a funcionar bem".

---

### CICIDS-2017

**CICIDS-2017** (Canadian Institute for Cybersecurity Intrusion Detection dataset, 2017) é o dataset de referência da literatura académica para avaliação de sistemas de deteção de intrusões. Foi publicado por Sharafaldin, Lashkari e Ghorbani (2018) e é o benchmark mais citado na área.

**O que contém:** tráfego de rede real capturado durante 5 dias num ambiente controlado, com ataques reais executados contra uma infraestrutura de teste. Inclui:

| Tipo de ataque | Exemplos |
|---|---|
| DoS / DDoS | Slowloris, GoldenEye, Hulk, LOIC UDP |
| Brute Force | FTP-Patator, SSH-Patator |
| Web Attacks | SQL Injection, XSS, Command Injection |
| Infiltration | Backdoor, reverse shell |
| Botnet | ARES botnet |
| PortScan | nmap com vários modos |
| Tráfego normal | HTTP, HTTPS, FTP, SSH, email |

**Porquê é importante para o projeto:**

Até à S19, o modelo foi avaliado exclusivamente em dados sintéticos gerados pelo próprio `traffic_generator.py` do projeto. Dados sintéticos têm uma limitação crítica: foram gerados com as mesmas regras que inspiraram o modelo, o que pode inflar artificialmente as métricas (F1=0,838 pode ser mais fácil de atingir em dados que o próprio sistema ajudou a definir).

O CICIDS-2017 é **tráfego real** de ataques reais — um modelo que generaliza bem para este dataset demonstra que aprendeu padrões genuínos, não artefactos do dataset sintético.

**O que o Goal D (S19) vai medir:**
- correr o Isolation Forest e o ensemble no CICIDS-2017 sem retreinar
- comparar F1 e ROC-AUC: dados sintéticos vs CICIDS-2017
- se a diferença for grande, indica overfitting ao dataset sintético
- se a diferença for pequena, valida que o modelo generaliza

**Limitação conhecida:** o CICIDS-2017 é tráfego de rede (pcap + flows), não logs HTTP estruturados como os do projeto. Será necessária adaptação do feature engineering para alinhar os formatos — isso faz parte do trabalho da S19.

---

### Sumário dos Goals

| Bloco | Sprints | O que inclui |
|-------|---------|-------------|
| **Goals A+B** | S1–S13 | Infraestrutura, ML, monitorização, CI/CD — concluído |
| **Goal C** | S14–S16 | Security hardening, demo, documentação intercalar — S14 concluído |
| **Goal D** | S17–S23 | API REST pública, alerting avançado, dashboard avançado, LIME, incident workflow, relatório final |

**"Docker Orchestration + Monitorização + Dashboard + Testing + CI/CD"** = Goals A+B (o que está feito)

**"API REST Pública + Alertas + Dashboard Avançado + Relatório Final"** = Goal D (o que vem a seguir)
