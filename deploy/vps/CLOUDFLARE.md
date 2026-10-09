# Cloudflare na frente do O51NT — passo a passo

O que a Cloudflare acrescenta: WAF e proteção contra bots/DDoS antes do servidor, ocultação do IP da VPS, limite de
requisições no login e, com o **Zero Trust Access**, uma verificação por código no e-mail *antes mesmo* de chegar ao
painel. Tudo no plano gratuito. O servidor já está preparado (Caddy confia nos IPs da Cloudflare e o app lê o IP real
do visitante); o que falta é feito na conta Cloudflare do dono, em ~20 minutos.

## 1. Zona e DNS

1. Crie a conta em <https://dash.cloudflare.com> e clique em **Add a domain** → `sentinela.api.br` (plano Free).
2. A Cloudflare mostra dois servidores de nomes (ex.: `ada.ns.cloudflare.com`). No **Registro.br**, em
   `sentinela.api.br` → *Alterar servidores DNS*, substitua pelos dois indicados. A propagação leva de minutos a 24 h.
3. Em **DNS → Records** confirme/crie: tipo `A`, nome `o51nt`, conteúdo `162.35.16.238`, **Proxy status: Proxied**
   (nuvem laranja). Remova qualquer outro registro apontando para a VPS sem proxy (senão o IP continua exposto).

## 2. SSL/TLS

- **SSL/TLS → Overview**: modo **Full (strict)** (o Caddy já tem certificado válido da Let's Encrypt).
- **Edge Certificates**: *Always Use HTTPS* ON, *Minimum TLS Version* 1.2, *TLS 1.3* ON, *HSTS* ON
  (max-age 6 meses, include subdomains), *Automatic HTTPS Rewrites* ON.

## 3. Segurança

- **Security → Settings**: *Security Level* **High**, *Bot Fight Mode* ON, *Browser Integrity Check* ON.
- **Security → WAF → Managed rules**: ative o *Cloudflare Managed Ruleset* (free) e o *OWASP Core Ruleset* se disponível.
- **Security → WAF → Rate limiting rules** (1 regra grátis): *If* `URI Path starts with /api/auth/` → **10
  requisições / 10 s por IP** → *Block* por 1 h. Protege o pedido/verificação de código contra força bruta.
- **Security → WAF → Custom rules** (opcional): bloquear países de onde ninguém da equipe acessa
  (`ip.geoip.country ne "BR"` → Block). Cuidado com VPNs institucionais.

## 4. Zero Trust Access (código no e-mail antes do painel)

1. **Zero Trust** (menu lateral) → crie a organização (nome livre, plano Free, até 50 usuários).
2. **Settings → Authentication → Login methods**: *One-time PIN* (já vem ativo). Opcional: *Google* como IdP.
3. **Access → Applications → Add an application → Self-hosted**:
   - Application name `O51NT`, Session Duration **12 hours**, domain `o51nt.sentinela.api.br`.
   - Policy `Equipe O51NT`: Action **Allow**; Include → *Emails* → `adiogo27@gmail.com` (acrescente cada analista
     aqui; é a lista de quem passa pela porta da Cloudflare — o cadastro no painel continua sendo necessário).
   - Em *Additional settings*: *Enable Binding Cookie* ON, *HTTP Only* ON, *Same Site* Strict.
4. Teste: abra <https://o51nt.sentinela.api.br> em uma janela anônima → tela da Cloudflare pede o e-mail → código →
   depois a senha básica do Caddy → depois o login do O51NT (e-mail + código). Três camadas independentes.

> Para reduzir atrito depois de validado, pode-se remover a **senha básica** do Caddy (apague o bloco `basic_auth`
> do `/etc/caddy/Caddyfile` e `systemctl reload caddy`), mantendo Access + login do app.

## 5. Fechar o servidor para só a Cloudflare falar com ele

Depois que o DNS estiver *proxied* (nuvem laranja) e o site abrir pela Cloudflare:

```bash
ssh o51nt@162.35.16.238
sudo bash /opt/o51nt/app/deploy/vps/07_cloudflare.sh --fechar
```

O script confere que `o51nt.sentinela.api.br` resolve para IPs da Cloudflare (senão aborta sem tocar no firewall),
troca as regras 80/443 do UFW por regras só para as faixas da Cloudflare, atualiza o `trusted_proxies` do Caddy e
instala um timer semanal que mantém as faixas em dia. `--abrir` reverte. O SSH (22) não é afetado.

## O que já está pronto no servidor

| Item | Onde |
|---|---|
| Caddy confia nos IPs da Cloudflare e usa `CF-Connecting-IP` como IP do cliente | `/etc/caddy/confiaveis.caddy`, `Caddyfile` (`client_ip_headers`) |
| App recebe o IP real em `X-Real-IP` (auditoria, bloqueios por IP) | `backend/app/middleware_auth.py` |
| fail2ban lê o log do Caddy com IP real | `/etc/fail2ban/jail.d/o51nt-caddy.local` |
| Firewall só-Cloudflare + timer | `07_cloudflare.sh` |

## Observações

- A renovação do certificado Let's Encrypt (desafio HTTP-01) continua funcionando através do proxy da Cloudflare.
- Se o domínio for despromovido para *DNS only* (nuvem cinza) com o firewall fechado, o site some: rode `--abrir`.
- O Access só protege o que passa pela Cloudflare; por isso o passo 5 é o que torna a camada obrigatória.
