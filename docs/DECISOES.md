# Registro de decisões (ADR curto)

Formato: data · ID · status. Contexto, decisão e consequências. Decisões só entram aqui após resposta explícita do Luiz (`APROVO`, `REJEITO`, `AJUSTE`).

---

## 2026-11-06 · P-05 · Aprovada (via PE-0a) · Coleta antecipada desde o dia 1

**Contexto.** O AISStream não oferece histórico nem replay ("events are not durably replayed", documentação). O tempo de coleta é o gargalo do TCC (~4 semanas até 05/12/2026).
**Decisão.** O primeiro artefato da Fase 0 é um coletor mínimo que grava o payload bruto, append-only, particionado por data/hora, com checksum. O teste de cobertura (G0) é calculado sobre esse mesmo bruto.
**Consequências.** As horas do teste de cobertura já viram dataset. Se o formato de armazenamento mudar, o bruto continua reprocessável porque guarda o frame original.

## 2026-11-06 · P-06 · Aprovada (via PE-0a) · uv para ambiente e lockfile

**Contexto.** Reprodutibilidade exige dependências travadas.
**Decisão.** `uv` (pyproject + `uv.lock`); `pytest` e `ruff` como ferramentas de desenvolvimento.
**Alternativas descartadas.** poetry (mais lento), pip-tools (mais manual).
**Consequências.** `uv sync --frozen` reproduz o ambiente, inclusive no Docker. Reversível migrando o `pyproject.toml`.

## 2026-11-06 · P-09 · Aprovada com AJUSTE (P-11) · Coletar amplo, modelar poucos portos

**Contexto.** O custo que cresce por porto é o rótulo (geofences validadas, máquina de estados, testes), não a coleta.
**Decisão.** A coleta assina a costa brasileira inteira (bbox única, aproximada). A modelagem fica restrita aos portos-alvo (ver P-11).
**Consequências.** Há portos reserva caso algum falhe no G0; mais disco (não estimado). Base para a Release 2.

## 2026-11-06 · P-11 · Aprovada · Portos-alvo: Santos, Paranaguá e Itajaí

**Contexto.** O Luiz decidiu trabalhar com os "3 maiores portos". Como o critério de tamanho não foi verificado contra o ranking da ANTAQ, o Luiz escolheu explicitamente o trio.
**Decisão.** Modelagem em Santos, Paranaguá e Itajaí. A restrição vale só para a modelagem; a coleta segue nacional (P-09). Rio de Janeiro e Suape saem dos alvos.
**Consequências.** Escopo de rótulo menor e mais profundo. As bboxes em `config/collect.yaml` são grosseiras e **não validadas**; validação visual com o Luiz antes da Fase 2.

## 2026-11-06 · P-10 · Aprovada · Docker e Compose desde a Fase 0

**Contexto.** A coleta precisa ficar de pé 24/7 e religar sozinha; a Fase 4 exige demo com um comando.
**Decisão.** O coletor roda em container (`restart: unless-stopped`, usuário não-root, chave só via `env_file` em tempo de execução, limite de memória, healthcheck por heartbeat).
**Alternativa descartada.** Serviço `systemd` no WSL (funcionaria, mas não serve à demo).
**Consequências.** O coletor depende do Docker Desktop estar em execução ("Start Docker Desktop when you sign in" precisa estar ativo). Reversível: o coletor roda fora do container com `uv run`.

## 2026-11-06 · P-12 · Aprovada · Coleta contínua em Lightsail (conta AWS exclusiva do TCC)

**Contexto.** Coletar no notebook arrisca lacunas (suspensão, reinícios, quedas de energia e rede). O Luiz criou uma conta AWS exclusiva para o TCC (nova experiência de cadastro, plano gratuito, US$ 100 em créditos, válido até 06/05/2027) e uma instância Lightsail.
**Decisão.** O coletor roda em Lightsail: Ubuntu 24.04, 1 GB de RAM, 2 vCPUs, 40 GB SSD, região us-east-2 (atribuída automaticamente ao projeto, sem opção de São Paulo). Firewall só com SSH/22; acesso apenas por chave; Docker do repositório do Ubuntu; atualizações automáticas. A coleta começa direto no servidor (opção A), sem coleta paralela no notebook.
**Alternativas descartadas.** EC2 com SSM (mais complexa), Hetzner (sem ganho de portfólio), notebook (risco de lacunas), Oracle Free (risco de a instância ser recuperada).
**Consequências.** O custo é coberto pelos créditos (preço do plano não verificado). O disco de 40 GB pode ser insuficiente para a costa inteira, e o volume precisa ser medido. Se a conta não migrar para o plano pago até 06/05/2027, ela é apagada 90 dias depois (risco para a Release 2). Reversível: copiar os dados e apagar a instância e o IP estático.

## 2026-11-07 · P-14 · Aprovada · Portos-alvo pós-G0: Santos e Rio de Janeiro (substitui P-11)

**Contexto.** Gate G0 com 19 h de coleta (07/11, 00:01–18:59 UTC), medido sobre a coleta nacional (P-09) com bboxes aproximadas:

| Região | MMSI | Carga/tanque | Intervalo mediano | G0 |
|---|---|---|---|---|
| Santos | 143 | 106 | 9,0 min | PASS/PASS |
| Rio de Janeiro (Guanabara + entrada) | 157 | 51 | 9,0 min | PASS/PASS |
| Itajaí | 11 | 7 | 9,0 min | FAIL/PASS |
| Paranaguá | 0 | 0 | n/a | FAIL/FAIL |
| Vitória/Vila Velha + Tubarão/Praia Mole | 5 | 3 | 12,0 min | FAIL/FAIL |
| Itaguaí/Sepetiba (referência) | 0 | 0 | n/a | FAIL/FAIL |

**Decisão.** Os portos-alvo da modelagem passam a ser **Santos e Rio de Janeiro**. Saem Paranaguá e Itajaí. O Espírito Santo foi avaliado a pedido do Luiz e descartado pela cobertura. A coleta continua nacional, e o coletor não foi reiniciado.
**Alternativas descartadas.** Manter Itajaí como porto de baixa cobertura (poucas atracações para treinar); Espírito Santo (sem cobertura); Plano B de outra região ou domínio (desnecessário, porque 2 portos passaram).
**Consequências.** A comparação por porto fica mais estreita, mas os perfis são distintos (Santos: porto público de contêiner e granel; Rio: baía urbana com mais embarcações de apoio). A bbox do Rio é aproximada e precisa de validação visual antes da Fase 2. A cobertura gratuita do AISStream no Brasil se concentra no Sudeste, o que é um achado em si.

## 2026-11-07 · P-13 · Aprovada · Documentação da jornada do projeto

**Contexto.** O Luiz quer estudar o projeto depois e gerar uma apresentação profissional para a banca, destacando decisões, dificuldades, gargalos e restrições.
**Decisão.** Criar `docs/JORNADA.md` (diário cronológico por sessão, com a etiqueta [BANCA] e só fatos verificados) e `docs/ESTADO.md` (foto atual, para retomar o trabalho). `docs/DECISOES.md` continua sendo o registro formal.
**Consequências.** Cerca de 15 minutos por sessão para manter. A apresentação da banca será gerada a partir dessa base, na Fase 5.

## 2026-11-06 · Desvio do PE-0a · Aprovado · Dependência `pyyaml`

**Contexto.** `config/collect.yaml` exige um parser YAML, não previsto no PE-0a.
**Decisão.** Adicionar `pyyaml` (escolha do Luiz entre pyyaml e TOML).
**Consequências.** Uma dependência a mais, pequena e madura.

## 2026-11-07 · P-15 · Aprovada (PE-1) · pre-commit com gitleaks e ruff

**Contexto.** O repositório vai para o GitHub, e a chave do AISStream existe no `.env` local. Um vazamento é um incidente.
**Decisão.** Adotar `pre-commit` (dependência de dev, 4.7.0) com:
- gitleaks v8.30.0;
- pre-commit-hooks v6.0.0 (arquivos grandes, chave privada, YAML/TOML, fim de linha);
- ruff local via `uv run`, para usar a mesma versão do `uv.lock`.

O histórico inteiro (3 commits) foi varrido antes do primeiro push: nenhum vazamento.
**Alternativa descartada.** detect-secrets (mais falsos positivos e exige arquivo de baseline).
**Consequências.** O primeiro commit numa máquina nova baixa o gitleaks (pre-commit compila com Go). A varredura da pasta acusa o `.env`, como esperado, porque ele contém a chave e é ignorado pelo Git. Reversível: apagar `.pre-commit-config.yaml` e remover a dependência.

## 2026-11-07 · P-16 · Aprovada (PE-1) · CI no GitHub Actions

**Decisão.** O workflow `ci` roda a cada push e PR, em três jobs:
- pre-commit em todos os arquivos + pytest;
- gitleaks sobre o histórico completo (`gitleaks-action@v2`);
- `docker build` da imagem do coletor.

**Alternativa descartada.** Sem CI (perde a evidência automática de qualidade para a banca).
**Consequências.** Os minutos de CI de repositório privado são limitados no plano gratuito (*cota não verificada*). **Ajuste aprovado em 08/11:** a `gitleaks-action@v2` falhou no primeiro push da branch (tentou varrer a partir do pai do commit raiz, que não existe, e varreu 0 bytes). Ela foi trocada pela imagem oficial `ghcr.io/gitleaks/gitleaks:v8.30.0`, a mesma versão do hook local, que sempre varre o histórico inteiro. Desde a execução 42430671392 o CI está verde.

## 2026-11-07 · P-17 · Aprovada (PE-1) · Repositório privado, licença MIT e dados brutos fora do Git

**Contexto.** O AISStream não publica termos de uso (ver `docs/LICENCAS.md`).
**Decisão.**
- Repositório GitHub **privado** até a defesa, com o Aliclei como colaborador. A abertura ao público é decisão posterior.
- Código sob **MIT**.
- Dados AIS brutos **nunca** no Git nem publicados; só código e agregados.
- `main` só recebe merge quando o Luiz pedir.

**Consequências.** A banca verá o código por convite ou depois da publicação.

## 2026-11-08 · P-18 · Aprovada · Desenho do modelo: espera de cada navio na chegada ao fundeio (substitui P-01)

**Contexto.** A P-01 (rótulo de espera derivado do AIS) não definia o momento da previsão, a saída, os baselines nem o critério de sucesso. Revisão feita em 07/11 com o deck do TCC e a página oficial do MBA.
**Decisão.** A especificação completa está em [`MODELO.md`](MODELO.md). Em resumo:
- **alvo:** espera fundeio → atracação, derivada do AIS, prevista quando o fundeio é confirmado;
- **saída:** P10/P50/P90 em horas;
- **personas:** principal = planejador (previsão); secundária = agente marítimo (anomalias);
- **baselines:** B0 histórico e B1 de fila;
- **avaliação:** walk-forward semanal; campeão = menor MAE do P50 com cobertura do P90 ≥ 85%;
- **monitoramento:** 4 camadas, incluindo o desempenho real com rótulo atrasado;
- **retreino:** semanal ou por gatilho;
- **anomalias:** z-score robusto, com Isolation Forest como comparação;
- **gate G1** em 14/11, com Plano B (fila em t+12 h).

**Alternativas descartadas.** Fila em t+h como alvo principal (vira o Plano B); rótulo da ANTAQ (atraso de semanas ou meses); reprevisão a cada hora; modelos de sobrevivência (extensão).
**Consequências.** Define as semanas 2 a 4. A stack (tracking, serving, orquestração) e a RAM do servidor ficam para propostas próprias. Os limiares são heurísticos até o G1. Reversível por nova proposta; o Plano B é a saída prevista.

## 2026-11-08 · PE-2 · Aprovado · Semana 2: camada tratada, polígonos, episódios e G1

**Decisão.** Branch `feat/phase2-episodes`. A semana tem 7 passos:
1. cópia só de leitura dos dados do servidor;
2. camada tratada em Parquet;
3. polígonos candidatos tirados dos dados;
4. validação dos polígonos pelo Luiz;
5. extrator de esperas;
6. relatório do G1;
7. execução do G1 em 14/11.

**Consequências.** A correção da medição de lacunas do coletor fica fora do PE-2, porque o deploy exige reiniciar o coletor, o que precisa de confirmação separada.

## 2026-11-08 · P-19 · Aprovada · polars e shapely na camada de dados

**Contexto.** A camada tratada precisa caber no servidor de 1 GB, e o geofencing precisa de teste ponto-em-polígono confiável.
**Decisão.** `polars` para tabelas e Parquet; `shapely` para polígonos. As licenças (MIT, BSD-3) estão em `LICENCAS.md`.
**Alternativas descartadas.** pandas (mais memória); DuckDB (mais uma linguagem, SQL); ray-casting escrito à mão.
**Consequências.** Medido: a normalização de 1,7 dia leva cerca de 5 s, com 127 MB de pico. Reversível com `uv remove` e reescrita do `normalize.py`.

## 2026-11-08 · PE-2 passo 4 · Aprovado · Polígonos de fundeio e cais congelados

**Contexto.** Os polígonos candidatos foram gerados a partir de onde navios de carga e tanque realmente param, usando 07/11 00:01 a 08/11 17:59 UTC de dados. Eles foram mostrados ao Luiz num mapa com as posições reais.
**Decisão.** Os polígonos foram congelados em `config/geofences.yaml`:
- Santos: 2 de fundeio e 7 de cais;
- Rio: 1 de fundeio e 8 de cais.

**Consequências.** Esses polígonos definem os rótulos. Qualquer mudança neles exige nova proposta, e os rótulos precisam ser recalculados.

## 2026-11-08 · P-20 · Aprovada · Espera só conta com a chegada ao fundeio observada

**Contexto.**
- Na rodada preliminar do G1, a recepção de AIS no fundeio de Santos se mostrou fraca: intervalo mediano de 18 min e 37 silêncios acima de 6 h, contra 7 min nos cais.
- Por isso, muitos navios aparecem já fundeados, e o início real da espera fica desconhecido.

**Decisão.** Um episódio só vira rótulo útil se `arrival_observed` for verdadeiro: o ponto anterior ao fundeio está em movimento ou fora do fundeio, e no máximo 6 h antes. Os demais episódios continuam no relatório, contados à parte.
**Alternativa descartada.** Usar o primeiro ponto ouvido como início do fundeio. Daria mais rótulos, mas subestimaria a espera sem aviso, e esse é o erro mais caro para o planejador.
**Consequências.** Menos rótulos, principalmente em Santos. O teto preliminar por chegadas ficou em 144, abaixo dos 150 da tabela do G1. Reversível com uma linha em `scripts/g1_report.py`.
