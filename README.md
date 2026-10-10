# O51NT Workbench

Workbench OSINT para monitoramento eleitoral (boletim "Op. Eleições 2026"), baseado no documento mestre `O51NT.pdf`.
Roda de dois jeitos:

- **Local, sem login** (modo de desenvolvimento e uso individual): `./run.sh` sobe tudo em `http://127.0.0.1:8051/`.
- **Na VPS, com login por e-mail + código e vários usuários**: `https://o51nt.sentinela.api.br`, implantado pelos
  scripts de `deploy/vps/` (HTTPS, systemd com watchdog, backup diário, Telegram e assistente de IA via OpenClaw).

Sem telemetria. Nenhuma chave paga no núcleo: a coleta funciona por **deeplinks**, **feeds públicos** e, onde permitido,
**scraping ético**. Integrações com IA e e-mail são opt-in e as chaves ficam só no `.env` da VPS (nunca no repositório).

## Requisitos

- Linux (testado no Kali e no Ubuntu 24.04 da VPS), bash
- Python 3.12+ (`.venv` criado pelo `run.sh`)
- Node.js 22+ e npm (para buildar o frontend; a VPS usa Node 24)
- Um navegador (firefox, chromium, google-chrome, brave…)
- Opcional: Chromium para scraping com JavaScript (o Playwright usa o próprio ou o do sistema)
- Opcional, recomendado: **Docker** para o SearXNG local (`127.0.0.1:8080`), fonte das buscas nas subabas "Scraping ético".
  Sem ele, esses módulos funcionam só por deeplinks. No Kali: `sudo systemctl enable --now docker && sudo usermod -aG docker $USER`.
- Opcional: OCR (`requirements-cv.txt`, instalado por padrão pelo `run.sh`) e CLIP (`requirements-ml.txt`, `./run.sh --ml`)
  para o módulo Convocações.

## Instalação e uso (local)

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
  (o item aparece na busca de aplicativos como "O51NT Workbench"), ou clique com o botão direito em `iniciar.sh` →
  **Executar como um programa**. No Thunar/XFCE, o lançador da raiz funciona com duplo clique.

### Desenvolvimento e testes

```bash
./run.sh --ml                   # instala o perfil "completo" do módulo Convocações (PyTorch CPU + open_clip, ~1 GB)
./run.sh --sem-ocr              # não instala o OCR (rapidocr); Convocações fica só com léxico + pHash + QR
./run.sh --reset-searxng        # recria data/searxng/settings.yml a partir do template, preservando o secret
./test.sh                       # TUDO num comando: pytest paralelo + sequencial, Vitest, tsc e Playwright E2E
./test.sh --quick               # idem, sem o E2E
.venv/bin/pytest -n auto        # suíte completa em paralelo (xdist)
.venv/bin/pytest backend/tests/unit/test_operators.py   # um módulo isolado
cd frontend && npm run dev      # Vite em :5173 com proxy /api → :8051
cd frontend && npm run test:unit # Vitest (paridade queryOperators.ts ↔ operators.py)
cd frontend && npm run test:e2e # Playwright E2E (sobe um backend isolado em :8059 com banco temporário)
cd frontend && npm run guia     # regenera "Guia O51NT — Op. Eleições 2026.pdf" (capturas reais em instância isolada)
```

Estado da suíte (2026-10-10): 395 testes pytest (unitários + integração via `TestClient`; 1 pulado quando os modelos de
OCR/CLIP não estão instalados), 43 Vitest, 11 cenários Playwright. **Regra do projeto: tudo verde antes de qualquer commit
ou implantação; nunca remover um teste para passar.** A mesma suíte roda no GitHub Actions a cada push e pull request
(`.github/workflows/ci.yml`: jobs `backend`, `frontend` e `e2e`).

Testes com autenticação usam a fixture `cliente_auth` (`backend/tests/integration/test_auth_router.py`), que captura os
códigos em vez de enviar e-mail. O assistente de IA é testado com o `FakeOpenClaw` de `backend/tests/conftest.py`.

## Módulos

| Aba | O que faz | Deeplinks | Coleta automática |
|---|---|---|---|
| Query Builder | Painéis Precisão (`""`, `-`, `OR`, `()`, `*`), Temporal (`before:`, `after:`), Escopo (`site:`, `-site:`, `filetype:`, `inurl:`, `intitle:`, `intext:`) e **X/TweetDeck** (`since:`, `until:`, `from:`, `to:`, `@`, `-is:retweet`, `is:`, `has:`, `lang:`, `min_*:`, `AND`); preview ao vivo, validação, 22 templates, histórico com retenção, localidades IBGE/DNIT | Google, Bing, DuckDuckGo, Startpage + X (recentes), TikTok, YouTube, Google Notícias | via SearXNG local |
| Monitores + **Radar** | Vários monitores ao mesmo tempo: o Radar coleta **feeds públicos** (RSS/Atom de imprensa, Mastodon por hashtag, feed pessoal do Google Alertas) e **páginas HTML sem feed** (tipo `pagina`, com hash de conteúdo e intervalo próprio) a cada N min e casa cada item novo com a query de **todos** os monitores ativos (sintaxe do Query Builder). Hits com fonte, data e termos casados; alertas JSONL/webhook/**Telegram**; "adicionar ao boletim" em um clique; monitores com `ia=True` alimentam o assistente de IA | ✓ | ✓ feeds e páginas (robots.txt, 1 req/3 s, backoff) |
| Agenda | Compromissos por candidato/dia, tipo, cidade/UF, rodovias federais (base DNIT), selo de impacto em rodovia, queries de monitoramento, criação de monitor, export CSV/JSON/ICS | ✓ | — |
| Boletim | Itens do dia por seção com fonte e evidência; **perfis vigiados** (handle normalizado, menções, monitor); consolida agenda, hashtags, convites e perfis; exporta Markdown/JSON/HTML no formato do boletim Op. Eleições 2026 | ✓ | — |
| **Convocações** | Detector de cartazes/postagens que **convocam para atos**: print, URL (imagem, post do Bluesky, `t.me/<canal>/<id>`, página com `og:image`) ou fontes públicas agendadas. Pipeline em CPU: pHash (dedup e propagação entre redes) → OpenCV (pré-processamento + **QR de grupo**) → OCR (rapidocr) → **léxico ponderado** de mobilização → queries dos monitores → CLIP opcional → **score 0–100 + severidade**. Ações: confirmar, descartar, boletim, agenda, e **"Buscar na internet"** (termos do cartaz → convites abertos de WhatsApp/Telegram, menções via SearXNG + deeplinks, monitor contínuo; "Refinar com IA" opcional) | ✓ | ✓ só fontes públicas, sem login |
| **Alertas** | Caixa de entrada persistida: convocações, convites, resultados do Radar e **vereditos do assistente de IA** (`tipo="ia"`), com severidade, marcar lido e atalho para o detalhe; contador no menu | — | — |
| **Assistente** (`/ia`) | Fila de tarefas do assistente de IA: status, saúde do gateway OpenClaw, custo do dia e por dia, aprovação/rejeição/reprocessamento de cada item, pesquisa sob demanda. Ver "Assistente de IA" abaixo | — | — |
| Convites | Queries do PDF (deeplinks) **e** consultas simples para o SearXNG; extração ampliada de links de grupo/canal (WhatsApp, Telegram) a partir de buscas, cartazes (QR/OCR), posts coletados e texto colado; **Testar** cada link (página pública: nome, nº de membros, ativo/revogado, foto como evidência); reverificação automática opcional; export CSV/JSON | ✓ | via SearXNG + verificação pública |
| Hashtags | CRUD, coleta em trends24 e Mastodon, variantes sem acento/caixa, rastreio periódico, gráfico SVG + série temporal | ✓ | ✓ |
| Imagens | Upload (vira evidência com SHA-256) → links para Google Lens, TinEye, Yandex, Lenso, Sensity | ✓ | — |
| Ferramentas | Hub do PDF mestre + **Checagem de fatos** (AFP Checamos, Comprova, Lupa, Aos Fatos, g1, Boatos.org, Estadão Verifica, TSE, Google Fact Check Explorer) + **Busca em redes** (X, TikTok, Instagram, YouTube, Facebook, Google Notícias), com URL pré-preenchida; na VPS, **Ferramentas OSINT do servidor** (12 ferramentas do Kali com lista de permissão, sem shell, alvo validado, auditoria; as sensíveis ficam desligadas por padrão) | ✓ | — |
| Evidências | Upload, galeria, verificação de hash, busca por SHA-256, manifesto JSONL, export ZIP (`manifest.json` + `SHA256SUMS`) | — | — |
| Tema | Cores, raio, fonte, presets; preferências de Radar, Convocações, Convites, **Telegram** (teste de envio), **Assistente de IA** (ligar, intervalo, itens por ciclo, teto diário em US$, modelos, política de Boletim/Agenda) e ferramentas sensíveis; persistido em `data/settings.json` | — | — |
| **Usuários** (só admin, VPS) | Cadastro de e-mails autorizados, papel (admin/analista), Telegram opcional, auditoria de acessos | — | — |

## Autenticação do painel (VPS)

Ativa só quando `O51NT_ADMIN_EMAIL` está no `.env`; sem ela (desenvolvimento, testes) nada muda e `/api/auth/estado`
responde `ativo:false`. Fluxo: o usuário informa o e-mail → recebe um **código de 6 dígitos de uso único** (10 min,
5 tentativas, 5 pedidos por 15 min; bloqueio de 15 min após 5 falhas por e-mail ou 20 por IP) → sessão em cookie
`HttpOnly`/`Secure`/`SameSite=Strict` (12 h, encerrada após 2 h sem uso). Mutações exigem o cabeçalho `X-Requested-With: O51NT`
(anti-CSRF). Respostas nunca revelam se um e-mail existe. Só administradores cadastram usuários; ninguém rebaixa ou remove
a si mesmo nem o último admin. Entrega do código: **SMTP** (Gmail com senha de app) → Telegram do usuário → journal do serviço.
O acesso por loopback sem `X-Forwarded-For` (OpenClaw, health check) não passa pelo login. Na VPS há ainda a senha básica
do Caddy como primeira camada e, opcionalmente, Cloudflare Zero Trust (`deploy/vps/CLOUDFLARE.md`).

## Assistente de IA (pipeline OpenClaw)

O O51NT orquestra; o OpenClaw (na VPS, usuário próprio, gateway em `127.0.0.1:18789`) só executa turnos de agent via o
endpoint compatível com OpenAI (`model: "openclaw/<agent>"`). Entrada: hits de monitores com `ia=True` e detecções de
Convocações acima do limiar, uma tarefa por URL normalizada. Cadeia por tarefa:

1. **sentinela** — triagem em JSON com modelo barato (`iaModeloTriagem`): veredito RELEVANTE / OBSERVAR / DESCARTAR, severidade, seção;
2. **extrator** — só quando é evento: data, hora, cidade/UF, local, rodovias, organizador, impacto em rodovia federal;
3. **pesquisador** — só RELEVANTE com severidade ≥ `iaPesquisarSeveridadeMin`: fontes lidas, verificação (confirmado / parcial / não confirmado / falso), confiança e lacunas; pode chamar as ferramentas OSINT do servidor e a API local;
4. **analista/redator** — cartão final (título, resumo, impacto, ação, fontes).

Saídas: alerta `tipo="ia"` sempre (DESCARTAR só marca o hit como lido); Telegram imediato para RELEVANTE; resumo periódico
dos OBSERVAR; Boletim e Agenda conforme `iaBoletim`/`iaAgenda` (`auto | aprovar | nunca`), com aprovação no painel ou pelo
Telegram. Guardrails: `iaMaxItensCiclo`, teto `iaCustoDiarioUsd` (custo estimado por tabela de preços), 2 tentativas por
etapa e 3 por tarefa, gateway fora do ar só adia a fila. O conteúdo coletado entra no prompt dentro de um bloco `<conteudo>`
tratado como dado, nunca como instrução. Código em `backend/app/services/ia/`; agents definidos em `deploy/vps/05_openclaw.sh`;
avaliação dos quickstarts da pasta `agents/` em `agents/README-O51NT.md`.

## Implantação na VPS

Scripts idempotentes em `deploy/vps/` (ordem: `01_endurecer.sh`, `02_dependencias.sh`, `03_o51nt.sh`, `04_caddy.sh`,
`05_openclaw.sh`, `segredos.sh`, `06_ssh.sh`, `07_cloudflare.sh`, `08_ferramentas.sh`). Layout em `/opt/o51nt/{app,venv,data,backups,.env}`;
serviço `o51nt.service` (`Type=notify`, `WatchdogSec=90`, `sd_notify` em `app/sdnotify.py`); backup diário às 03:30 com
7 cópias; Caddy com Let's Encrypt; UFW só 22/80/443; fail2ban no SSH e no Caddy. Atualizar após um push:

```bash
ssh o51nt@<vps>
cd /opt/o51nt/app && git pull && bash deploy/vps/03_o51nt.sh
```

**Deploy automático**: o job `deploy` do CI roda esse mesmo `git pull` + `03_o51nt.sh` por SSH a cada merge na `main` com
a suíte verde. Para ativar: na VM, `sudo bash deploy/vps/chave_deploy.sh` (gera uma chave restrita a esse comando) e grave
os segredos `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_KNOWN_HOSTS` em Settings → Secrets → Actions. Sem eles, o job é pulado.

Segredos (Telegram, SMTP, Anthropic/OpenAI, token do gateway) só na VM, gravados por `segredos.sh`. Relatório completo,
armadilhas e operação em `deploy/vps/RELATORIO_IMPLANTACAO.md`; contexto operacional e progresso em `CLAUDE.md`.

## Arquitetura

```
frontend/ (Vite + React + TS + Tailwind + componentes estilo shadcn + Zustand + React Query)
   └─ npm run build → backend/static/  (servido pelo FastAPI)
backend/app/
   main.py            FastAPI + lifespan (init DB, seed, scheduler, admin, watchdog) + fallback de SPA
   config.py          pydantic-settings (prefixo O51NT_; TELEGRAM_*/SMTP_* aceitos sem prefixo)
   db.py              SQLModel + SQLite (WAL)
   middleware_auth.py sessão por cookie, isenção de loopback, anti-CSRF
   sdnotify.py        READY/WATCHDOG/STOPPING para o systemd (no-op fora dele)
   models/            27 tabelas SQLModel (monitor, radar, convocacao, ia, auth, evidence, boletim…) + settings (JSON)
   routers/           agenda, alertas, auth, boletim, convocacoes, evidence, ferramentas, hashtags, ia, images,
                      invites, monitors, perfis, query_builder, radar, scraping, settings, tools
   services/
     operators.py, query_compose.py      tokenizador/validador O(n), montagem de blocos, templates, deeplinks
     scraper.py                          páginas públicas: robots.txt, 1 req/3 s por domínio, backoff 1h→6h→24h
     searxng_client.py                   busca na instância local do SearXNG
     scheduler.py                        APScheduler: monitores, radar, convocações, descarga, convites, IA, resumo
     radar.py                            parser RSS/Atom e páginas, matcher da sintaxe do Query Builder, ciclo
     convocacoes/                        imagem, ocr, lexico_mobilizacao, clip, score, coleta, busca, bluesky, telegram
     ia/                                 cliente_openclaw, esquemas, prompts, pipeline
     auth.py, alerts.py (jsonl/webhook/telegram), ferramentas.py, agenda.py, boletim.py,
     evidence_store.py, hashtag_tracker.py, retention.py, locations.py
backend/tests/        unit/ e integration/ (pytest, httpx TestClient, FakeOpenClaw)
shared/               google_operator_cases.json (paridade do validador back/front)
deploy/vps/           scripts de implantação, Caddyfile, units systemd, relatório
deploy/searxng/       template de settings.yml do SearXNG
data/                 o51nt.db, evidence/, alerts/, logs/, settings.json, models/ (OCR), ferramentas_home/
```

## Coleta: scraper ético e SearXNG

**Páginas públicas** (feeds, páginas do Radar, trends24, prévias de convites) passam pelo scraper ético:
- Só páginas públicas, sem login, sem burlar paywall ou captcha.
- `robots.txt` checado antes de cada URL (se o robots.txt der erro 5xx ou de rede, a coleta é **negada**); exceção
  explícita por fonte só para feeds pessoais (ex.: Google Alertas).
- 1 requisição a cada 3 s por domínio, fila global e concorrência 2.
- User-Agent: `O51NT-Workbench/1.0 (+local; contato: usuario local)`.
- 403/429 → domínio em **backoff persistente** (tabela `domain_backoff`): 1 h, depois 6 h, depois 24 h. Consulte em `GET /api/scraper/status`.
- Todo resultado guarda URL de origem, horário e SHA-256 do conteúdo.

**Buscas em buscadores** (subaba "Scraping ético" do Query Builder, Convites e menções em Convocações) passam pela
**instância local do SearXNG**.

> **Transparência:** o SearXNG é uma metabusca. Ele consulta DuckDuckGo, Bing e Startpage como um cliente de busca
> e **não aplica o robots.txt** desses buscadores. O app mitiga isso com uma consulta por clique do operador (ou por
> monitor), baixo volume, instância privada em `127.0.0.1` e nenhum crawling de páginas de resultado. Avalie se esse uso
> atende à sua política. Se não atender, rode com `--no-searxng` e use só os deeplinks.

## Guia em PDF

`Guia O51NT — Op. Eleições 2026.pdf` (na raiz) é o passo a passo, com capturas de tela reais, de como usar cada
recurso para produzir o boletim "INFORMAÇÕES RELEVANTES". Fonte em `deploy/guia/` (HTML + imagens); regenere com
`cd frontend && npm run guia`.

## Radar — como os monitores pesquisam de verdade

Buscadores bloqueiam coleta automática (CAPTCHA/robots.txt), então o Radar usa o que foi feito para máquina ler:
**feeds**, e, para sites sem feed, **páginas HTML** com detecção de mudança por hash. Cerca de 50 fontes validadas ao
vivo vêm cadastradas: grande imprensa (g1, Folha, UOL, Metrópoles, Poder360, CNN Brasil, Estadão), Agência Brasil e
TSE, agências de checagem (Lupa, Aos Fatos), imprensa independente (Agência Pública, Intercept, Nexo, CartaCapital,
Fórum, Brasil 247, GGN, DCM, Mídia Ninja, Ponte, piauí, JOTA), BBC e RFI em português, regionais de 15 UFs, hashtags no
Mastodon e um **feed de busca do Google Notícias** (manifestação/protesto/bloqueio/carreata, com robots.txt ignorado
por decisão do dono). Outras entram em **Fontes do radar** (teste a URL antes de gravar: `POST /api/radar/fontes/testar`);
candidatas e validação em lote: `backend/scripts/validar_fontes.py` (workflow "Fontes do Radar" no GitHub Actions).
A cada ciclo (padrão 10 min, ajustável em **Tema**), o Radar:

1. coleta cada fonte ativa pelo scraper ético (robots.txt, 1 req/3 s por domínio, backoff em 403/429);
2. casa os itens novos com a query de **todos** os monitores ativos de uma vez (modo `termos`, recomendado para
   imprensa, ignora `site:`; modo `estrito` exige o domínio);
3. grava os hits (único por monitor + URL), dispara os alertas do monitor, enfileira para o assistente de IA quando o
   monitor tem `ia=True`, e mostra tudo em **Monitores → Resultados**.

Para ter a **busca do Google** no Radar: crie um alerta em google.com/alerts com a sua query, escolha *Entregar em: Feed
RSS* e cadastre a URL do feed em **Fontes do radar** marcando "ignorar robots.txt" (é um feed que o próprio Google entrega
a você). Hashtags em qualquer instância Mastodon: `https://<instancia>/tags/<hashtag>.rss`.

## Convocações: como funciona e o que esperar

Caso de uso: um cartaz "REVOLTA NAS RUAS — DIA 11 DE OUTUBRO EM BELO HORIZONTE — ATO NÃO PACÍFICO" circulando como **imagem**.

1. **Entrada**: print solto/colado na aba *Analisar*; URL (imagem direta, post do Bluesky via API pública, `t.me/<canal>/<id>`,
   página com `og:image`; para o X só o texto via oEmbed público); ou coletores agendados (fontes em *Fontes*).
2. **Análise** (`backend/app/services/convocacoes/`): `imagem.py` (Pillow, imagehash, OpenCV: normaliza, pHash/dHash,
   pré-processamento, QR), `ocr.py` (rapidocr/ONNX, modelo `latin`; baixado uma vez para `data/models/`),
   `lexico_mobilizacao.py` (termos ponderados por categoria, extração de data/hora/local, "convocando × noticiando"),
   `clip.py` (opcional), `score.py` (pesos redistribuídos quando um componente não existe; piso "alta" para não pacífico
   com léxico forte).
3. **Saída**: `Deteccao` com evidência (SHA-256 + manifesto), alerta na inbox e JSONL/webhook/Telegram quando
   `score ≥ limiar`; QR/links de grupo vão para *Convites*; "Confirmar" cria a referência usada nas próximas análises;
   detecções acima do limiar também entram na fila do assistente de IA.
4. **Do cartaz para a busca** (`busca.py`): termos extraídos do OCR (frases entre aspas, locais, siglas, hashtags, menções,
   datas) → scan de convites abertos, menções via SearXNG + deeplinks, monitor contínuo (`ia=True`).

Expectativas honestas:

- **X, Instagram e Facebook não têm API pública nem página aberta sem login.** O app não faz login nem burla bloqueios.
  A cobertura automática dessas redes vem só de imagens já indexadas (fonte `searxng_imagens`), que é baixa e irregular.
  **O caminho confiável para essas redes é o print (aba Analisar)** e os deeplinks de busca.
- Bluesky (API pública), canais públicos do Telegram (`t.me/s/<canal>`) e Mastodon (RSS com mídia) são coletados de verdade.
- Tudo roda em **CPU**. O perfil **leve** (padrão) resolve cartazes com texto. O perfil **completo** (CLIP, `./run.sh --ml`)
  usa ~1 GB de RAM quando carregado e é descarregado após ociosidade.
- `opencv-python` (não headless) é obrigatório porque o rapidocr depende dele; não instale `opencv-python-headless` junto.
- Testar um convite é um GET da página pública: o app **nunca entra no grupo**, não lista membros e respeita `robots.txt`
  por padrão, com toggle explícito por link.

## Limitações aceitas (por design)

O O51NT Workbench **entrega ao analista a query certa e o deeplink certo, e deixa a decisão com ele**. Ele não tenta
ser um crawler furtivo. Os itens abaixo são fronteiras deliberadas do produto, não bugs pendentes:

- **Não burla CAPTCHA nem rate-limit.** No teste real de 05/10/2026, todos os buscadores (DuckDuckGo, Qwant: CAPTCHA;
  Brave: HTTP 429; Startpage: desativado upstream) recusaram acesso automatizado. A coleta parou aí.
- **SearXNG** não aplica o robots.txt dos buscadores e **não respeita operadores do Google** (`site:`, `inurl:`,
  `before:`, aspas, `OR`…). Por isso o Query Builder desabilita "Buscar via SearXNG" quando a query contém qualquer um
  desses operadores (`frontend/src/lib/queryOperators.ts`, espelho de `operadores_google` no backend, casos compartilhados
  em `shared/google_operator_cases.json`). Em **Convites** vão ao SearXNG só **consultas simples** geradas pelo backend.
- **OneMillionTweetMap: encerrado.** O HTML público não expõe hashtags. A fonte está desabilitada na interface.
- **Hashtags:** a comparação ignora acentos e caixa (`#Eleicoes2026` ≡ `#Eleições2026`). As formas originais ficam
  guardadas e aparecem como "variantes".
- **Google Notícias:** o `robots.txt` não libera `/rss/`, então não há coleta automática; a seção "Notícias relevantes"
  do Boletim é assistida (deeplink + registro manual com evidência).
- **Operadores do X/TweetDeck** só funcionam no X. O Query Builder os valida e avisa.
- **Contratos:** endpoints e campos existentes não mudam por padrão; toda evolução é aditiva (ex.: `/api/alertas/contagem`
  não ganhou chave nova com a IA). `robots.txt` e o ritmo de 1 req/3 s são o padrão, mas o analista pode desligar o
  robots.txt fonte a fonte (feeds de busca, YouTube). Nunca: CAPTCHA, login automatizado, rotação de UA/proxies.
- **Verificação (OOVS 0.1.0):** cada item RELEVANTE recebe uma etiqueta de confiança derivada mecanicamente de origens
  distintas (republicações contam uma vez), da verificação do pesquisador e do aterramento das afirmações do cartão.

## Avisos legais

- **LGPD (Lei 13.709/2018):** use apenas para finalidades legítimas, como segurança pública, investigação autorizada ou
  exercício regular de direitos (art. 7º, IX; art. 11). Guarde só o necessário. O app não semeia dados pessoais; as
  ferramentas que tocam dados pessoais (holehe, h8mail, phoneinfoga) ficam desligadas até serem habilitadas em Tema.
- **Termos de uso:** cada site externo tem os próprios termos. O app não faz login, não usa APIs privadas e não contorna
  bloqueios. A responsabilidade pelo uso é do operador.
- Convites de grupos e hashtags podem conter dados pessoais de terceiros: trate-os com sigilo.

## Limitações

- Busca reversa de imagem local exige upload manual no provedor; a busca direta só funciona se você informar a URL pública da imagem.
- **Teste real em 05/10/2026 (Kali, Docker rootless): a busca via SearXNG retornou 0 convites úteis.** Na prática,
  convites e hashtags em redes sociais funcionam pelos **deeplinks**.
- Docker rootless: o container passa `data/searxng/` para um subuid, e seu usuário perde a permissão de editar esses
  arquivos. Para editar: `docker exec -u searxng o51nt-searxng vi /etc/searxng/settings.yml` e depois `docker restart o51nt-searxng`.
- Sem Docker utilizável, o SearXNG não sobe e as subabas de busca mostram "SearXNG indisponível".
- A imagem do SearXNG está fixada em `searxng/searxng:2026.10.4-d48c4b555` (`docker-compose.yml` e `run.sh`).
- **Dívida técnica (B3):** os handlers async acessam o SQLite de forma síncrona, o que bloqueia o event loop por alguns
  milissegundos. Aceitável para poucos usuários; migre para `aiosqlite` ou handlers `def` se houver 3 ou mais usuários
  simultâneos ou latência acima de 50 ms nos endpoints.
- Os operadores `before:`/`after:` só funcionam de forma confiável no Google; o app avisa a incompatibilidade em cada botão.
- A base de localidades é um recorte embutido (27 UFs, 27 capitais, 30 rodovias federais).
- Localmente não há autenticação: o servidor escuta só em `127.0.0.1`. Na VPS o login é obrigatório.
