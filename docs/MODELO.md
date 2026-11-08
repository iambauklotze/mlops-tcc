# Especificação do modelo (P-18)

> Aprovada em 08/11/2026. Substitui a P-01. **Todos os limiares são heurísticos e ajustáveis**: nenhum foi medido ainda, e o gate G1 (14/11) os calibra. Mudanças nesta especificação exigem nova proposta.

## 1. Pergunta de produto e personas

"*Este navio acabou de fundear em Santos ou no Rio. Quanto tempo ele vai esperar até atracar?*"

| | **Principal: planejador** (importador ou exportador) | **Secundário: agente marítimo** |
|---|---|---|
| Saída que usa | previsão de espera do navio, **P10 / P50 / P90 em horas** | alertas de anomalia e visão da fila por porto |
| Erro que mais dói | **subestimar** a espera | perder uma mudança brusca na fila |
| Métrica | MAE do P50 e cobertura do P90 | alertas úteis com poucos falsos alarmes |

Quando faltar tempo, o que serve à persona principal não é cortado.

## 2. Eventos derivados do AIS

Valem só para navios de carga e tanque (tipo AIS 70–89).

| Evento | Definição |
|---|---|
| Início do fundeio | dentro do polígono de fundeio, SOG < 0,5 nó por ≥ 30 min; o início é o primeiro ponto da sequência |
| Atracação | dentro do polígono de cais, SOG < 0,5 nó por ≥ 30 min |
| **Espera (rótulo)** | atracação − início do fundeio, no mesmo porto, sem sair da caixa do porto entre os dois eventos |
| Saída sem atracar | navio deixa a caixa depois de fundear; fica fora do treino, mas é contado e reportado |

- O `NavigationalStatus` é só um sinal auxiliar, porque é preenchido à mão.
- Os polígonos de fundeio e de cais são desenhados dentro das caixas validadas em 07/11, a partir dos dados reais.
- Episódios com lacuna de AIS acima de 6 h recebem `label_quality = low` e são reportados separados.

## 3. Momento da previsão e anti-vazamento

- A previsão é emitida quando o fundeio é **confirmado** (30 min depois do início).
- Todas as variáveis usam apenas dados disponíveis até esse instante, e um teste automatizado verifica isso.

## 4. Variáveis (v1)

| Grupo | Variáveis |
|---|---|
| Fila | navios fundeados, navios atracados, chegadas ao fundeio em 24 h, atracações em 24 h |
| Navio | tipo AIS (carga ou tanque), comprimento |
| Calendário | hora do dia, dia da semana |
| Porto | identificador, mediana da espera nos últimos 7 dias |

Clima fica fora da v1.

## 5. Baselines

| | Regra |
|---|---|
| **B0 · histórico** | quantis da espera dos últimos 7 dias, por porto |
| **B1 · fila** | (navios à frente + 1) × mediana do intervalo entre atracações nos últimos 7 dias |

## 6. Modelo candidato

- Gradient boosting com perda quantílica, um modelo para cada quantil (P10, P50, P90), sobre `log1p(horas)`.
- A biblioteca será escolhida na proposta de stack.

## 7. Avaliação

- **Walk-forward semanal:** treina com as semanas até *k*, testa na semana *k*+1. Split aleatório é proibido, por causa do vazamento via estado compartilhado da fila.
- **Escolha do campeão:** menor **MAE do P50**, desde que a **cobertura do P90 seja ≥ 85%** (ou seja, no máximo 15% das esperas reais acima do P90).
- **Métricas reportadas:** MAE do P50 (h), pinball loss média, cobertura do intervalo P10–P90 (meta ≈ 80%) e cobertura do P90; todas por porto.
- **Censura:** treinar só com chegadas anteriores a (data de corte − P95 da espera observada), e reportar a taxa de censura.
- **Critério honesto:** se o modelo não vencer os baselines, isso é resultado e é apresentado como tal.

## 8. Rótulo atrasado e monitoramento

O rótulo chega quando o navio atraca. O log de previsões é cruzado com as atracações confirmadas.

1. **Qualidade do dado:** cobertura e lacunas, vindas do coletor.
2. **Drift de entrada:** PSI diário das variáveis de fila contra a referência de treino.
3. **Drift da previsão:** distribuição do P50 emitido.
4. **Desempenho real:** MAE móvel e cobertura do P90 sobre os rótulos que já amadureceram.

## 9. Retreino

- **Agenda:** semanal.
- **Gatilho:** MAE móvel pior que o do B0 por 3 dias seguidos, **ou** PSI > 0,25 numa variável de fila.
- **Promoção (champion/challenger):** o modelo novo só entra se vencer o atual no período mais recente, respeitando o critério da seção 7.

## 10. Anomalias de fluxo (persona secundária)

- **Principal:** z-score robusto (mediana e MAD dos últimos 7 dias) do número de navios fundeados e da taxa de chegada, por porto e por hora. Alerta quando |z| > 3.
- **Comparação:** Isolation Forest sobre o mesmo vetor horário.
- **Avaliação:** anomalias **sintéticas injetadas**, sempre rotuladas como sintéticas, mais análise qualitativa de eventos reais, se ocorrerem.

## 11. Gate G1 (14/11, com 7 dias de dados)

Projetar para 28/11 o número de esperas completas com `label_quality` normal:

| Projeção | Decisão |
|---|---|
| Santos ≥ 150 **e** Rio ≥ 50 | alvo principal nos 2 portos |
| Santos ≥ 150, Rio < 50 | previsão de espera só em Santos; o Rio fica com anomalias e monitoramento |
| Santos entre 100 e 150 | decisão do Luiz, com os números na mesa |
| Santos < 100 | **Plano B:** alvo = navios fundeados em t+12 h, por porto e por hora, com baselines de persistência e sazonal; usa os mesmos polígonos e eventos |

## Fora da v1

Clima, reprevisão a cada hora, previsão antes da chegada (ETA), ANTAQ como validação externa do rótulo, e modelos de sobrevivência (estes só se a censura passar de ~20%).
