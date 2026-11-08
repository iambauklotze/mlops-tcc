# Licenças e termos de uso

> Levantamento feito em 07/11/2026. Revisar sempre que entrar uma dependência ou uma fonte de dados nova.

## Código do projeto

Licença **MIT** (arquivo [`LICENSE`](../LICENSE)), em nome de Luiz Eduardo e Aliclei. A licença vale para o código; os dados coletados seguem as regras da fonte (abaixo).

## Fontes de dados

### AISStream (em uso desde 07/11/2026)

Páginas lidas: [aisstream.io](https://aisstream.io/), [documentação](https://aisstream.io/documentation) e [política de privacidade](https://aisstream.io/privacypolicy).

- **O AISStream não publica termos de uso.** As URLs `/terms`, `/terms-of-service` e `/tos` retornam 404. O rodapé do site só traz Documentation, Account, Privacy e Support.
- Nenhuma página permite ou proíbe expressamente armazenar, usar em pesquisa, usar comercialmente ou redistribuir os dados. Também não há exigência de atribuição.
- A política de privacidade trata dos dados do usuário da conta (IP, GitHub), não dos dados AIS.
- **Restrições técnicas documentadas:**
  - 3 conexões inscritas por conta e 3 por IP;
  - inscrição em até 3 s;
  - 1 atualização de inscrição por segundo;
  - proibição de conexão direta pelo navegador.
- A documentação também avisa que, desde setembro de 2026, conexões **sem compressão** têm limite de banda por usuário. Nosso coletor usa compressão, confirmada na Fase 0.
- **Garantias:** sem SLA, sem garantia de disponibilidade, e os eventos não podem ser reenviados ("not durably replayed").

**Postura adotada (conservadora), enquanto não houver termos:**
1. Os dados brutos ficam privados: no servidor e no notebook, **nunca no Git** (`data/` está no `.gitignore`).
2. O repositório público, se houver, publica apenas código e resultados agregados (métricas, gráficos por porto), sem arquivos de posições brutas.
3. Os trabalhos citam o AISStream como fonte.
4. Antes de publicar qualquer dataset derivado, perguntar ao provedor pelo canal de suporte ([GitHub](https://github.com/aisstream/issues)). **Ainda não foi feito.**

### ANTAQ (Estatístico Aquaviário): ainda não usada

Dado público do governo federal. **A licença ainda não foi verificada**; isso acontece antes do primeiro download.

### Clima: fonte ainda não definida

## Dependências Python

As licenças foram lidas dos metadados dos pacotes instalados pelo `uv.lock` em 07/11/2026. Todas são permissivas e compatíveis com MIT.

| Pacote | Versão | Licença | Uso |
|---|---|---|---|
| websockets | 17.4 | BSD-3-Clause | runtime |
| python-dotenv | 1.2.4 | BSD-3-Clause | runtime |
| PyYAML | 6.0.3 | MIT | runtime |
| polars (+ polars-runtime-32) | 2.1.0 | MIT | runtime: camada tratada (P-19) |
| shapely | 2.2.0 | BSD-3-Clause | runtime: geofencing (P-19) |
| numpy (transitiva do shapely) | 2.5.4 | BSD-3-Clause, com partes 0BSD, MIT, Zlib e CC0-1.0 | runtime |
| pytest | 9.2.0 | MIT | dev |
| ruff | 0.17.4 | MIT | dev |
| pre-commit | 4.7.0 | MIT | dev |
| dependências transitivas de dev (virtualenv, filelock, platformdirs, identify, cfgv, nodeenv, distlib, packaging, pluggy, iniconfig, Pygments, python-discovery) | — | MIT, BSD, Apache-2.0 ou PSF-2.0 | dev |

## Ferramentas externas

| Ferramenta | Licença | Uso |
|---|---|---|
| gitleaks | MIT | varredura de segredos (pre-commit e CI) |
| imagem `python:3.12-slim` | PSF e licenças do Debian | base do container |
| uv (`ghcr.io/astral-sh/uv`) | MIT ou Apache-2.0 | build do container |
