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

## 2026-11-06 · Desvio do PE-0a · Aprovado · Dependência `pyyaml`

**Contexto.** `config/collect.yaml` exige um parser YAML, não previsto no PE-0a.
**Decisão.** Adicionar `pyyaml` (escolha do Luiz entre pyyaml e TOML).
**Consequências.** Uma dependência a mais, pequena e madura.
