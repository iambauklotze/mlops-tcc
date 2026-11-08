# Estado do projeto

> Arquivo vivo: atualizado ao fim de cada sessão. Histórico completo em [JORNADA.md](JORNADA.md); decisões em [DECISOES.md](DECISOES.md).

**Última atualização:** 08/11/2026 (Fase 0 fechada: repositório no GitHub, CI verde)
**Fase atual:** **Fase 0 concluída.** Gate G0 aprovado com 2 portos (Santos e Rio de Janeiro); coleta contínua em andamento.
**Prazo:** entrega em 05/12/2026.

## Feito e verificado

- Coletor rodando no Lightsail desde **07/11/2026 00:01 UTC** (compressão confirmada, container `healthy`).
- **G0 (19 h de dados):** Santos e Rio passam nos dois critérios; Paranaguá, Itajaí e Espírito Santo reprovam. Portos-alvo redefinidos na P-14.
- **Caixas de Santos e Rio validadas visualmente** pelo Luiz em 07/11: todos os navios fundeados, atracados e parados caem dentro delas.
- Servidor: Ubuntu 24.04, 1 GB de RAM com 1 GB de swap, 40 GB de disco, us-east-2, firewall só SSH/22, SSH só por chave, atualizações automáticas, UTC.
- Conta AWS exclusiva (plano gratuito, US$ 100, até 06/05/2027), com 2FA e orçamento zero-spend.
- Documentação: `DECISOES.md` (P-05 a P-17), `JORNADA.md`, `ESTADO.md`, `LICENCAS.md`, `README.md`, `CLAUDE.md`, `LICENSE` (MIT).
- pre-commit com gitleaks e ruff; histórico varrido, sem vazamentos (P-15).
- Repositório **privado** [iambauklotze/mlops-tcc](https://github.com/iambauklotze/mlops-tcc), com a branch `feat/minimal-collector` (padrão por enquanto; `main` ainda não existe).
- **CI verde** em 08/11 (execução 42430671392): pre-commit + testes, gitleaks no histórico completo (8 commits, sem vazamentos) e build da imagem.

## Em andamento

- Coleta contínua da costa brasileira inteira, com a modelagem focada em Santos e Rio.

## Próximos passos

1. ✅ ~~Validar visualmente as bboxes de Santos e Rio~~: aprovadas em 07/11 (ver JORNADA). Na Fase 2, desenhar os polígonos de fundeio e de cais dentro delas.
2. ✅ ~~Resto da Fase 0~~ (PE-1), concluído em 08/11. Falta convidar o Aliclei (precisa do usuário GitHub dele).
3. **Decidir o desenho do modelo** (proposta P-18, com base na revisão de 07/11): alvo principal = espera de cada navio na chegada ao fundeio, saída em quantis, dois baselines, gate G1 em 14/11 com plano B de previsão da fila.
4. Fase 1:
   - **corrigir a medição de lacunas** (incluir o silêncio antes do timeout, registrando o horário do último frame);
   - corrigir o teste com o formato real das mensagens (`latitude`, `longitude`, `time_utc` em minúsculas);
   - validação de esquema e dead-letter;
   - métricas de ingestão;
   - cópia periódica dos dados para o notebook;
   - atualizar actions do CI para versões em Node.js 24 (`checkout`, `setup-uv`) e fixar a imagem do runner antes da migração do `ubuntu-latest` para Ubuntu 26.

## Pendências de aprovação

- **P-18** desenho do modelo (a escrever; substitui a P-01 e responde o "momento da previsão") ·
- **P-01** rótulo de espera derivado do AIS · **P-02** critério de cobertura e Plano B (aplicado de fato no G0; falta a aprovação formal) · **P-03** replay com drift simulado · **P-04** TCC antes da plataforma.

## Perguntas em aberto (para o Luiz)

- **Q4:** o que exatamente é entregue em 05/12 e como a banca avalia.
- Divisão de tarefas com o Aliclei.
- Nível em cada ferramenta (para calibrar o modo mentor).
- Momento da previsão: na chegada ao fundeio, atualizada a cada hora, ou antes da chegada.
- Onde está o `ais_coverage_test.py` original. O deck está em `Downloads/TCC – MLOps para congestionamento portuário (AIS).pdf`.

## Riscos abertos

- **Apenas 2 portos:** comparação por porto mais estreita. Se um deles perder cobertura, sobra um só.
- **Lacunas subestimadas no relatório** até a correção da Fase 1. Houve 1 silêncio real de pelo menos 2 min em 19 h.
- AISStream em beta, sem SLA.
- Fim do plano gratuito da AWS em 06/05/2027.
- Disco: cerca de 4,4 MB/dia, risco descartado.

## Como retomar

```bash
ssh mlops-tcc 'cd ~/mlops-tcc && docker compose ps && docker compose logs --tail 5'
```
```bash
ssh mlops-tcc 'cd ~/mlops-tcc && docker compose run --rm --no-deps collector python scripts/coverage_report.py --since-hours 24'
```
```bash
ssh mlops-tcc 'tail -n 5 ~/mlops-tcc/data/ops/connection_events.jsonl'
```

## Lista v2 (depois do TCC)

- Plataforma web (Release 2), avaliação de ANTAQ e Global Fishing Watch como fontes históricas, migração do plano AWS antes de 06/05/2027.
