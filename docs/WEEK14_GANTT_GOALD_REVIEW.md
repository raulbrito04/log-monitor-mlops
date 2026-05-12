# Goal D — Revisão e Recomendações do Gantt

Data da revisão: 2026-05-03

## Alinhamento calendário ↔ sprints

| Sprint | Datas |
|--------|-------|
| S1  | 26 Jan – 01 Fev |
| S2  | 02 Fev – 08 Fev |
| S3  | 09 Fev – 15 Fev |
| S4  | 16 Fev – 22 Fev |
| S5  | 23 Fev – 01 Mar |
| S6  | 02 Mar – 08 Mar |
| S7  | 09 Mar – 15 Mar |
| S8  | 16 Mar – 22 Mar |
| S9  | 23 Mar – 29 Mar |
| S10 | 30 Mar – 05 Abr |
| S11 | 06 Abr – 12 Abr |
| S12 | 13 Abr – 19 Abr |
| S13 | 20 Abr – 26 Abr |
| S14 | 27 Abr – 03 Mai ← estado atual |
| S15 | 04 Mai – 10 Mai |
| S16 | 11 Mai – 17 Mai ← Apresentação Intercalar |
| S17 | 18 Mai – 24 Mai |
| S18 | 25 Mai – 31 Mai |
| S19 | 01 Jun – 07 Jun |
| S20 | 08 Jun – 14 Jun |
| S21 | 15 Jun – 21 Jun |
| S22 | 22 Jun – 28 Jun |
| S23 | 29 Jun – 05 Jul |
| —   | 11 Jul → Entrega relatório final |
| —   | 01 Ago → Discussão |

---

## Recomendações por tarefa

### S17 (18–24 Mai) — Human-in-loop: FP/FN marking UI
**Actual:** S17–S18 (2 semanas, partilhadas com CICIDS em S18)
**Recomendado:** S17 apenas para a parte de UI/dashboard
**Razão:** A estrutura de dados já está preparada (confirmado no V2_REPORT_REVIEW). Uma semana é suficiente para a página de marcação no dashboard.

---

### S18 (25–31 Mai) — Human-in-loop: Retraining pipeline automation
**Actual:** incluído no bloco S17–S18 sem separação clara
**Recomendado:** S18 dedicada ao backend — pipeline de retraining automático
**Razão:** Separar UI de pipeline evita que uma parte atrase a outra. 2 semanas no total para human-in-loop mantêm-se, mas sem sobreposição com CICIDS.

---

### S19 (1–7 Jun) — Benchmark CICIDS-2017
**Actual:** S18–S19 (2 semanas)
**Recomendado:** S19 apenas (1 semana)
**Razão:** Não é uma feature nova — é data loading + correr o pipeline existente + gerar métricas. 2 semanas é excessivo. 1 semana focada chega.

---

### S20 (8–14 Jun) — LIME / counterfactual explanations
**Actual:** S19–S20 (2 semanas)
**Recomendado:** S20 apenas (1 semana)
**Razão:** SHAP já está implementado. LIME é trabalho aditivo em cima do que existe, não uma nova pipeline. 1 semana é realista.

---

### S21–S22 (15 Jun – 28 Jun) — Incident workflow NEW→INVESTIGATING→RESOLVED
**Actual:** S20–S21 (2 semanas, com sobreposição em S20 com LIME)
**Recomendado:** Deslocar para S21–S22, sem sobreposição
**Razão:** Esta feature toca no schema da BD, no dashboard e na API — merece as 2 semanas intactas. Deslocá-la 1 semana elimina o conflito com LIME e não perde tempo.

---

### S23 (29 Jun – 5 Jul) — Buffer + polimento final
**Actual:** S23 = "Cobertura de testes ≥85%"
**Recomendado:** Renomear para "Buffer / documentação final / polimento"
**Razão:** A cobertura ≥85% não pode ser uma tarefa de 1 semana no fim — tem de ser incremental em cada sprint de S17 a S22. Se deixares para S23, qualquer atraso anterior compromete o limiar CI. S23 deve ser a semana de fechar lacunas, rever documentação e preparar a entrega de 11 Jul.

---

### Após S23 (6 Jul – 1 Ago) — Cloud deployment POC
**Actual:** S22 (1 semana, antes do relatório)
**Recomendado:** Mover para depois da entrega do relatório final (11 Jul)
**Razão:** Há 3 semanas livres entre a entrega (11 Jul) e a discussão (1 Ago). O Cloud POC é a tarefa com maior risco de escorregar — se der problemas numa semana antes do relatório, compromete tudo. Depois do relatório é o lugar certo: se funcionar enriquece a discussão; se não funcionar não custa nada.

---

## Gantt revisto (comparação)

| Sprint | Datas          | Actual                      | Recomendado                          |
|--------|----------------|-----------------------------|--------------------------------------|
| S17    | 18–24 Mai      | Human-in-loop (UI+retrain)  | Human-in-loop: UI dashboard          |
| S18    | 25–31 Mai      | Human-in-loop + CICIDS ⚠️   | Human-in-loop: retraining pipeline   |
| S19    | 1–7 Jun        | CICIDS + LIME ⚠️            | CICIDS-2017 benchmark                |
| S20    | 8–14 Jun       | LIME + Incident ⚠️          | LIME / counterfactuals               |
| S21    | 15–21 Jun      | Incident workflow           | Incident workflow                    |
| S22    | 22–28 Jun      | Cloud POC (1 sem.)          | Incident workflow (continuação)      |
| S23    | 29 Jun–5 Jul   | Cobertura ≥85%              | Buffer + polimento + documentação    |
| —      | 11 Jul         | Entrega final               | Entrega final ✓                      |
| —      | Jul–Ago        | —                           | Cloud POC opcional (best-effort)     |

---

## Resumo das alterações

1. Eliminar as 3 sobreposições (S18, S19, S20 tinham duas tarefas em paralelo)
2. Comprimir CICIDS-2017 de 2 semanas para 1 (não é feature nova, é avaliação)
3. Comprimir LIME de 2 semanas para 1 (SHAP já existe como base)
4. Deslocar Incident workflow para S21–S22 (liberta S20 para LIME)
5. Converter S23 em semana de buffer/polimento (cobertura deve ser incremental S17–S22)
6. Mover Cloud POC para depois de 11 Jul (zona de baixo risco, entre entrega e discussão)
