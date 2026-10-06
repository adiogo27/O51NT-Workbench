# O51NT Workbench

Workbench OSINT **local e single-user**, baseado no documento mestre `O51NT.pdf` (gerado em 02/10/2026).
Sem cloud, sem telemetria, sem chaves de API: tudo funciona por **deeplinks** e, onde permitido, **scraping ético**.

## Requisitos

- Linux (testado no Kali), bash
- Python 3.12+ (testado com 3.14)
- Node.js 18+ e npm (apenas para buildar o frontend)
- Um navegador (firefox, chromium, google-chrome, brave…)
- Opcional: Chromium para scraping com JavaScript. O Playwright usa o próprio navegador ou, se faltar, o `chromium`/`google-chrome` do sistema.
- Opcional, recomendado: **Docker** para o SearXNG local, que é a fonte das buscas nas subabas "Scraping ético".
  Sem ele, esses módulos funcionam só por deeplinks. No Kali: `sudo systemctl enable --now docker && sudo usermod -aG docker $USER` (depois relogue).
  O `run.sh` usa `docker compose`, `docker-compose` ou, na falta dos dois, `docker run`.

## Instalação e uso

```bash
./run.sh                     # cria .venv, instala deps, builda o frontend se precisar, sobe o backend e abre o navegador
./run.sh --browser chromium  # força um navegador
./run.sh --no-browser        # só o backend
./run.sh --rebuild           # força rebuild do frontend
./run.sh --no-searxng        # não tenta subir o SearXNG
./run.sh --reset-db          # backup consistente (data/o51nt.db.bak.<timestamp>) e recria o banco; evidências em disco são preservadas
./run.sh --dry-run           # mostra o que faria (Python, Node, navegadores detectados) sem executar nada
./run.sh --list-browsers
./stop.sh                    # encerra o backend
```

A aplicação fica em `http://127.0.0.1:8051/`; a documentação da API em `/docs`.
A escolha de navegador (`--browser X` ou o menu interativo) fica salva em `data/settings.json` → `preferencias.navegadorPadrao`
e vale para as próximas execuções. Também dá para alterar na aba **Tema**.
O SearXNG fica em `http://127.0.0.1:8080`; outra instância pode ser indicada com `O51NT_SEARXNG_URL`.

### Inicializador (um clique)

```bash
./iniciar.sh                 # sobe o backend (se ainda não estiver no ar) e abre uma aba no navegador padrão
./iniciar.sh --atalho        # (re)gera o lançador "O51NT Workbench.desktop" na raiz (rode de novo se mover a pasta)
./iniciar.sh --instalar      # coloca o lançador no menu de aplicativos e na área de trabalho
./iniciar.sh --desinstalar   # remove do menu e da área de trabalho
```

- **Navegador:** usa a preferência da aba **Tema** (`preferencias.navegadorPadrao`). Com `auto`, abre no navegador padrão
  do sistema (`xdg-open`). Só aceita nomes de navegadores conhecidos.
- **Sem terminal:** o progresso e os erros aparecem como notificações da área de trabalho, e a saída completa fica em
  `data/logs/iniciar.log`. Cliques repetidos não sobem dois backends: o segundo espera o primeiro terminar e só abre a aba.
- **GNOME:** o Nautilus não executa `.desktop` nem scripts com duplo clique dentro de pastas. Use `./iniciar.sh --instalar`
  (o item aparece na busca de aplicativos como "O51NT Workbench" e pode ser fixado no dash, além do ícone na área de
  trabalho com a extensão DING), ou clique com o botão direito em `iniciar.sh` → **Executar como um programa**.
  No Thunar/XFCE, o lançador da raiz funciona com duplo clique.

### Desenvolvimento

```bash
./test.sh                       # TUDO num comando: pytest paralelo + sequencial, Vitest, tsc e Playwright E2E
./test.sh --quick               # idem, sem o E2E
.venv/bin/pytest -n auto        # suíte completa em paralelo (xdist)
.venv/bin/pytest                # sequencial
.venv/bin/pytest backend/tests/unit/test_operators.py   # um módulo isolado
cd frontend && npm run dev      # Vite em :5173 com proxy /api → :8051
cd frontend && npm run test:unit # Vitest (paridade queryOperators.ts ↔ operators.py)
cd frontend && npm run test:e2e # Playwright E2E
cd frontend && npm run guia     # regenera "Guia O51NT — Op. Eleições 2026.pdf" (capturas reais em instância isolada) (sobe backend isolado em :8059 com banco temporário; usa o Chromium do sistema)
```

## Módulos

| Aba | O que faz | Deeplinks | Scraping ético |
|---|---|---|---|
| Query Builder | Painéis Precisão (`""`, `-`, `OR`, `()`, `*`), Temporal (`before:`, `after:`), Escopo (`site:`, `-site:`, `filetype:`, `inurl:`, `intitle:`, `intext:`) e **X/TweetDeck** (`since:`, `until:`, `from:`, `to:`, `@`, `-is:retweet`, `is:`, `has:`, `lang:`, `min_*:`, `AND`); preview ao vivo, validação, 22 templates (18 do PDF mestre + 4 strings do boletim Op. Eleições), histórico com retenção, localidades IBGE/DNIT | Google, Bing, DuckDuckGo, Startpage + X (recentes), TikTok, YouTube, Google Notícias | via SearXNG local |
| Monitores + **Radar** | Vários monitores pesquisando **ao mesmo tempo**: o Radar coleta feeds públicos (RSS/Atom de imprensa, Mastodon por hashtag, feed pessoal do Google Alertas) a cada N min e casa cada item novo com a query de **todos** os monitores ativos (mesma sintaxe do Query Builder: AND/OR/parênteses, frases, -negação, #hashtag, site: em modo estrito, after:/since:…). Hits com fonte, data e termos casados; alertas JSONL/webhook; "adicionar ao boletim" em um clique; cron por monitor, timeline e deeplinks como antes | ✓ (inclui X/TikTok/YouTube/Google Notícias) | ✓ feeds (robots.txt, 1 req/3 s, backoff) |
| Agenda | Compromissos por candidato/dia, tipo, cidade/UF, rodovias federais (normalizadas e cruzadas com a base DNIT), selo de impacto em rodovia, queries de monitoramento (Google `after:` e X `since:`), criação de monitor, export CSV/JSON/ICS | ✓ | — |
| Boletim | Itens do dia por seção (notícias, fake news, manifestações, imagem institucional…) com fonte e evidência; **perfis vigiados** (handle normalizado, menções no X/Google, monitor); consolida agenda, hashtags, convites e perfis; exporta Markdown/JSON/HTML imprimível **no formato do boletim Op. Eleições 2026** | ✓ | — |
| Convites | Queries do PDF para `chat.whatsapp.com` e `t.me/joinchat`; tabela com export CSV/JSON | ✓ | via SearXNG local |
| Hashtags | CRUD, coleta em trends24/OneMillionTweetMap, rastreio periódico, gráfico SVG + série temporal | ✓ | ✓ |
| Imagens | Upload (vira evidência com SHA-256) → links para Google Lens, TinEye, Yandex, Lenso, Sensity | ✓ | — |
| Ferramentas | As 16 ferramentas externas do PDF mestre + **Checagem de fatos** (AFP Checamos, Comprova, Lupa, Aos Fatos, g1 Fato ou Fake, Boatos.org, Estadão Verifica, TSE, Google Fact Check Explorer) + **Busca em redes** (X recentes, TikTok, Instagram por hashtag, YouTube, Facebook, Google Notícias); URL pré-preenchida quando a ferramenta aceita | ✓ | — |
| Evidências | Upload, galeria, verificação de hash, busca por SHA-256 (dedup e prova de primeira coleta), manifesto JSONL, export ZIP (`manifest.json` + `SHA256SUMS`) | — | — |
| Tema | Cores, raio, fonte, tamanho 12–24 px, presets; persistido em `data/settings.json` | — | — |

## Arquitetura

```
frontend/ (Vite + React + TS + Tailwind + componentes estilo shadcn + Zustand + React Query)
   └─ npm run build → backend/static/  (servido pelo FastAPI)
backend/app/
   main.py            FastAPI + lifespan (init DB, seed, scheduler) + fallback de SPA
   config.py          pydantic-settings (prefixo O51NT_)
   db.py              SQLModel + SQLite (WAL, check_same_thread=False)
   models/            tabelas SQLModel (query, template, monitor, evidence, hashtag, invite) + settings (JSON)
   schemas/           DTOs Pydantic
   routers/           query_builder, scraping, monitors, invites, tools, evidence, hashtags, images, settings,
                      agenda, perfis, boletim
   services/
     operators.py     tokenizador/validador O(n)
     query_compose.py montagem de blocos + templates + deeplinks
     searxng_client.py busca (fonte primária) na instância local do SearXNG — httpx async, timeout 15 s, 1 retry
     scraper.py       páginas públicas: fila asyncio, 2 workers, robots.txt, 1 req/3 s por domínio, timeout 20 s,
                      1 retry, backoff persistente (domain_backoff) 1h → 6h → 24h; Playwright só p/ OneMillionTweetMap
     scheduler.py     APScheduler AsyncIOScheduler; jobs em memória reconstruídos da tabela `monitor` no startup
     retention.py     poda do histórico (idade/teto, configurável em Tema)
     radar.py         parser RSS/Atom, matcher da sintaxe do Query Builder, ciclo de coleta + casamento + alertas
     agenda.py        queries de monitoramento do evento (cidade + rodovias DNIT + tipo), ICS (RFC 5545) e CSV
     boletim.py       perfis (normalização de handle/URL, menções) e renderização do boletim (Markdown/HTML)
     evidence_store.py SHA-256 em streaming, manifesto JSONL, ZIP
     hashtag_tracker.py, alerts.py, locations.py
data/                 o51nt.db, evidence/, alerts/, logs/ (JSONL), settings.json, searxng/ (config do container)
docker-compose.yml    serviço searxng (127.0.0.1:8080); template de config em deploy/searxng/settings.yml
```

## Coleta: scraper ético e SearXNG

**Páginas públicas** (trends24, OneMillionTweetMap) passam pelo scraper ético:
- Só páginas públicas, sem login, sem burlar paywall ou captcha.
- `robots.txt` checado antes de cada URL (`urllib.robotparser`; se o robots.txt der erro 5xx ou de rede, a coleta é **negada**).
- 1 requisição a cada 3 s por domínio, fila global e concorrência 2.
- User-Agent: `O51NT-Workbench/1.0 (+local; contato: usuario local)` (sem acento, porque headers HTTP só aceitam ASCII).
- 403/429 → domínio em **backoff persistente** (tabela `domain_backoff`): 1 h, depois 6 h, depois 24 h. Um sucesso depois do prazo zera a escada. Consulte em `GET /api/scraper/status`.
- Todo resultado guarda URL de origem, horário e SHA-256 do conteúdo.

**Buscas em buscadores** (subaba "Scraping ético" do Query Builder e de Convites) passam pela **instância local do SearXNG**:
O Bing proíbe `/search` no robots.txt, e o scraper ético se recusa a consultá-lo. A recusa do DuckDuckGo registrada antes foi, na verdade, um timeout de rede: o scraper trata erro de rede no robots.txt como "negado".

> **Transparência:** o SearXNG é uma metabusca. Ele consulta DuckDuckGo, Bing e Startpage como um cliente de busca
> e **não aplica o robots.txt** desses buscadores. O app mitiga isso com uma consulta por clique do operador (ou por
> monitor), baixo volume, instância privada em `127.0.0.1` e nenhum crawling de páginas de resultado. Avalie se esse uso
> atende à sua política. Se não atender, rode com `--no-searxng` e use só os deeplinks.

## Guia em PDF

`Guia O51NT — Op. Eleições 2026.pdf` (na raiz) é o passo a passo, com capturas de tela reais, de como usar cada
recurso para produzir o boletim "INFORMAÇÕES RELEVANTES": hashtags, notícias, fake news, manifestações em rodovias,
agenda dos candidatos, imagem institucional, grupos e perfis. Fonte em `deploy/guia/` (HTML + imagens); regenere com
`cd frontend && npm run guia`.

## Legenda de status (relatórios e checklists)

- `[x]` Funcionalidade implementada e validada ao vivo
- `[~]` Implementada, mas limitada por terceiros (bloqueio, CAPTCHA, HTML sem dados); documentada abaixo. **Não significa "incompleto".**
- `[ ]` Não implementada

## Radar — como os monitores pesquisam de verdade

Buscadores bloqueiam coleta automática (CAPTCHA/robots.txt), então o Radar usa o que foi feito para máquina ler:
**feeds**. Onze fontes verificadas vêm cadastradas (Agência Brasil, g1, Folha, UOL, Metrópoles, Poder360, CNN Brasil,
Estadão e a hashtag `#eleicoes2026` no Mastodon). A cada ciclo (padrão 10 min, ajustável em **Tema**), o Radar:

1. coleta cada fonte ativa pelo scraper ético (robots.txt, 1 req/3 s por domínio, backoff em 403/429);
2. casa os itens novos com a query de **todos** os monitores ativos de uma vez (modo `termos`, recomendado para
   imprensa, ignora `site:`; modo `estrito` exige o domínio);
3. grava os hits (único por monitor + URL), dispara os alertas do monitor e mostra tudo em **Monitores → Resultados**.

Para ter a **busca do Google** no Radar: crie um alerta em google.com/alerts com a sua query, escolha *Entregar em: Feed
RSS* e cadastre a URL do feed em **Fontes do radar** marcando "ignorar robots.txt" (o `robots.txt` do google.com não
cobre feeds pessoais; é um feed que o próprio Google entrega a você). Hashtags em qualquer instância Mastodon:
`https://<instancia>/tags/<hashtag>.rss`. YouTube, Bluesky e gov.br/TSE não oferecem feed acessível (robots ou 404).

## Limitações aceitas (por design)

O O51NT Workbench **entrega ao analista a query certa e o deeplink certo, e deixa a decisão com ele**. Ele não tenta
ser um crawler furtivo. Os itens abaixo são fronteiras deliberadas do produto, não bugs pendentes:

- **Não burla CAPTCHA nem rate-limit, nunca.** No teste real de 05/10/2026, todos os buscadores (DuckDuckGo, Qwant:
  CAPTCHA; Brave: HTTP 429; Startpage: desativado upstream por captcha) recusaram acesso automatizado. A coleta parou aí,
  e esse é o comportamento correto.
- **SearXNG** consulta os buscadores como cliente de busca: **não aplica o robots.txt** deles e **não respeita
  operadores do Google** (`site:`, `inurl:`, `before:`, aspas, `OR`…). Por isso o Query Builder desabilita "Buscar via
  SearXNG" quando a query contém qualquer um desses operadores (`frontend/src/lib/queryOperators.ts`, espelho de
  `operadores_google` no backend, com casos compartilhados em `shared/google_operator_cases.json`). A **mesma regra**
  vale para a aba **Convites**: como as queries de convite do PDF sempre usam `site:`, `OR`, aspas e parênteses, o botão
  fica desabilitado ali, com o mesmo aviso e o deeplink como alternativa (componente único `SearxngSearchButton`).
- **Busca de convites via SearXNG** funciona tecnicamente, mas os motores bloqueiam ou ignoram as queries do PDF.
  **O deeplink é o caminho confiável.**
- **OneMillionTweetMap: encerrado.** O HTML público não expõe hashtags (os tweets carregam dinamicamente no mapa).
  A fonte está desabilitada na interface.
- **DuckDuckGo:** um timeout de rede ao buscar o robots.txt é tratado como "negado" (conservador). Um relatório antigo
  confundiu isso com uma proibição no robots.txt; a afirmação foi corrigida.
- **Hashtags:** a comparação ignora acentos e caixa (`#Eleicoes2026` ≡ `#Eleições2026`). As formas originais ficam
  guardadas e aparecem como "variantes".
- **Google Notícias:** o `robots.txt` não libera `/rss/`, então não há coleta automática de notícias — a seção
  "Notícias relevantes" do Boletim é assistida (deeplink + registro manual com evidência).
- **Operadores do X/TweetDeck** (`since:`, `-is:retweet`, `from:`…) só funcionam no X. O Query Builder os valida e
  avisa; nos demais motores viram texto literal, e a busca via SearXNG fica desabilitada quando aparecem.

## Avisos legais

- **LGPD (Lei 13.709/2018):** use apenas para finalidades legítimas, como segurança pública, investigação autorizada ou exercício regular de direitos (art. 7º, IX; art. 11). Guarde só o necessário para a investigação. Os dados ficam só na sua máquina; apagar `data/` remove tudo.
- **Termos de uso:** cada site externo tem os próprios termos. O app não faz login, não usa APIs privadas e não contorna bloqueios. A responsabilidade pelo uso é do operador.
- Convites de grupos e hashtags podem conter dados pessoais de terceiros: trate-os com sigilo.

## Limitações

- Busca reversa de imagem local exige upload manual no provedor; a busca direta só funciona se você informar a URL pública da imagem.
- **Teste real em 05/10/2026 (Kali, Docker rootless): a busca via SearXNG retornou 0 convites úteis.**
  DuckDuckGo ficou inacessível desta rede (timeout TCP) e depois passou a pedir CAPTCHA; o Startpage está `inactive`
  upstream nesta versão do SearXNG (captcha de prova de trabalho); o Bing responde, mas ignora os operadores
  (`site:`, aspas, `#`). Mojeek, Brave e Qwant também foram testados e recusaram (CAPTCHA ou HTTP 429). O app não
  tenta burlar CAPTCHA nem rate-limit. Na prática, convites e hashtags em redes sociais funcionam pelos **deeplinks**.
- Docker rootless: o container passa `data/searxng/` para um subuid (ex.: 100976), e seu usuário perde a permissão de
  editar esses arquivos. Para editar: `docker exec -u searxng o51nt-searxng vi /etc/searxng/settings.yml` (ou apague
  com `docker run --rm -v "$PWD/data/searxng:/x" alpine rm -rf /x/settings.yml`) e depois `docker restart o51nt-searxng`.
- Sem Docker utilizável, o SearXNG não sobe e as subabas de busca mostram "SearXNG indisponível".
- A imagem do SearXNG está fixada em `searxng/searxng:2026.10.4-d48c4b555` (`docker-compose.yml` e `run.sh`). Para atualizar, troque a tag nos dois arquivos.
- **Dívida técnica (B3):** os handlers async acessam o SQLite de forma síncrona, o que bloqueia o event loop por alguns
  milissegundos. Para uso single-user isso é aceitável. Migre para `aiosqlite` ou handlers `def` se houver 3 ou mais
  usuários simultâneos ou latência acima de 50 ms nos endpoints.
- Os operadores `before:`/`after:` só funcionam de forma confiável no Google; o app avisa a incompatibilidade em cada botão.
- A base de localidades é um recorte embutido (27 UFs, 27 capitais, 30 rodovias federais).
- Sem autenticação: o servidor escuta só em `127.0.0.1`.
