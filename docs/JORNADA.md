# Jornada do projeto

Diário cronológico da construção do projeto, feito para **estudo** e para a **apresentação à banca**.

## Como usar este diário

- Uma seção por sessão de trabalho, da mais antiga para a mais recente.
- Cada sessão registra: o que foi feito, **decisões** (com link para o ADR em [DECISOES.md](DECISOES.md)), **dificuldades**, **gargalos**, **restrições**, **riscos**, **lições aprendidas** e **evidências**.
- **[BANCA]** marca os pontos com maior valor para a apresentação.
- **Regra de honestidade:** só entram fatos verificados (comando executado e saída vista). Suposições aparecem marcadas como *não verificado*.
- Horários em UTC; Brasília = UTC−3.

## Linha do tempo

| Data (UTC) | Marco |
|---|---|
| antes de 06/11 | Projeto anterior (MVTec AD) rejeitado pela banca por falta de originalidade; novo tema: congestionamento portuário com AIS em streaming |
| 06/11 | Planejamento inicial (Passo 0), repositório criado, coletor implementado e testado |
| 06/11 | Conta AWS exclusiva do TCC e servidor Lightsail configurado |
| **07/11 00:01** | **Início da coleta contínua de AIS** (marco zero do dataset autoral) |
| 07/11 ~19:00 | **Gate G0**: Santos e Rio passam; Paranaguá, Itajaí e Espírito Santo reprovam; portos-alvo trocados sem perder coleta (P-14) |

---

## Sessão 1 · 06/11/2026 → 07/11/2026 00:05 UTC · Fundação e início da coleta

### Ponto de partida

- Prazo de entrega: **05/12/2026**, cerca de 4 semanas.
- Tema novo depois da rejeição do MVTec AD. O diferencial pretendido é um **dataset autoral coletado em streaming** e o monitoramento de um modelo cuja verdade-terreno chega atrasada. **[BANCA]**
- Regra de trabalho da dupla com o assistente de IA: nada é criado, alterado ou executado sem aprovação explícita (`APROVO` / `REJEITO` / `AJUSTE`), e toda decisão vira ADR.

### O que foi feito (em ordem)

1. **Planejamento (Passo 0).** Entendimento do projeto, lacunas identificadas, cronograma replanejado e propostas P-01 a P-04 (rótulo de espera derivado do AIS, critério de cobertura, drift simulado, prioridade do TCC sobre a plataforma). *P-01 a P-04 ainda aguardam aprovação formal.*
2. **Repositório** criado em `~/programming/projects/mlops-tcc` (WSL), com `git init -b main`.
3. **Pesquisa de dados históricos.** Resultado: o AISStream **não oferece histórico nem replay**. A documentação diz que os eventos "are not durably replayed". Alternativas mapeadas para avaliação futura: ANTAQ (atracações) e Global Fishing Watch (port visits). Um rastreador comercial foi descartado porque os termos proíbem usar os dados para treinar ou avaliar modelos de ML sem autorização escrita. **[BANCA]**
4. **Escopo de portos.** Decisão de coletar a **costa brasileira inteira** e modelar só **Santos, Paranaguá e Itajaí** (P-09 e P-11).
5. **Docker desde o início** (P-10), após discutir se ele era necessário já na coleta.
6. **Coletor implementado (PE-0a).**
   - Cliente WebSocket assíncrono com compressão, reconexão com backoff exponencial e timeout de inatividade.
   - Camada bruta append-only, particionada por data e hora (JSONL gzip), com checksum SHA-256 e proibição de sobrescrever arquivos finalizados.
   - Log de eventos de conexão e de lacunas, e heartbeat para o healthcheck.
   - Relatório de cobertura para o gate G0.
   - Evidências: 12 testes passando, ruff sem erros, imagem de 185 MB rodando como usuário não-root.
7. **Onde coletar: notebook ou nuvem.** Comparação de riscos e benefícios, depois de provedores (Hetzner, DigitalOcean, AWS, Google Cloud). Escolha: **AWS**, numa **conta exclusiva do TCC**.
8. **Conta AWS na "nova experiência" de cadastro (lançada em 16/09/2026).**
   - A conta é organizada em projetos, sem usuários IAM, com a região atribuída automaticamente (**us-east-2**, sem opção de São Paulo).
   - Plano gratuito com US$ 100 em créditos, válido até **06/05/2027**.
   - 2FA no provedor de login e orçamento "zero-spend" criados.
9. **Servidor Lightsail (PE-1).**
   - Máquina: Ubuntu 24.04.4, 1 GB de RAM, 2 vCPUs, 40 GB de SSD, IP estático.
   - Firewall: só SSH/22 aberto (a porta 80 foi removida).
   - Hardening: atualizações aplicadas e automáticas, swap de 1 GB, UTC, SSH só por chave e sem login de root (validado antes de aplicar), reinício controlado.
   - Código enviado por `rsync` sem o `.env`. O segredo foi criado pelo próprio Luiz no servidor, com permissão 600.
10. **Início da coleta: 07/11/2026 00:01:12 UTC.** Conexão confirmada com `CompressionEnabled: true`, container `healthy`. **[BANCA]**

### Decisões desta sessão

| ID | Decisão | Por que importa |
|---|---|---|
| [P-05](DECISOES.md) | Coletar desde o dia 1, gravando o bruto | Sem histórico na fonte, cada dia sem coletar é perdido |
| [P-06](DECISOES.md) | `uv` com lockfile | Reprodutibilidade |
| [P-09 / P-11](DECISOES.md) | Coletar amplo, modelar 3 portos | O custo por porto está no rótulo, não na coleta; a coleta ampla dá portos reserva |
| [P-10](DECISOES.md) | Docker desde a Fase 0 | Religa sozinho e é o mesmo ambiente da demo final |
| [P-12](DECISOES.md) | Lightsail numa conta AWS exclusiva | Tira a coleta (o gargalo) da dependência do notebook |
| [P-13](DECISOES.md) | Este diário | Rastreabilidade para estudo e para a banca |

### Dificuldades

- **A fonte de dados não tem histórico.** Isso impôs a ordem do projeto: coletar primeiro, construir o resto depois.
- **A documentação do AISStream diverge do dado real.** A documentação mostra `MetaData.Latitude` e `MetaData.Longitude`; o stream real envia `latitude`, `longitude` e `time_utc` em minúsculas, além de `MMSI_String`. O coletor não foi afetado, porque grava o frame inteiro. Um teste usa o formato da documentação e será corrigido na Fase 1. É uma evidência concreta da instabilidade de API prevista no planejamento. **[BANCA]**
- **O console da AWS era diferente do roteiro.** O passo a passo inicial (root, IAM, região São Paulo) supunha o console clássico. A conta caiu na nova experiência, onde não há IAM e a região é imposta. Foi preciso ler a documentação oficial e refazer o checklist.
- **Espaços reservados executados literalmente.** O comando com `NOME-DA-CHAVE` e o bloco de `~/.ssh/config` colado no terminal falharam. Os dois foram resolvidos sem dano.
- **Suposição não verificada do assistente.** Arquivos antigos em `~/.ssh` foram atribuídos a outro projeto sem verificação. O erro foi corrigido quando o Luiz apontou.

### Gargalos

- **Tempo de coleta:** é o principal gargalo do TCC. A coleta só começou no fim do dia 1.
- **Cobertura AIS terrestre:** ainda desconhecida por porto. É o gate G0.

### Restrições

- Prazo de 05/12/2026; apenas dados públicos ou simulados; manutenção preditiva fora do escopo.
- AISStream: beta, sem SLA, até 3 conexões por conta, conexão encerrada se o cliente não consumir rápido, sem histórico, sem acesso direto pelo navegador.
- AWS na nova experiência: região imposta (us-east-2), sem IAM, plano gratuito com US$ 100 de créditos e término em 06/05/2027.
- Servidor: 1 GB de RAM (por isso o swap) e 40 GB de disco.

### Riscos abertos

| Risco | Situação |
|---|---|
| Cobertura fraca em Paranaguá e Itajaí | Leitura parcial com **3,6 h** (07/11 00:01–03:39 UTC, madrugada): Santos com 104 MMSIs (70 de carga ou tanque); Itajaí com 9 (6); **Paranaguá com 0**, sem nenhuma mensagem nas células de 1° em volta do porto, ou seja, não é erro da bbox. A região do Rio tem 149 MMSIs. *Ainda não é o G0, que exige 24 a 48h.* O Rio é o reserva natural |
| Disco de 40 GB insuficiente | 688 KB em 3,6 h (cerca de 5 MB/dia pela extrapolação). **Risco praticamente descartado** |
| Quedas do AISStream | Reconexão automática; lacunas registradas em `data/ops/connection_events.jsonl` |
| Fim do plano gratuito da AWS (06/05/2027) | Sem migração, a conta é apagada 90 dias depois (afeta a Release 2) |
| Rótulo de espera (P-01) | Desenho proposto, ainda sem aprovação |

### Lições aprendidas

- **Verificar a fonte antes de desenhar o pipeline.** A ausência de histórico mudou a ordem do trabalho inteiro.
- **Ler o dado real, não só a documentação.** A divergência de campos apareceu nos primeiros 2 minutos.
- **Separar coleta de modelagem.** Coletar amplo custa pouco e protege contra a falha de cobertura de um porto.
- **Instruções operacionais precisam distinguir "comando" de "conteúdo de arquivo"** e evitar espaços reservados que possam ser executados literalmente.
- **Validar antes de aplicar mudanças arriscadas.** O `sshd -t` e um login de teste antes do reinício evitaram perder o acesso ao servidor.

### Evidências (comandos e saídas reais)

- Testes locais: `uv run pytest` resultou em `12 passed`; `uv run ruff check .` resultou em `All checks passed!`.
- Commit `5c8077b`: `feat(ingest): add containerized raw AIS collector`.
- Hardening: `sshd -T` mostrou `passwordauthentication no`, `kbdinteractiveauthentication no` e `permitrootlogin no`.
- Container: `id` dentro da imagem mostrou `uid=1000(app)`.
- Início da coleta (log do coletor):
  ```
  {"msg": "start", "ts": "2026-11-07T00:01:12.784589+00:00", ...}
  {"msg": "connected", "ts": "2026-11-07T00:01:13.327776+00:00", ...}
  {"msg": "subscription_confirmed", "message": {"CompressionEnabled": true}}
  ```
- Primeiros ~2 minutos: 39 mensagens e 30 MMSIs distintos. Tipos: `PositionReport`, `StandardClassBPositionReport`, `ShipStaticData`, `StaticDataReport`.
- Relatório de cobertura com 3,6 h de dados (`scripts/coverage_report.py --since-hours 24`), com 7.527 frames e 0 reconexões:

  | Porto | Reports de posição | MMSI | Carga/tanque | Intervalo mediano (min) | Critério MMSI | Critério intervalo |
  |---|---|---|---|---|---|---|
  | Santos | 2013 | 104 | 70 | 10,5 | PASS | FAIL |
  | Paranaguá | 0 | 0 | 0 | n/a | FAIL | FAIL |
  | Itajaí | 95 | 9 | 6 | 9,0 | FAIL | PASS |

### Continuação em 07/11: gate G0 (cobertura)

**O que aconteceu**
- Com 18,8 h de coleta, o relatório de cobertura mostrou Santos aprovado (106 navios de carga ou tanque, intervalo de 9 min), Itajaí fraco (7) e **Paranaguá zerado**.
- A pedido do Luiz, foram medidos candidatos substitutos sobre os dados já coletados, **sem coletar de novo**. Isso só foi possível porque a coleta é nacional (P-09). Ver a tabela na [P-14](DECISOES.md).
- **Decisão (P-14):** portos-alvo Santos e Rio de Janeiro. **[BANCA]**

**Dificuldades e achados**
- **A cobertura gratuita é concentrada no Sudeste.** Paranaguá, Itaguaí/Sepetiba e o canal de Vitória tiveram zero navios; Tubarão/Praia Mole, 1. O planejamento já tratava cobertura como risco bloqueante, e o gate G0 existia para isso. **[BANCA]**
- **Lacuna mal medida.** Às 04:30 UTC, o stream ficou 2 min sem enviar nada; o coletor detectou (timeout de inatividade) e reconectou em ~1 s. O relatório mostrou "0.0 min" de lacuna porque mede só o intervalo entre desconectar e reconectar, e não o silêncio anterior. A lacuna real foi de pelo menos 2 min. A correção (registrar o horário do último frame recebido) fica para a Fase 1. **[BANCA]**: lacunas "detectadas, medidas e nunca escondidas", inclusive quando a própria medição falha.
- O aviso `truncated or unreadable part … .inprogress` no relatório é esperado: é o arquivo da hora corrente, ainda sendo gravado.

**Evidências**
- 19 h: 40.460 frames, 331 navios com tipo conhecido, 1 reconexão (`IdleTimeoutError: no frame for 120s`, conexão anterior viva por 16.161 s).
- Disco: 3,5 MB em 19 h (cerca de 4,4 MB/dia), com 34 GB livres.

**Lições**
- Coletar amplo e decidir com dados: a troca de porto custou minutos de análise, não dias de coleta.
- Toda métrica operacional precisa ser conferida contra o evento bruto. O "0.0 min" parecia ótimo e estava errado.

### Continuação em 07/11: validação visual das caixas (Santos e Rio)

**O que aconteceu**
- Foi gerado um mapa interativo (página privada no claude.ai) com as posições reais de 07/11, 00:01–19:02 UTC, amostradas em 1 ponto por navio a cada 5 min (cerca de 6.900 pontos em Santos e 8.200 no Rio). Os pontos são coloridos por status AIS (fundeado, atracado, parado, em movimento), sobre as caixas do `config/collect.yaml`.
- **O Luiz aprovou as duas caixas como estão.**

**Evidências** (navios distintos, área exportada = caixa + ~0,1°)

| | Santos | Rio |
|---|---|---|
| Fundeados dentro / só fora | 56 / 0 | 73 / 0 |
| Atracados dentro / só fora | 62 / 0 | 53 / 0 |
| Parados (outro status) dentro / só fora | 54 / 0 | 67 / 0 |
| Extensão dos fundeados | 24°14′S–23°57′S, 46°22′W–46°08′W | toda dentro da Baía de Guanabara |

**Dificuldades e limitações**
- A página publicada não pode carregar mapas de fundo externos. A forma da água foi "desenhada" pelos próprios navios, com um link para o OpenStreetMap para comparar com a costa.
- A exportação só olhou ~11 km além das caixas; fundeios mais distantes não teriam aparecido (*não verificado além dessa margem*).
- As caixas são largas de propósito (incluem marinas, estaleiros, base naval, praias). A distinção fina (polígonos de fundeio e de cais) fica para a Fase 2.

**Lição**
- A validação foi feita com o comportamento real dos navios, e não só com a carta náutica: o dado mostra onde os navios efetivamente fundeiam. **[BANCA]**

### Continuação em 07/11: fechamento da Fase 0 (PE-1)

**O que foi feito**
- **pre-commit** com gitleaks, ruff e hooks de higiene (P-15). A varredura do **histórico completo** antes do primeiro push não encontrou vazamentos. A varredura da pasta acusou só o `.env`, que é ignorado pelo Git (comportamento esperado).
- **CI** no GitHub Actions (P-16): lint, testes, segredos no histórico e build da imagem. *Ainda não executado*, porque falta o repositório remoto.
- **README**, **CLAUDE.md**, licença **MIT** e **docs/LICENCAS.md** (P-17).
- Todas as dependências têm licença permissiva (MIT, BSD, Apache, PSF).

**Achado importante [BANCA]**
- **O AISStream não publica termos de uso.** Não há regra sobre armazenar, usar em pesquisa, redistribuir ou atribuir. Daí a postura conservadora: dado bruto privado, publicação só de agregados, e consulta ao provedor antes de qualquer dataset derivado.
- A documentação avisa que conexões **sem compressão** têm limite de banda desde setembro de 2026. A escolha de ativar compressão no coletor (Fase 0) evitou esse problema.

**Bloqueio**
- O repositório GitHub ainda não foi criado. O `gh` não está instalado no WSL, e a chave SSH do WSL não está cadastrada no GitHub (`Permission denied (publickey)`). Esse passo depende do Luiz.

### Material para a banca (rascunho)

- A narrativa "**dataset autoral nasce em 07/11/2026**", com a justificativa: a fonte não tem histórico, então a coleta foi priorizada.
- A decisão "coletar amplo, modelar estreito" como gestão de risco, comprovada no G0: Paranaguá e Itajaí substituídos pelo Rio sem perder coleta.
- A divergência entre a documentação e o dado real como caso concreto de API instável e de validação de esquema na entrada.
- A arquitetura de coleta: container não-root, bruto imutável com checksum, lacunas medidas e nunca escondidas.
- O processo de decisão rastreável: propostas e ADRs, com aprovação explícita.
- Segurança como gate: varredura de segredos no commit e no CI, e uma fonte de dados sem termos de uso tratada com postura conservadora.
