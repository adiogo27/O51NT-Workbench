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
- `agents/` (quickstarts de Managed Agents da Claude Platform): `deep-researcher` e `structured-extractor` foram portados
  para os agents `pesquisador` e `extrator` do OpenClaw na VPS; `field-monitor` não serve (blogs de IA → Notion).
  Ver `agents/README-O51NT.md`. Não há integração com a nuvem de Managed Agents.

---

## Autenticação do painel (desde 2026-10-09)

- Ativa só com `O51NT_ADMIN_EMAIL`; sem ela (dev/testes) nada muda e `/api/auth/estado` devolve `ativo:false`.
- Fluxo: `POST /api/auth/solicitar {email}` (resposta sempre genérica) → código 6 dígitos, 10 min, 5 tentativas, 5 pedidos/15 min,
  bloqueio 15 min após 5 falhas (e-mail) ou 20 (IP) → `POST /api/auth/verificar` → cookie `o51nt_sessao` (HttpOnly, Secure,
  SameSite=Strict; 12 h, inatividade 2 h). Mutações exigem `X-Requested-With: O51NT` (já no `api.ts`).
- Admin: `/api/auth/usuarios` (GET/POST/PATCH/DELETE), `/api/auth/eventos`; regras: não rebaixar/remover a si nem o último admin.
- Testes com auth: fixture `cliente_auth` em `backend/tests/integration/test_auth_router.py` (captura os códigos em vez de enviar e-mail).
- Segredos de SMTP (`SMTP_HOST/PORT/USER/PASSWORD/FROM`) só no `.env` da VPS via `segredos.sh`.

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
| 3 | O51NT em `/opt/o51nt`: clone, venv, build, systemd `o51nt.service` com `WatchdogSec` + `sd_notify`, backup diário de `data/` | ✅ 2026-10-09 | `deploy/vps/03_o51nt.sh` (reexecutar = atualizar). Layout: `/opt/o51nt/{app,venv,data,backups,.env,backup.sh}`; `WatchdogSec=90`; timer 03:30; SearXNG via compose em `127.0.0.1:8080` |
| 4 | Caddy: HTTPS automático + basic auth → proxy `127.0.0.1:8051` | ✅ 2026-10-09 | `deploy/vps/04_caddy.sh` + `Caddyfile`. Cert Let's Encrypt até 2027-01-07; 401 sem senha, 403 por IP. Credenciais em `/root/o51nt-credenciais.txt` (600) na VM. Armadilha: `caddy validate` como root cria o log com dono root → `chown` no script |
| 5 | Canal de alerta **Telegram** (monitores/Radar/Convocações) lendo `.env`; testes | ✅ código 2026-10-09 (teste ao vivo pendente da chave no `.env`) | `services/alerts.py` (`telegram`, HTML, JSONL preservado), `GET/POST /api/settings/telegram[/teste]`, card em Tema; `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` aceitos sem prefixo; 422 se canal telegram sem token. `app/sdnotify.py` (READY/WATCHDOG/STOPPING) |
| 6 | **OpenClaw** em usuário próprio (`openclaw`), daemon systemd, canal Telegram, agents O51NT | ✅ 2026-10-09 (LLM/Telegram ativam ao gravar as chaves) | `deploy/vps/05_openclaw.sh`. OpenClaw 2026.9.9, gateway `127.0.0.1:18789` (token), serviço de usuário `openclaw-gateway` (linger), agents `analista`/`sentinela` com skill `o51nt-api`, `tools.deny` exec/browser, Telegram allowlist 371824016, `tools.sessions.visibility=agent`, `agentToAgent` off. Armadilhas: rodar `openclaw` com `cd ~openclaw` (EACCES na sondagem do Node); o drop-in systemd só pode existir DEPOIS de `gateway install --force` |
| 7 | Fechamento SSH: `PermitRootLogin no`, `PasswordAuthentication no` | ✅ 2026-10-09 | `deploy/vps/06_ssh.sh` → `/etc/ssh/sshd_config.d/90-o51nt.conf` (`AllowUsers o51nt`). Validado: `o51nt` por chave + sudo OK; root e senha recusados |
| 8 | Verificação ponta a ponta + relatório (`deploy/vps/RELATORIO_IMPLANTACAO.md`) | ✅ 2026-10-09 | Todos os serviços ativos, watchdog vivo, HTTPS 401/200/403, ciclo do Radar OK, 0 erros no journal. **Pendência única:** chaves (Anthropic/OpenAI/Telegram) ainda não gravadas → `sudo bash /opt/o51nt/app/deploy/vps/segredos.sh` na VM (interativo). Até lá Telegram e LLM do OpenClaw ficam inativos |
| 9 | **Login do painel**: e-mail autorizado + código de uso único; usuários só por admin; auditoria; fail2ban no Caddy; preparação Cloudflare | ✅ 2026-10-09 (SMTP pendente: até lá o código cai no journal) | Admin `adiogo27@gmail.com` (`O51NT_ADMIN_EMAIL` no `.env`). Código: `backend/app/{services/auth.py,middleware_auth.py,routers/auth.py,models/auth.py}`, `frontend/src/{lib/auth.tsx,pages/Login,pages/Usuarios}`. Entrega do código: SMTP → Telegram do usuário → journal. Isenção: acesso loopback **sem** `X-Forwarded-For` (OpenClaw/health). Anti-CSRF: cookie `SameSite=Strict` + `X-Requested-With: O51NT`. Caddy: basic auth mantida como 1ª camada, `confiaveis.caddy`, `X-Real-IP`, CSP em modo relatório; jail `o51nt-caddy`. Cloudflare: `07_cloudflare.sh` (faixas + `--fechar`) e `CLOUDFLARE.md` (passos no painel do dono: DNS proxied, WAF, rate limit, Zero Trust Access com PIN por e-mail) |

Estado dos segredos (2026-10-09 19h UTC): Telegram OK (bot responde; exige `/start` do usuário antes), SMTP Gmail OK (código de login chega por e-mail), OpenAI OK (fallback do OpenClaw = `openai/gpt-5.5`), Anthropic OK desde 19h40 UTC (chave trocada pelo dono; agents respondem em `claude-sonnet-5-5`, fallback `openai/gpt-5.5`). OCR (rapidocr) instalado na VPS e validado com cartaz sintético. Armadilhas vistas: senha de app digitada no campo SMTP_HOST; OpenClaw reescreve `openclaw.json` em JSON (usar `openclaw config set`, não `sed`).

Arquivos de implantação versionados em `deploy/vps/` (scripts idempotentes; segredos só na VM).

### Itens do PLANO_MESTRE_OSINT recusados (com motivo)
Rotação de UA / `fake-useragent` / proxies residenciais (burla de bloqueio — contraria a regra ética);
watchdog como agente LLM com root "sem confirmação" (substituído pelo watchdog do systemd);
`bypassPermissions` no host do desenvolvedor (desnecessário e desaconselhado pela própria doc).
