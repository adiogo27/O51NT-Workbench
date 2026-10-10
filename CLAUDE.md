# CLAUDE.md — contexto operacional do O51NT Workbench

Este arquivo é a memória de trabalho do projeto. **Atualize a seção "Implantação na VPS — progresso"
a cada etapa concluída ou alterada com sucesso.** Linguagem: português do Brasil.

## O que é o projeto
Workbench OSINT para monitoramento eleitoral — roda **local sem login** (dev) e **na VPS com login por e-mail + código e múltiplos usuários** (ver "Autenticação do painel"), (boletim "Op. Eleições 2026")
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

### Regras (revisadas pelo dono em 2026-10-10)
- **Coleta**: só dados públicos, sem login. `robots.txt` e o ritmo de 1 req/3 s por domínio continuam sendo o padrão,
  mas **deixaram de ser obrigatórios**: o analista pode marcar "ignorar robots.txt" fonte a fonte (feeds de busca do
  Google Notícias/Bing, canais do YouTube, feeds pessoais) e o ritmo pode ser ajustado quando a finalidade pedir. O
  backoff 1h→6h→24h em 403/429 fica (protege o Radar de bloqueios). UA `O51NT-Workbench/1.0 (+local; contato: usuario local)`.
  **Nunca, em nenhum caso**: burla de CAPTCHA, login automatizado em contas de terceiros, rotação de User-Agent ou
  proxies para escapar de bloqueio.
- **Contratos**: endpoints e campos existentes não mudam por padrão; evolução aditiva. Uma mudança de contrato só com
  decisão explícita do dono, testes atualizados no mesmo commit e nota no CLAUDE.md. Testes que codificam dados (preços,
  contagem de fontes semeadas, catálogos) podem ser atualizados junto com os dados.
- **Testes sempre verdes** antes de qualquer commit/implantação: `./test.sh` (pytest paralelo + sequencial, Vitest,
  tsc, Playwright) e o CI (`.github/workflows/ci.yml`). Nunca remover ou pular um teste para passar. Vitest (funções
  puras, sem navegador) e Playwright (fluxos inteiros no navegador com backend isolado) são complementares; um não
  substitui o outro.
- **LGPD**: guardar o mínimo; não semear dados pessoais (CPF, telefone, nomes de administradores de grupos).
- Sem chaves pagas no core; integrações com IA/API ficam **opt-in** e as chaves só em `.env` (nunca no repo).

### Comandos
`./iniciar.sh` (abre no navegador) · `./run.sh [--no-browser|--no-searxng|--reset-db]` · `./stop.sh` ·
`./test.sh [--quick]` · `cd frontend && npm run guia` (regenera o PDF do guia).
Ambiente: Python 3.12+ (`.venv`), Node 22+, Docker opcional (SearXNG em `127.0.0.1:8080`).

### Decisões já tomadas (não reabrir)
- **Teto diário do assistente = US$ 1** (padrão `iaCustoDiarioUsd=1.0`; na VPS o valor vale é o de `data/settings.json`,
  ajustado em Tema). Tabela de preços em `cliente_openclaw.PRECOS_ESTIMADOS` (lista Anthropic 2026-10: Haiku 5.5
  0,10/0,50; Sonnet 5.5 2/10; Opus 5.5 4/20 por 1M tokens).
- **Modelos por etapa**: triagem e aterramento no Haiku 5.5 (`iaModeloTriagem`); extração e cartão no Haiku 5.5
  (`iaModeloLeve`, agents `extrator`/`redator` com `MODELO_LEVE` em `05_openclaw.sh`); pesquisador no Sonnet 5.5
  (único com ferramentas). Trocar o pesquisador para Haiku não foi feito: é a etapa com web_fetch/web_search e síntese.
- **Camada OOVS** (`services/ia/verificacao.py`, OWASP OSINT Verification Standard 0.1.0): origens distintas por domínio
  registrável + similaridade de trecho (Jaccard de shingles ≥ 0,85), aterramento das afirmações do cartão (agent
  `sentinela`, só RELEVANTE com pesquisa, `iaAterramento`), etiqueta de confiança determinística
  (alta/média/baixa/não verificada/refutada) em `ia_tarefa.verificacao_json`, no cartão do Telegram, no alerta e em `/ia`.
  Não implementar enxame de agentes, votação entre modelos nem grafo de conhecimento (custo × ganho).
- **Radar**: termo solto com `*` é curinga de prefixo/infixo (`manifesta*` casa manifestação/manifestantes); em frase
  entre aspas `*` continua sendo palavra inteira (semântica Google). Fontes novas só entram em `FONTES_PADRAO` depois de
  passarem em `backend/scripts/validar_fontes.py` (workflow manual `fontes.yml`, que tem internet; o contêiner de dev não tem).
- **Deploy automático**: job `deploy` do CI após merge na `main` com a suíte verde, por SSH com chave restrita a
  `git pull && 03_o51nt.sh` (`deploy/vps/chave_deploy.sh` gera a chave e imprime os segredos `VPS_*`). Sem os segredos o job é pulado.
- **Login**: um único fluxo (e-mail cadastrado + código). A tela tem o seletor Usuário/Administrador; "Administrador"
  só confere o papel ao entrar. Sem autocadastro, sem senha, papéis só admin/analista.
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

## Assistente de IA (pipeline OpenClaw) — desde 2026-10-09

- O51NT orquestra; o OpenClaw só executa turnos de agent via `POST http://127.0.0.1:18789/v1/chat/completions`
  (`model: "openclaw/<agent>"`, token do gateway em `OPENCLAW_GATEWAY_TOKEN`, sessão nova por chamada).
  Código: `backend/app/services/ia/{cliente_openclaw,esquemas,prompts,pipeline}.py`, `models/ia.py`, `routers/ia.py`.
- **Entrada**: só `MonitorHit` (casamento determinístico em `radar.casar_itens`, monitores com `ia=True`) e `Deteccao` ≥ limiar.
  Uma tarefa por URL normalizada (`pipeline.normalizar_url`). Fila: `ia_tarefa` (status pendente → em_processo → concluida|erro).
- **Cadeia**: sentinela (triagem JSON, modelo barato `iaModeloTriagem`) → extrator (só `eh_evento`) → pesquisador (só RELEVANTE
  ≥ `iaPesquisarSeveridadeMin`) → analista (cartão). Prompts com marcador `### O51NT-PIPELINE` e bloco `<conteudo>` tratado como dado.
- **Saídas**: Alerta `tipo="ia"` sempre (DESCARTAR não gera alerta; marca o hit lido); Telegram imediato para RELEVANTE; resumo
  periódico dos OBSERVAR (`iaResumoHoras`); Boletim/Agenda conforme `iaBoletim`/`iaAgenda` (`auto|aprovar|nunca`) — aprovação
  no painel (`/ia`) ou pelo Telegram (analista chama `GET /api/ia/tarefas/{id}/acao?acao=aprovar`, aceito só de loopback
  sem `X-Forwarded-For`, porque o `web_fetch` do OpenClaw só faz GET).
- **Guardrails**: `iaMaxItensCiclo`, teto `iaCustoDiarioUsd` (custo estimado por tabela em `cliente_openclaw.PRECOS_ESTIMADOS`),
  2 tentativas por etapa + 3 por tarefa, gateway fora do ar só adia. `/api/alertas/contagem` NÃO ganhou chave (contrato).
- **Páginas HTML** no Radar: `Fonte.tipo="pagina"` + `intervalo_min` (`radar.parse_pagina/descobrir_feed/hash_conteudo/fonte_devida`).
- **Ferramentas Kali** (`services/ferramentas.py`, `routers/ferramentas.py`, `deploy/vps/08_ferramentas.sh`): lista de permissão,
  `create_subprocess_exec` sem shell, alvo validado por regex, 64 KB, auditoria em `ferramenta_execucao`; sensíveis (holehe, h8mail,
  phoneinfoga) exigem `ferramentasSensiveisAtivas`. Intrusivas (nmap etc.) não existem. GET local `/api/ferramentas/executar`
  para o pesquisador (mesma regra de loopback).
- OpenClaw (`05_openclaw.sh`): `gateway.http.endpoints.chatCompletions.enabled`, heartbeat `every "0m"`,
  `tools.web.fetch.ssrfPolicy.allowedHostnames=[127.0.0.1]` (sem isso o web_fetch bloqueia a API local), plugin SearXNG
  (`SEARXNG_BASE_URL`), `model.fallbacks=[openai/gpt-5.5]`. Token do gateway → `/opt/o51nt/.env`. O gateway reescreve o
  `openclaw.json` em JSON: o script lê o token em ambos os formatos e regenera o arquivo inteiro (não usar `sed`).
- Testes: `FakeOpenClaw` em `tests/conftest.py` (respostas por agent), `tests/integration/test_ia_router.py`, `tests/unit/test_ia_unidades.py`.
- **Do cartaz para a busca** (`services/convocacoes/busca.py`, rotas `/api/convocacoes/{id}/busca[/ia|/convites|/mencoes]` e
  `/{id}/monitor`): termos extraídos do OCR (frases entre aspas, locais "na Praça X", siglas, hashtags, menções, datas) →
  scan de convites abertos (reusa `routers.invites.executar_scan`), menções via SearXNG + deeplinks, monitor contínuo
  (`ia=True`, canal `nenhum`). IA (`extrator`, prompt `termos_busca`) só enriquece quando o analista clica "Refinar com IA".
  Frontend: `pages/Convocacoes/Busca.tsx` (botão "Buscar na internet" no cartão da detecção).
- Ferramentas rodam com `HOME=data/ferramentas_home` (ProtectHome=true no serviço); theHarvester = tag 4.11.1 (a main exige Python 3.14).

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
| 5 | Canal de alerta **Telegram** (monitores/Radar/Convocações) lendo `.env`; testes | ✅ 2026-10-09 (teste ao vivo OK às 19h UTC: mensagem entregue no chat 371824016) | `services/alerts.py` (`telegram`, HTML, JSONL preservado), `GET/POST /api/settings/telegram[/teste]`, card em Tema; `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` aceitos sem prefixo; 422 se canal telegram sem token. `app/sdnotify.py` (READY/WATCHDOG/STOPPING) |
| 6 | **OpenClaw** em usuário próprio (`openclaw`), daemon systemd, canal Telegram, agents O51NT | ✅ 2026-10-09 (LLM/Telegram ativam ao gravar as chaves) | `deploy/vps/05_openclaw.sh`. OpenClaw 2026.9.9, gateway `127.0.0.1:18789` (token), serviço de usuário `openclaw-gateway` (linger), agents `analista`/`sentinela` com skill `o51nt-api`, `tools.deny` exec/browser, Telegram allowlist 371824016, `tools.sessions.visibility=agent`, `agentToAgent` off. Armadilhas: rodar `openclaw` com `cd ~openclaw` (EACCES na sondagem do Node); o drop-in systemd só pode existir DEPOIS de `gateway install --force` |
| 7 | Fechamento SSH: `PermitRootLogin no`, `PasswordAuthentication no` | ✅ 2026-10-09 | `deploy/vps/06_ssh.sh` → `/etc/ssh/sshd_config.d/90-o51nt.conf` (`AllowUsers o51nt`). Validado: `o51nt` por chave + sudo OK; root e senha recusados |
| 8 | Verificação ponta a ponta + relatório (`deploy/vps/RELATORIO_IMPLANTACAO.md`) | ✅ 2026-10-09 | Todos os serviços ativos, watchdog vivo, HTTPS 401/200/403, ciclo do Radar OK, 0 erros no journal. **Pendência única:** chaves (Anthropic/OpenAI/Telegram) ainda não gravadas → `sudo bash /opt/o51nt/app/deploy/vps/segredos.sh` na VM (interativo). Até lá Telegram e LLM do OpenClaw ficam inativos |
| 10 | **Assistente de IA autônomo** (pipeline OpenClaw), fontes do tipo página, ferramentas Kali na VPS, busca a partir do cartaz | ✅ 2026-10-09 23h UTC — **ligado na VPS** (`iaAtivo=true`, fila a cada 5 min, teto US$ 3/dia) | Validado ao vivo: 2 hits reais triados (DESCARTAR, corretos) a US$ 0,0017 o ciclo; 12 ferramentas instaladas (theHarvester 4.11.1); endpoint HTTP do gateway 200. Armadilhas: `x-openclaw-model` só aceita modelos da lista do agent → modelo barato configurado no próprio `sentinela` + fallback no pipeline; `max_completion_tokens` inclui o raciocínio → `thinkingDefault: "off"` nos agents de JSON e `tools.profile: "minimal"` (sem isso: 20–40k tokens/chamada e resposta truncada); o gateway devolve `model=openclaw/<agent>` → custo estimado pelo modelo configurado |
| 9 | **Login do painel**: e-mail autorizado + código de uso único; usuários só por admin; auditoria; fail2ban no Caddy; preparação Cloudflare | ✅ 2026-10-09 (SMTP pendente: até lá o código cai no journal) | Admin `adiogo27@gmail.com` (`O51NT_ADMIN_EMAIL` no `.env`). Código: `backend/app/{services/auth.py,middleware_auth.py,routers/auth.py,models/auth.py}`, `frontend/src/{lib/auth.tsx,pages/Login,pages/Usuarios}`. Entrega do código: SMTP → Telegram do usuário → journal. Isenção: acesso loopback **sem** `X-Forwarded-For` (OpenClaw/health). Anti-CSRF: cookie `SameSite=Strict` + `X-Requested-With: O51NT`. Caddy: basic auth mantida como 1ª camada, `confiaveis.caddy`, `X-Real-IP`, CSP em modo relatório; jail `o51nt-caddy`. Cloudflare: `07_cloudflare.sh` (faixas + `--fechar`) e `CLOUDFLARE.md` (passos no painel do dono: DNS proxied, WAF, rate limit, Zero Trust Access com PIN por e-mail) |

Estado dos segredos (2026-10-09 19h UTC): Telegram OK (bot responde; exige `/start` do usuário antes), SMTP Gmail OK (código de login chega por e-mail), OpenAI OK (fallback do OpenClaw = `openai/gpt-5.5`), Anthropic OK desde 19h40 UTC (chave trocada pelo dono; agents respondem em `claude-sonnet-5-5`, fallback `openai/gpt-5.5`). OCR (rapidocr) instalado na VPS e validado com cartaz sintético. Armadilhas vistas: senha de app digitada no campo SMTP_HOST; OpenClaw reescreve `openclaw.json` em JSON (usar `openclaw config set`, não `sed`).

| 11 | **Leva 2026-10-10**: README/CI (PR #1); teto US$ 1, preços atuais, Haiku 5.5 em extração/cartão; fontes candidatas + validação ao vivo; deeplinks (Buscadores, Arquivo, Dados oficiais, Bluesky/Threads/Reddit/Lyzem, Bing Visual); camada OOVS; seletor na tela de login; deploy automático; Vitest de utils | 🔄 PR aberto | Pendências do dono na VM: `sudo bash deploy/vps/chave_deploy.sh` + segredos no GitHub; `sudo bash deploy/vps/05_openclaw.sh` (agents em Haiku); Tema → teto 1.0 e Assistente (ou `PUT /api/settings`) |

Arquivos de implantação versionados em `deploy/vps/` (scripts idempotentes; segredos só na VM).

### Itens do PLANO_MESTRE_OSINT recusados (com motivo)
Rotação de UA / `fake-useragent` / proxies residenciais (burla de bloqueio — contraria a regra ética);
watchdog como agente LLM com root "sem confirmação" (substituído pelo watchdog do systemd);
`bypassPermissions` no host do desenvolvedor (desnecessário e desaconselhado pela própria doc).
