# Relatório de implantação — O51NT Workbench na VPS

Data: 2026-10-09. VM: InterServer KVM `vps3700295` (Ubuntu 24.04.5, 2 vCPU, 7,8 GB RAM, 156 GB), IP `162.35.16.238`,
domínio `o51nt.sentinela.api.br`. Executor: Claude Code, sob autorização do dono do projeto.

## Estado final (verificado em 2026-10-09 11:30 BRT)

| Componente | Estado |
|---|---|
| `o51nt.service` (uvicorn `127.0.0.1:8051`, `Type=notify`, `WatchdogSec=90`) | ativo, WATCHDOG=1 chegando a cada 30 s, 0 erros no journal |
| Caddy (HTTPS Let's Encrypt até 2027-01-07, basic auth) | ativo; `/api/health` → 401 sem senha, 200 com senha; HTTP por IP → 403 |
| SearXNG (Docker, `127.0.0.1:8080`) | ativo, busca JSON responde 200 |
| Radar (ciclo a cada 10 min) | ciclo forçado OK em 6,6 s, todas as fontes 200 |
| Backup diário (`o51nt-backup.timer`, 03:30, mantém 7) | ativo, próximo 2026-10-10 03:34 |
| OpenClaw 2026.9.9 (`openclaw-gateway`, usuário `openclaw`, `127.0.0.1:18789`) | ativo; agents `analista` e `sentinela`; auditoria de segurança sem alertas críticos |
| UFW | ativo: só 22/80/443 |
| fail2ban (sshd) | ativo; já baniu 3 IPs nas primeiras horas |
| SSH | só chave, só usuário `o51nt`; root e senha recusados (validado de fora) |
| Recursos | 1,3 GB RAM em uso, 10 GB de disco (7 %), load 0,5 |

Portas expostas à internet: 22, 80, 443. Tudo o mais (8051, 8080, 18789, 2019) é loopback.

## Acesso

- Painel: `https://o51nt.sentinela.api.br` — usuário e senha em `/root/o51nt-credenciais.txt` na VM
  (`sudo cat /root/o51nt-credenciais.txt`). Não estão no repositório.
- SSH: `ssh o51nt@162.35.16.238` (chave já autorizada). `sudo` sem senha.
- OpenClaw: `sudo -iu openclaw` e depois `openclaw status`, `openclaw health`, `openclaw security audit`.

## Login do painel (adicionado em 2026-10-09, 18h BRT)

Três camadas independentes, todas verificadas ao vivo:

1. **Senha básica do Caddy** (já existente) — credenciais em `/root/o51nt-credenciais.txt`.
2. **Login do O51NT**: e-mail autorizado + código de 6 dígitos de uso único (10 min, 5 tentativas). Administrador inicial:
   `adiogo27@gmail.com`. Só administradores cadastram usuários (menu **Usuários**), com auditoria de cada pedido,
   acerto, erro, bloqueio e alteração (e-mail, IP, horário). Bloqueio de 15 min após 5 erros por e-mail (20 por IP);
   sessão de 12 h, encerrada após 2 h sem uso; cookie HttpOnly/Secure/SameSite=Strict; anti-CSRF por cabeçalho.
   Respostas nunca revelam se um e-mail existe.
3. **Cloudflare (opcional, feito na conta do dono)** — WAF, rate limit no login e **Zero Trust Access** com PIN por
   e-mail antes de chegar ao servidor. Passo a passo em `deploy/vps/CLOUDFLARE.md`; o servidor já confia nos IPs da
   Cloudflare e `07_cloudflare.sh --fechar` deixa o firewall aceitando só a Cloudflare.

Também: fail2ban agora lê o log do Caddy e bane (só nas portas 80/443) quem erra a senha básica ou o código de login
8 vezes em 10 min; cabeçalhos `Permissions-Policy`, `Cross-Origin-*` e CSP em modo relatório.

**Entrega do código**: por e-mail (SMTP). Enquanto o SMTP não estiver configurado, o código cai no Telegram do usuário
(se o bot estiver configurado) ou no journal do serviço — nesse caso a tela de login avisa e o operador lê com
`sudo journalctl -u o51nt | grep CODIGO`. O acesso local direto (OpenClaw, health) não passa pelo login.

## Assistente de IA autônomo (adicionado em 2026-10-09, 19h BRT)

O OpenClaw passou a trabalhar os termos dos monitores sem intervenção: o Radar coleta (feeds e, agora, páginas HTML
sem RSS), só o que casa com os termos dos monitores entra na fila, e a cadeia sentinela → extrator → pesquisador →
analista produz veredito, evento, verificação e cartão. Alertas e Telegram saem sozinhos; Boletim e Agenda só com
aprovação (painel **Assistente** ou "aprovar N" no chat do bot). Teto diário de custo, resumo periódico dos itens
OBSERVAR e auditoria completa em `/ia`. Ferramentas OSINT do Kali (12) instaladas em `/opt/o51nt/ferramentas` e
expostas em **Ferramentas → Ferramentas OSINT do servidor** e ao agent pesquisador; as sensíveis (holehe, h8mail,
phoneinfoga) ficam desligadas até serem habilitadas em Tema. Em **Convocações**, cada cartaz tem "Buscar na internet":
termos lidos → convites abertos de WhatsApp/Telegram, menções na web/redes e monitor contínuo.

Ligar: Tema → Assistente de IA → "Assistente ligado" (padrões: fila a cada 5 min, 25 itens/ciclo, teto US$ 3/dia).

## Pendência única: gravar as chaves (passo manual, ~2 minutos)

As chaves da Anthropic, da OpenAI, do bot do Telegram e a **senha de app do Gmail (SMTP)** não estão na VM (nem no
repositório, de propósito). Sem elas o painel funciona, mas o canal Telegram e o OpenClaw ficam inativos e o código de
login não chega por e-mail. Para o Gmail: verificação em 2 etapas ativa → <https://myaccount.google.com/apppasswords>
→ criar senha de app "O51NT" (16 letras) e informá-la ao script.

```bash
ssh o51nt@162.35.16.238
sudo bash /opt/o51nt/app/deploy/vps/segredos.sh
```

O script pergunta as chaves e os dados de SMTP (senhas com digitação oculta; Enter mantém o atual), grava em
`/opt/o51nt/.env` e em `/home/openclaw/.openclaw/{secrets.env,telegram.token}`, reinicia os serviços e envia uma
mensagem de teste para o chat 371824016 (@alertao51ntbot). Depois disso:

- em **Tema → Telegram** no painel o card mostra "configurado" e o botão de teste;
- os monitores aceitam `canal_alerta = telegram` (até lá a API devolve 422, por contrato);
- o OpenClaw responde no Telegram (DM do chat autorizado) como o agent `analista`;
- o login do painel passa a enviar o código por e-mail (`/api/auth/estado` mostra `canal: email`).

## Layout na VM

```
/opt/o51nt/
  app/        checkout do repositório (git pull + deploy/vps/03_o51nt.sh para atualizar)
  venv/       Python 3.12 + deps
  data/       SQLite (WAL), evidências, alertas JSONL
  backups/    o51nt-AAAA-MM-DD.tar.gz (7 mais recentes)
  .env        segredos do app (600, dono o51nt)
/home/openclaw/.openclaw/   openclaw.json, secrets.env, telegram.token, workspace-analista/, workspace-sentinela/
/etc/caddy/Caddyfile        gerado por 04_caddy.sh (hash da senha)
/etc/ssh/sshd_config.d/90-o51nt.conf
```

## Scripts (idempotentes, em `deploy/vps/`)

| Ordem | Script | Executar como | O que faz |
|---|---|---|---|
| 1 | `01_endurecer.sh` | root | updates, timezone, usuário `o51nt`, UFW, fail2ban, unattended-upgrades |
| 2 | `02_dependencias.sh` | root | Node 24, Docker, Caddy (binário oficial: o repo apt deu 402) |
| 3 | `03_o51nt.sh` | `o51nt` | clone/pull, venv, build do frontend, SearXNG, `o51nt.service`, backup. **Reexecutar para atualizar.** |
| 4 | `04_caddy.sh` | root | credenciais, Caddyfile, HTTPS |
| 5 | `05_openclaw.sh` | root | usuário `openclaw`, OpenClaw, agents, gateway como serviço de usuário |
| 6 | `segredos.sh` | root (interativo) | grava as chaves, o SMTP do login e testa o Telegram |
| 7 | `06_ssh.sh` | root | fecha root/senha no SSH |
| 8 | `07_cloudflare.sh [--fechar]` | root | faixas da Cloudflare no Caddy; `--fechar` restringe 80/443 à Cloudflare (ver `CLOUDFLARE.md`) |

## Deploy automático (2026-10-10)

O CI (`.github/workflows/ci.yml`) ganhou o job `deploy`: após merge na `main` com pytest, Vitest, tsc e Playwright verdes,
ele entra por SSH na VM e executa `cd /opt/o51nt/app && git pull && bash deploy/vps/03_o51nt.sh`. A chave usada é
exclusiva e restrita a esse comando (`authorized_keys` com `command=`, sem pty/forwarding). Ativação, uma vez, na VM:

```bash
sudo bash /opt/o51nt/app/deploy/vps/chave_deploy.sh   # imprime VPS_HOST, VPS_USER, VPS_KNOWN_HOSTS e a chave privada
```

Grave os quatro valores em GitHub → Settings → Secrets and variables → Actions. Sem eles o job é pulado com um aviso.
Rodar o script de novo gera outra chave e revoga a anterior. O fail2ban do SSH continua ativo: um segredo errado por
vários pushes seguidos pode banir o IP do runner por um tempo, sem efeito no serviço.

## Operação

```bash
# logs
sudo journalctl -u o51nt -f
sudo journalctl -u caddy -f
sudo -iu openclaw journalctl --user -u openclaw-gateway -f
# atualizar o app após um push
cd /opt/o51nt/app && git pull && bash deploy/vps/03_o51nt.sh
# backup manual / restauração
sudo systemctl start o51nt-backup.service ; ls /opt/o51nt/backups
```

## Problemas encontrados e como foram resolvidos

- Repositório apt do Caddy (Cloudsmith) respondeu 402 → Caddy instalado do GitHub Releases com checksum e unit oficial.
- `caddy validate` executado como root criou `/var/log/caddy/o51nt.log` com dono root e o serviço caiu → `chown caddy:caddy` no script.
- OpenClaw: `EACCES` na sondagem do Node porque o cwd (`/home/o51nt`) é inacessível ao usuário `openclaw` → `cd ~openclaw` antes de invocar.
- OpenClaw: `gateway install` recusa "artefatos alterados" se o drop-in systemd já existe → o script remove o drop-in, instala com `--force` e só então cria o drop-in (`EnvironmentFile=secrets.env`).
- Auditoria do OpenClaw apontava sessões visíveis entre agents → `tools.sessions.visibility=agent` e `tools.agentToAgent.enabled=false`.
- Arquivos em `/opt/o51nt/app/deploy/vps` tinham ficado com dono root (cópia anterior) → `chown -R o51nt:o51nt /opt/o51nt/app`.

## Diferenças em relação ao PLANO_MESTRE_OSINT.md

O plano previa um "osint-brain" separado (trafilatura + analisador OpenAI + notificador próprio). Optou-se por
estender o O51NT existente: o Radar/monitores já fazem a coleta; o Telegram entrou como canal de alerta nativo
(`services/alerts.py`); a camada de IA é o OpenClaw com skill que consulta a API local. O watchdog systemd foi
implementado como no plano (`sd_notify`). Testes locais: 361 pytest, 43 Vitest, 10 E2E verdes após as mudanças.
