# CLAUDE.md — contexto operacional do O51NT Workbench

Este arquivo é a memória de trabalho do projeto. **Atualize a seção "Implantação na VPS — progresso"
a cada etapa concluída ou alterada com sucesso.** Linguagem: português do Brasil.

## O que é o projeto
Workbench OSINT **local, single-user, sem login**, para monitoramento eleitoral (boletim "Op. Eleições 2026")
baseado no documento mestre `O51NT.pdf`. Backend FastAPI + SQLModel/SQLite (WAL) em `backend/app`,
frontend Vite + React + TS + Tailwind em `frontend/` (build servido em `backend/static/`).
Repositório: `git@github.com:adiogo27/O51NT-Workbench.git` (branch `main`).

### Módulos (routers em `backend/app/routers/`, páginas em `frontend/src/pages/`)
Query Builder (operadores Google + X/TweetDeck, validador com paridade back/front em
`shared/google_operator_cases.json`) · Monitores + **Radar** (feeds RSS/Atom públicos casados com a query de
todos os monitores ativos; hits; alertas) · Agenda · Boletim (itens por seção, perfis vigiados, export MD/JSON/HTML)
· Convites (WhatsApp/Telegram) · Hashtags (trends24 + Mastodon, variantes sem acento) · Imagens (busca reversa)
· Ferramentas (hub) · Evidências (SHA-256, manifesto, ZIP) · **Convocações** (detector de cartazes de ato:
OCR + léxico + QR + pHash, CLIP opcional/PyTorch opt-in) · Alertas (inbox) · Tema/Settings (`data/settings.json`).

### Regras inegociáveis
- **Scraping ético**: só dados públicos, `robots.txt` sempre (exceção explícita só para feeds pessoais, ex. Google
  Alertas), 1 req/3 s por domínio, UA `O51NT-Workbench/1.0 (+local; contato: usuario local)`, backoff 1h→6h→24h em
  403/429. **Nunca** rotação de User-Agent, proxies, burla de CAPTCHA ou login automatizado.
- **Contratos congelados**: endpoints/campos existentes não mudam; tudo é aditivo. Se um teste antigo quebrar por
  mudança de contrato, reverter a mudança, não o teste.
- **Testes sempre verdes** antes de qualquer commit/implantação: `./test.sh` (pytest paralelo + sequencial, Vitest,
  tsc, Playwright). Nunca remover testes para passar.
- **LGPD**: guardar o mínimo; não semear dados pessoais (CPF, telefone, nomes de administradores de grupos).
- Sem chaves pagas no core; integrações com IA/API ficam **opt-in** e as chaves só em `.env` (nunca no repo).

### Comandos
`./iniciar.sh` (abre no navegador) · `./run.sh [--no-browser|--no-searxng|--reset-db]` · `./stop.sh` ·
`./test.sh [--quick]` · `cd frontend && npm run guia` (regenera o PDF do guia).
Ambiente: Python 3.12+ (`.venv`), Node 22+, Docker opcional (SearXNG em `127.0.0.1:8080`).

### Decisões já tomadas (não reabrir)
- SearXNG é opcional e **não respeita operadores do Google/X** → o botão fica desabilitado quando a query os usa.
- Hashtags casam sem acento/caixa (diverge do X de propósito; formas originais preservadas e exibidas).
- OneMillionTweetMap encerrado (HTML público sem hashtags). Google Notícias sem RSS (robots) → assistido.
- Scheduler: jobs em memória reconstruídos da tabela `monitor`; job global `radar-ciclo`.

---

## Implantação na VPS — plano e progresso

**Alvo**: VM InterServer `vps3700295` → **`162.35.16.238`** (o `162.35.16.238` é a VM; `216.158.228.164` é
`cdns1.interserver.net`, DNS da InterServer — não usar). Ubuntu 24.04.5, 2 vCPU, 7,8 GB RAM, 156 GB.
Domínio: `o51nt.sentinela.api.br` → A `162.35.16.238` (propagado em 2026-10-09).
Acesso: chave `~/.ssh/id_ed25519_github` (root hoje; passará a `o51nt` com sudo). Telegram: bot
`@alertao51ntbot`, chat ID `371824016`; token vai em `/opt/o51nt/.env` (`TELEGRAM_BOT_TOKEN`), nunca no repo.

Decisões do dono (2026-10-09): seguir as recomendações abaixo; **pode desligar root/senha no SSH ao final**;
IA = **OpenClaw** na VM (openclaw.ai, OpenClaw Foundation) com agents definidos, chaves de API chegam depois.

| # | Etapa | Status | Observações |
|---|---|---|---|
| 0 | Recon da VM e DNS | ✅ 2026-10-09 | VM limpa (só sshd), 40 updates pendentes, UFW/fail2ban ausentes, root+senha liberados |
| 1 | Endurecimento: updates, timezone, usuário `o51nt`+sudo+chave, UFW 22/80/443, fail2ban, unattended-upgrades | ✅ 2026-10-09 | `deploy/vps/01_endurecer.sh`; `/opt/o51nt` criado (dono `o51nt`, `.env` 600); reboot após kernel |
| 2 | Dependências: Node 24, Docker (SearXNG), Caddy | ✅ 2026-10-09 | `deploy/vps/02_dependencias.sh`. Repo apt do Caddy (Cloudsmith) deu 402 → binário oficial do GitHub Releases (v2.11.7) + unit systemd oficial; Docker com `"ip": "127.0.0.1"` para não furar o UFW |
| 3 | O51NT em `/opt/o51nt`: clone, venv, build, systemd `o51nt.service` com `WatchdogSec` + `sd_notify`, backup diário de `data/` | ⬜ | app continua em `127.0.0.1:8051` |
| 4 | Caddy: HTTPS automático + basic auth → proxy `127.0.0.1:8051` | ⬜ | credenciais entregues ao dono fora do repo |
| 5 | Canal de alerta **Telegram** (monitores/Radar/Convocações) lendo `.env`; testes | ✅ código 2026-10-09 (teste ao vivo pendente da chave no `.env`) | `services/alerts.py` (`telegram`, HTML, JSONL preservado), `GET/POST /api/settings/telegram[/teste]`, card em Tema; `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` aceitos sem prefixo; 422 se canal telegram sem token. `app/sdnotify.py` (READY/WATCHDOG/STOPPING) |
| 6 | **OpenClaw** em usuário próprio (`openclaw`), daemon systemd, canal Telegram, agents O51NT | ⬜ | chaves de API serão enviadas pelo dono depois |
| 7 | Fechamento SSH: `PermitRootLogin no`, `PasswordAuthentication no` | ⬜ | só após etapa 1 validada |
| 8 | Verificação ponta a ponta + relatório (`deploy/vps/RELATORIO_IMPLANTACAO.md`) | ⬜ | health via HTTPS, ciclo do Radar, alerta no Telegram, `./test.sh` verde |

Arquivos de implantação versionados em `deploy/vps/` (scripts idempotentes; segredos só na VM).

### Itens do PLANO_MESTRE_OSINT recusados (com motivo)
Rotação de UA / `fake-useragent` / proxies residenciais (burla de bloqueio — contraria a regra ética);
watchdog como agente LLM com root "sem confirmação" (substituído pelo watchdog do systemd);
`bypassPermissions` no host do desenvolvedor (desnecessário e desaconselhado pela própria doc).
