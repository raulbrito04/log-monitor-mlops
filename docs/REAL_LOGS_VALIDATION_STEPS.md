# Validação Com Logs Reais — Passo a Passo

## Objetivo

Validar o sistema com uma fonte **real** de logs, sem depender apenas dos logs sintéticos do projeto.

O protocolo recomendado é:

- **fonte real Apache/Nginx**
- **tráfego benigno real**
- **tráfego malicioso controlado**
- **critérios de avaliação**

Isto permite provar duas coisas ao mesmo tempo:

1. a pipeline funciona com logs reais
2. a deteção é testada em cenários controlados e mensuráveis

---

## O que já está preparado no projeto

Na branch `week15-RealLogsValidation`, o projeto já suporta:

- ingestão com `--format json`
- ingestão com `--format apache_combined`
- ingestão com `--format auto`
- fallback para campos em falta no feature engineering
- sanitização de `NaN`/`inf` antes do scoring ML

Ficheiros principais:

- `src/log_processor/ingester.py`
- `scripts/ingest.sh`
- `docker/scripts/run_ingester_loop.sh`
- `docker/docker-compose.yml`

---

## Pré-requisitos

Antes de começar, convém ter:

- a branch `week15-RealLogsValidation`
- o ambiente Python funcional (`./venv/bin/python`)
- a stack Docker disponível
- um ficheiro real de `access.log` de `Nginx` ou `Apache`

Se o ficheiro existir numa máquina Linux/WSL, os caminhos típicos são:

- `/var/log/nginx/access.log`
- `/var/log/apache2/access.log`

---

## Passo 1 — Confirmar a branch certa

```bash
git branch --show-current
```

Resultado esperado:

```text
week15-RealLogsValidation
```

---

## Passo 2 — Limpar alterações que não pertencem a esta fase

Se não quiseres manter o rascunho atual do guião:

```bash
git restore -- docs/GUIAO_APRESENTACAO.md
```

Isto evita misturar trabalho de apresentação com trabalho técnico.

---

## Passo 3 — Obter uma fonte real de logs

Criar uma pasta local para esta fase:

```bash
mkdir -p logs/real
```

Copiar o ficheiro real para dentro do projeto:

```bash
cp /var/log/nginx/access.log logs/real/access.log
```

ou

```bash
cp /var/log/apache2/access.log logs/real/access.log
```

Se o ficheiro estiver noutra máquina, exporta uma amostra e coloca-a em:

```text
logs/real/access.log
```

Notas:

- não precisa de ter ataques reais
- o importante é ser um log real gerado por um servidor real
- a parte maliciosa será gerada de forma controlada no passo seguinte

---

## Passo 4 — Separar baseline benigno e cenário malicioso

O ideal é trabalhar com **duas amostras**:

- `logs/real/access_benign.log`
- `logs/real/access_attack.log`

### Opção recomendada

1. Recolher uma janela de tráfego benigno normal
2. Guardar essa fatia como `access_benign.log`
3. Gerar tráfego malicioso controlado contra o mesmo servidor
4. Guardar a nova fatia como `access_attack.log`

Se estiveres a recolher tudo do mesmo `access.log`, podes fazer a separação por momento temporal ou por número de linhas.

Exemplo com as últimas linhas:

```bash
tail -n 500 logs/real/access.log > logs/real/access_benign.log
```

Depois de gerar o tráfego malicioso controlado:

```bash
tail -n 500 logs/real/access.log > logs/real/access_attack.log
```

Se quiseres mais rigor, usa snapshots antes e depois do teste para evitar mistura.

---

## Passo 5 — Gerar tráfego benigno real

Se tiveres um servidor `Nginx/Apache` de teste, produz algum tráfego normal:

- abrir páginas normais no browser
- fazer navegação simples
- chamar endpoints legítimos

Também podes usar `curl` de forma benigna:

```bash
curl -s http://localhost/
curl -s http://localhost/health
curl -s http://localhost/login
curl -s "http://localhost/search?q=normal"
```

Objetivo:

- produzir logs reais benignos
- observar se o sistema gera poucos ou nenhuns falsos positivos

---

## Passo 6 — Gerar tráfego malicioso controlado

Isto deve ser feito **apenas no teu ambiente de teste**.

Exemplos simples e controlados:

### Falhas repetidas de autenticação

```bash
for i in {1..10}; do
  curl -s -o /dev/null -X POST http://localhost/login
done
```

### Pedidos suspeitos a endpoints sensíveis

```bash
for path in /admin /phpmyadmin /wp-login.php /server-status; do
  curl -s -o /dev/null "http://localhost$path"
done
```

### Query strings suspeitas em ambiente controlado

```bash
curl -s -o /dev/null "http://localhost/search?q=' OR 1=1 --"
curl -s -o /dev/null "http://localhost/search?q=%3Cscript%3Ealert(1)%3C/script%3E"
```

Objetivo:

- gerar eventos maliciosos reais no `access.log`
- testar regras e scoring ML num cenário reproduzível

---

## Passo 7 — Ingerir o baseline benigno

Com a amostra benigna pronta:

```bash
./venv/bin/python src/log_processor/ingester.py logs/real/access_benign.log --format apache_combined --batch-size 500
```

ou usando o helper:

```bash
bash scripts/ingest.sh logs/real/access_benign.log 500 apache_combined
```

Resultado esperado:

- logs inseridos na tabela `raw_logs`
- poucas ou nenhumas falhas de parsing

---

## Passo 8 — Validar ingestão na base de dados

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT COUNT(*) AS total_logs, MIN(timestamp), MAX(timestamp) FROM raw_logs;"
```

Verificações úteis:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT log_type, COUNT(*) FROM raw_logs GROUP BY log_type ORDER BY COUNT(*) DESC;"
```

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT
      COUNT(*) AS total,
      COUNT(*) FILTER (WHERE ip IS NULL) AS missing_ip,
      COUNT(*) FILTER (WHERE method IS NULL) AS missing_method,
      COUNT(*) FILTER (WHERE endpoint IS NULL) AS missing_endpoint,
      COUNT(*) FILTER (WHERE status IS NULL) AS missing_status,
      COUNT(*) FILTER (WHERE response_time_ms IS NULL) AS missing_response_time
    FROM raw_logs;"
```

Objetivo:

- medir parsing com sucesso
- medir campos em falta
- perceber limitações reais do formato

---

## Passo 9 — Executar regras sobre o baseline benigno

```bash
./venv/bin/python src/detection/rule_engine.py --mode historical --days 30
```

Depois verificar os alertas:

```bash
docker compose -f docker/docker-compose.yml exec postgres \
  psql -U postgres -d logmonitor -c \
  "SELECT alert_type, severity, COUNT(*) FROM alerts GROUP BY alert_type, severity ORDER BY COUNT(*) DESC;"
```

O que esperamos no baseline benigno:

- poucos alertas
- idealmente poucos falsos positivos

---

## Passo 10 — Ingerir o cenário malicioso controlado

```bash
./venv/bin/python src/log_processor/ingester.py logs/real/access_attack.log --format apache_combined --batch-size 500
```

ou:

```bash
bash scripts/ingest.sh logs/real/access_attack.log 500 apache_combined
```

Depois voltar a correr o `rule_engine`:

```bash
./venv/bin/python src/detection/rule_engine.py --mode historical --days 30
```

Objetivo:

- verificar se as regras disparam no cenário malicioso controlado
- confirmar diferença clara entre benigno e malicioso

---

## Passo 11 — Validar a componente ML

### Se queres apenas validar ingestão + regras

Podes parar no passo anterior.

### Se queres validar também o caminho ML

Extrair features com os logs reais já ingeridos:

```bash
./venv/bin/python src/ml/feature_engineering.py
```

Se os modelos já existirem e quiseres scoring incremental:

```bash
./venv/bin/python src/ml/realtime_hybrid.py
```

Notas importantes:

- nesta fase **não é obrigatório retreinar já o modelo**
- primeiro queremos provar ingestão real end-to-end
- só depois decidimos se faz sentido novo treino ou apenas documentação de limitações

---

## Passo 12 — Validar dashboard e métricas

Abrir:

- Flask: `http://localhost:5001`
- MLflow: `http://localhost:5000`
- Grafana: `http://localhost:3000`
- Streamlit dashboard: `http://localhost:8501`
- Prometheus: `http://localhost:9090`

Conferir:

- logs aparecem na `raw_logs`
- alertas aparecem no dashboard
- métricas de monitorização atualizam
- baseline benigno e cenário malicioso produzem comportamento diferente

---

## Critérios de avaliação

No relatório e na análise final, registar pelo menos:

### 1. Parsing / ingestão

- número total de linhas
- número de linhas ingeridas
- taxa de sucesso no parsing
- campos em falta

### 2. Baseline benigno

- número de alertas
- tipos de alertas
- sinais de falsos positivos

### 3. Tráfego malicioso controlado

- número de alertas
- tipos de alertas disparados
- diferença face ao baseline benigno

### 4. Caminho ML

- se o scoring correu
- que limitações surgiram com logs reais
- se faltaram features relevantes

---

## O que não fazer

- não usar apenas logs sintéticos nesta fase
- não chamar benchmark externo de “validação real operacional”
- não inventar labels como se fossem ataques reais espontâneos
- não misturar apresentação/docs com estes commits técnicos

---

## Resultado esperado desta fase

No fim desta fase, deves conseguir afirmar com rigor:

- o sistema consegue ingerir uma fonte real de logs web
- a pipeline funciona ponta a ponta com dados reais
- o baseline benigno foi medido
- o tráfego malicioso controlado foi testado
- as limitações observadas ficaram documentadas

Isso é muito mais forte do que dizer apenas:

- “testei num dataset externo”
- ou “usei só logs sintéticos”

---

## Próximo passo depois disto

Quando esta validação estiver feita, então faz sentido decidir entre:

1. adaptar melhor features para logs reais
2. retreinar o modelo com mais dados reais/controlados
3. fazer benchmark complementar com `CICIDS-2017`
4. documentar gaps entre cenário real e cenário sintético
