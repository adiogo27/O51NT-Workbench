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

## Pendência única: gravar as chaves (passo manual, ~1 minuto)

As chaves da Anthropic, da OpenAI e do bot do Telegram **não estão na VM** (nem no repositório, de propósito).
Sem elas o painel funciona normalmente, mas o canal Telegram e as respostas do OpenClaw ficam inativos.

```bash
ssh o51nt@162.35.16.238
sudo bash /opt/o51nt/app/deploy/vps/segredos.sh
```

O script pergunta os três valores com digitação oculta (Enter em branco mantém o atual), grava em
`/opt/o51nt/.env` e em `/home/openclaw/.openclaw/{secrets.env,telegram.token}`, reinicia os serviços e envia uma
mensagem de teste para o chat 371824016 (@alertao51ntbot). Depois disso:

- em **Tema → Telegram** no painel o card mostra "configurado" e o botão de teste;
- os monitores aceitam `canal_alerta = telegram` (até lá a API devolve 422, por contrato);
- o OpenClaw responde no Telegram (DM do chat autorizado) como o agent `analista`.

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
| 6 | `segredos.sh` | root (interativo) | grava as chaves e testa o Telegram |
| 7 | `06_ssh.sh` | root | fecha root/senha no SSH |

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
