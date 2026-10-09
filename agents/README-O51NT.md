# Avaliação dos agentes desta pasta para o O51NT (2026-10-09)

Os três subdiretórios são **quickstarts genéricos de Managed Agents da Claude Platform**, exportados como arquivos
declarativos para a CLI `ant` (não é o Apache Ant instalado no Kali). Os `claude-lock.json` indicam que os três já
existem na organização Anthropic do dono (IDs `agent_01…`); rodam na nuvem da Anthropic, em sessões cobradas por uso,
e **nada no O51NT os chama**. Por isso a decisão foi portar o que serve para a camada de IA que o projeto já tem
(OpenClaw na VPS, com Telegram e acesso à API local), em vez de duplicar na nuvem.

| Quickstart | Serve? | O que foi feito |
|---|---|---|
| `deep-researcher` (pesquisa multi-etapa com fontes e citações) | **Sim** — é exatamente a verificação/aprofundamento que um analista faz sobre um hit, alerta ou convocação | Virou o agent **`pesquisador`** do OpenClaw (`deploy/vps/05_openclaw.sh`): mesmo método (subperguntas → fontes primárias lidas por inteiro → síntese citada → "Confiança e lacunas" → revisão das citações), com as regras do O51NT: só conteúdo público, sem redes sociais logadas, sem burlar bloqueio, LGPD, fontes oficiais e agências de checagem brasileiras primeiro, começa pelas URLs já no O51NT (skill `o51nt-api`) |
| `structured-extractor` (texto → JSON tipado) | **Sim** — útil para transformar OCR de cartaz/postagem em campos (data, hora, local, rodovias, organizador) e, se o analista pedir, cadastrar na Agenda | Virou o agent **`extrator`**, com a skill `o51nt-esquema` (esquema padrão de convocação, `impacto_rodovia_federal`, `confianca`, `_notas`), saída só JSON, sem dados pessoais, sem acesso à web |
| `field-monitor` (resumo semanal de blogs de software/IA → Notion) | **Não** — tema (arXiv, Hacker News, blogs de IA) e destino (Notion) estranhos ao projeto; o papel de "o que mudou na semana" já é do Radar + Boletim com fontes públicas | Nada implantado. Mantido aqui só como referência |

Observações:

- Os quickstarts usam `claude-opus-5-5`; no OpenClaw o modelo padrão é `anthropic/claude-sonnet-5-5` (variável
  `OPENCLAW_MODELO` no script). Os agents só respondem depois que a chave Anthropic for gravada por `segredos.sh`.
- Para usá-los pelo Telegram: a mensagem vai ao `analista` (binding padrão); peça "pesquisador: …" ou "extrator: …"
  e o analista encaminha, ou troque o binding em `~openclaw/.openclaw/openclaw.json`. Na VM, direto:
  `sudo -iu openclaw openclaw agent --agent pesquisador -m "…"`.
- Se um dia quiser os agentes também na nuvem da Anthropic, instale a CLI oficial
  (<https://platform.claude.com/docs/en/cli-sdks-libraries/cli/quickstart>) e rode `ant apply` em cada pasta.
  Vale apenas para uso fora do O51NT.
