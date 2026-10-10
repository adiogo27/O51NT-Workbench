import { useMutation, useQuery } from "@tanstack/react-query";
import { RotateCcw, Save } from "lucide-react";
import * as React from "react";
import { ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";
import { api, type AppSettings, type Preferencias } from "@/lib/api";
import { applyTheme, DEFAULT_SETTINGS, FONTES, useSettingsStore } from "@/theme/ThemeProvider";

const CORES: { k: keyof AppSettings["tema"]; l: string }[] = [
  { k: "primary", l: "Primária" },
  { k: "secondary", l: "Secundária (barra lateral)" },
  { k: "background", l: "Fundo" },
  { k: "foreground", l: "Texto" },
  { k: "accent", l: "Destaque / foco" },
];

const PRESETS: Record<string, AppSettings["tema"]> = {
  "O51NT escuro": DEFAULT_SETTINGS.tema,
  "O51NT claro (PDF)": { primary: "#0091d5", secondary: "#e8f4fb", background: "#ffffff", foreground: "#111827", accent: "#f2e08a", radius: 0.375 },
  "Alto contraste": { primary: "#ffff00", secondary: "#000000", background: "#000000", foreground: "#ffffff", accent: "#00ffff", radius: 0 },
  Terminal: { primary: "#22c55e", secondary: "#0a0a0a", background: "#050505", foreground: "#d1fae5", accent: "#facc15", radius: 0.25 },
};

interface TelegramStatus {
  configurado: boolean;
  chat_id: string | null;
  bot: string | null;
  erro: string | null;
}

/** Status do canal Telegram. O token e o chat ID ficam só no .env do servidor — aqui não se edita nada. */
function TelegramCard() {
  const { data, isLoading, refetch } = useQuery({ queryKey: ["telegram-status"], queryFn: () => api.get<TelegramStatus>("/api/settings/telegram") });
  const teste = useMutation({ mutationFn: () => api.post<{ ok: boolean; message_id?: number; erro?: string }>("/api/settings/telegram/teste") });
  return (
    <Card className="lg:col-span-2">
      <CardTitle>Alertas no Telegram</CardTitle>
      {isLoading || !data ? (
        <p className="text-sm text-muted-foreground">Verificando…</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <Badge variant={data.configurado ? "success" : "muted"}>{data.configurado ? "configurado" : "não configurado"}</Badge>
          {data.bot && <span>bot <strong>@{data.bot}</strong></span>}
          {data.chat_id && <span className="code text-xs">chat {data.chat_id}</span>}
          {data.erro && <span className="text-warning">{data.erro}</span>}
          <span className="flex-1" />
          <Button size="sm" variant="outline" onClick={() => void refetch()}>Atualizar</Button>
          <Button size="sm" disabled={!data.configurado || teste.isPending} onClick={() => teste.mutate()}>
            {teste.isPending ? "Enviando…" : "Enviar mensagem de teste"}
          </Button>
        </div>
      )}
      {teste.data && (
        <div className="mt-2">
          <Alert variant={teste.data.ok ? "success" : "error"}>{teste.data.ok ? `Mensagem enviada (id ${teste.data.message_id}).` : `Falhou: ${teste.data.erro}`}</Alert>
        </div>
      )}
      <ErrorText error={teste.error} />
      <p className="mt-2 text-xs text-muted-foreground">
        Configuração: <span className="code">TELEGRAM_BOT_TOKEN</span> e <span className="code">TELEGRAM_CHAT_ID</span> no arquivo <span className="code">.env</span> do servidor (reinicie o serviço).
        Depois escolha o canal "Telegram" nos monitores, na Agenda, nos perfis ou nas Convocações.
      </p>
    </Card>
  );
}

export default function SettingsPage() {
  const { settings, save } = useSettingsStore();
  const [draft, setDraft] = React.useState<AppSettings>(settings);
  const [status, setStatus] = React.useState<string | null>(null);
  const [erro, setErro] = React.useState<unknown>(null);
  const { data: browsers } = useQuery({ queryKey: ["browsers"], queryFn: () => api.get<{ disponiveis: string[] }>("/api/settings/browsers") });

  React.useEffect(() => setDraft(settings), [settings]);
  // preview ao vivo: aplica o rascunho; ao sair sem salvar, restaura o salvo
  React.useEffect(() => applyTheme(draft), [draft]);
  React.useEffect(() => () => applyTheme(useSettingsStore.getState().settings), []);

  const setTema = (k: keyof AppSettings["tema"], v: string | number) => setDraft({ ...draft, tema: { ...draft.tema, [k]: v } });
  const setPref = <K extends keyof Preferencias>(k: K, v: Preferencias[K]) => setDraft({ ...draft, preferencias: { ...draft.preferencias, [k]: v } });
  const salvar = async () => {
    try {
      setErro(null);
      await save(draft);
      setStatus("Salvo em data/settings.json");
    } catch (e) {
      setErro(e);
    }
  };

  return (
    <>
      <PageHeader title="Tema" description="Cores e tipografia persistidas em disco (data/settings.json) e aplicadas via CSS variables.">
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setDraft(DEFAULT_SETTINGS)}><RotateCcw size={14} /> Padrão</Button>
          <Button onClick={() => void salvar()}><Save size={14} /> Salvar</Button>
        </div>
      </PageHeader>
      {status && <div className="mb-3"><Alert variant="success">{status}</Alert></div>}
      <ErrorText error={erro} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Cores</CardTitle>
          <div className="mb-3 flex flex-wrap gap-2">
            {Object.entries(PRESETS).map(([n, t]) => (
              <Button key={n} size="sm" variant="outline" onClick={() => setDraft({ ...draft, tema: t })}>{n}</Button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {CORES.map(({ k, l }) => (
              <Field key={k} label={l} htmlFor={`c-${k}`}>
                <div className="flex gap-2">
                  <input id={`c-${k}`} type="color" value={String(draft.tema[k])} onChange={(e) => setTema(k, e.target.value)} className="h-9 w-12 cursor-pointer rounded border border-border bg-transparent" />
                  <Input aria-label={`${l} (hex)`} value={String(draft.tema[k])} onChange={(e) => setTema(k, e.target.value)} className="font-mono" maxLength={7} />
                </div>
              </Field>
            ))}
            <Field label={`Raio das bordas: ${draft.tema.radius}rem`} htmlFor="radius">
              <input id="radius" type="range" min={0} max={1.5} step={0.125} value={draft.tema.radius} onChange={(e) => setTema("radius", Number(e.target.value))} className="w-full" />
            </Field>
          </div>
        </Card>
        <Card>
          <CardTitle>Tipografia e preferências</CardTitle>
          <div className="space-y-3">
            <Field label="Fonte" htmlFor="font">
              <Select id="font" value={draft.tipografia.fontFamily} onChange={(e) => setDraft({ ...draft, tipografia: { ...draft.tipografia, fontFamily: e.target.value } })}>
                {Object.keys(FONTES).map((f) => <option key={f}>{f}</option>)}
              </Select>
            </Field>
            <Field label={`Tamanho base: ${draft.tipografia.fontSizeBase}px`} htmlFor="fsize">
              <input id="fsize" type="range" min={12} max={24} step={1} value={draft.tipografia.fontSizeBase} onChange={(e) => setDraft({ ...draft, tipografia: { ...draft.tipografia, fontSizeBase: Number(e.target.value) } })} className="w-full" />
            </Field>
            <Field label="Navegador padrão (iniciar.sh e run.sh)" htmlFor="nav" hint="'auto' = navegador padrão do sistema no iniciar.sh (primeiro disponível no run.sh). O run.sh também aceita --browser.">
              <Select id="nav" value={draft.preferencias.navegadorPadrao} onChange={(e) => setDraft({ ...draft, preferencias: { ...draft.preferencias, navegadorPadrao: e.target.value } })}>
                <option value="auto">auto</option>
                {browsers?.disponiveis.map((b) => <option key={b}>{b}</option>)}
              </Select>
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Radar: coleta automática de fontes" htmlFor="radar-ativo" hint="Feeds públicos (imprensa, Mastodon, Google Alertas) casados com todos os monitores ativos.">
                <label className="flex h-9 items-center gap-2 text-sm">
                  <input id="radar-ativo" type="checkbox" checked={draft.preferencias.radarAtivo}
                    onChange={(e) => setDraft({ ...draft, preferencias: { ...draft.preferencias, radarAtivo: e.target.checked } })} />
                  ligado
                </label>
              </Field>
              <Field label="Radar: intervalo entre ciclos (min, 2–1440)" htmlFor="radar-int">
                <Input id="radar-int" type="number" min={2} max={1440} value={draft.preferencias.radarIntervaloMin}
                  onChange={(e) => setDraft({ ...draft, preferencias: { ...draft.preferencias, radarIntervaloMin: Number(e.target.value) } })} />
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Histórico: reter por (dias, 0 = sempre)" htmlFor="ret">
                <Input id="ret" type="number" min={0} max={36500} value={draft.preferencias.historicoRetencaoDias}
                  onChange={(e) => setDraft({ ...draft, preferencias: { ...draft.preferencias, historicoRetencaoDias: Number(e.target.value) } })} />
              </Field>
              <Field label="Histórico: máximo de entradas (0 = sem teto)" htmlFor="maxh">
                <Input id="maxh" type="number" min={0} max={1000000} value={draft.preferencias.historicoMaxEntradas}
                  onChange={(e) => setDraft({ ...draft, preferencias: { ...draft.preferencias, historicoMaxEntradas: Number(e.target.value) } })} />
              </Field>
            </div>
          </div>
        </Card>
        <TelegramCard />
        <Card className="lg:col-span-2">
          <CardTitle>Convocações (detector de cartazes)</CardTitle>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Coletor agendado" htmlFor="conv-ativo" hint="Bluesky, canais do Telegram, SearXNG imagens e feeds com mídia">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="conv-ativo" type="checkbox" checked={draft.preferencias.convocacoesAtivo} onChange={(e) => setPref("convocacoesAtivo", e.target.checked)} /> ligado</label>
            </Field>
            <Field label="Intervalo do coletor (min)" htmlFor="conv-int"><Input id="conv-int" type="number" min={5} max={1440} value={draft.preferencias.convocacoesIntervaloMin} onChange={(e) => setPref("convocacoesIntervaloMin", Number(e.target.value))} /></Field>
            <Field label="Perfil de IA" htmlFor="conv-perfil" hint="completo = CLIP (PyTorch); requer ./run.sh --ml e ~1 GB de RAM">
              <Select id="conv-perfil" value={draft.preferencias.convocacoesPerfilML} onChange={(e) => setPref("convocacoesPerfilML", e.target.value as "leve" | "completo")}><option value="leve">leve (OCR + léxico + QR)</option><option value="completo">completo (+ CLIP)</option></Select>
            </Field>
            <Field label="Máx. imagens por ciclo" htmlFor="conv-max"><Input id="conv-max" type="number" min={1} max={500} value={draft.preferencias.convocacoesMaxImagensCiclo} onChange={(e) => setPref("convocacoesMaxImagensCiclo", Number(e.target.value))} /></Field>
            <Field label="Limiar de alerta (score)" htmlFor="conv-la"><Input id="conv-la" type="number" min={1} max={100} value={draft.preferencias.convocacoesLimiarAlerta} onChange={(e) => setPref("convocacoesLimiarAlerta", Number(e.target.value))} /></Field>
            <Field label="Limiar crítico (score)" htmlFor="conv-lc"><Input id="conv-lc" type="number" min={1} max={100} value={draft.preferencias.convocacoesLimiarCritico} onChange={(e) => setPref("convocacoesLimiarCritico", Number(e.target.value))} /></Field>
            <Field label="Canal de alerta" htmlFor="conv-canal">
              <Select id="conv-canal" value={draft.preferencias.convocacoesCanalAlerta} onChange={(e) => setPref("convocacoesCanalAlerta", e.target.value as "jsonl" | "webhook" | "telegram" | "nenhum")}><option value="jsonl">JSONL (data/alerts)</option><option value="webhook">webhook</option><option value="telegram">Telegram</option><option value="nenhum">só inbox</option></Select>
            </Field>
            <Field label="Webhook URL" htmlFor="conv-wh"><Input id="conv-wh" value={draft.preferencias.convocacoesWebhookUrl ?? ""} onChange={(e) => setPref("convocacoesWebhookUrl", e.target.value || null)} placeholder="https://…" /></Field>
            <Field label="Peso léxico" htmlFor="p-lex"><Input id="p-lex" type="number" step={0.05} min={0} max={1} value={draft.preferencias.convocacoesPesoLexico} onChange={(e) => setPref("convocacoesPesoLexico", Number(e.target.value))} /></Field>
            <Field label="Peso visual (CLIP)" htmlFor="p-vis"><Input id="p-vis" type="number" step={0.05} min={0} max={1} value={draft.preferencias.convocacoesPesoVisual} onChange={(e) => setPref("convocacoesPesoVisual", Number(e.target.value))} /></Field>
            <Field label="Peso referência" htmlFor="p-ref"><Input id="p-ref" type="number" step={0.05} min={0} max={1} value={draft.preferencias.convocacoesPesoReferencia} onChange={(e) => setPref("convocacoesPesoReferencia", Number(e.target.value))} /></Field>
            <Field label="Peso monitores" htmlFor="p-mon"><Input id="p-mon" type="number" step={0.05} min={0} max={1} value={draft.preferencias.convocacoesPesoMonitor} onChange={(e) => setPref("convocacoesPesoMonitor", Number(e.target.value))} /></Field>
            <Field label="Bônus QR/link de grupo" htmlFor="p-bon"><Input id="p-bon" type="number" min={0} max={50} value={draft.preferencias.convocacoesBonusDistribuicao} onChange={(e) => setPref("convocacoesBonusDistribuicao", Number(e.target.value))} /></Field>
            <Field label="Descarregar modelos após (min ocioso)" htmlFor="conv-desc"><Input id="conv-desc" type="number" min={1} max={240} value={draft.preferencias.convocacoesDescarregarMin} onChange={(e) => setPref("convocacoesDescarregarMin", Number(e.target.value))} /></Field>
            <Field label="Analisar imagens dos feeds do Radar" htmlFor="conv-feeds">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="conv-feeds" type="checkbox" checked={draft.preferencias.convocacoesAnalisarFeeds} onChange={(e) => setPref("convocacoesAnalisarFeeds", e.target.checked)} /> sim</label>
            </Field>
            <Field label="Reter descartadas (dias, 0 = sempre)" htmlFor="conv-ret"><Input id="conv-ret" type="number" min={0} max={36500} value={draft.preferencias.convocacoesRetencaoDias} onChange={(e) => setPref("convocacoesRetencaoDias", Number(e.target.value))} /></Field>
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Field label="Termos extras (peso 2, categoria convocação)" htmlFor="conv-extra" hint="um por linha; sem acento é opcional (comparação ignora acentos)">
              <Textarea id="conv-extra" rows={3} value={draft.preferencias.convocacoesTermosExtra.join("\n")} onChange={(e) => setPref("convocacoesTermosExtra", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} />
            </Field>
            <Field label="Termos a ignorar" htmlFor="conv-excl" hint="ex.: 'greve' se o contexto gerar falsos positivos">
              <Textarea id="conv-excl" rows={3} value={draft.preferencias.convocacoesTermosExcluir.join("\n")} onChange={(e) => setPref("convocacoesTermosExcluir", e.target.value.split("\n").map((x) => x.trim()).filter(Boolean))} />
            </Field>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <CardTitle>Assistente de IA (OpenClaw)</CardTitle>
          <p className="mb-2 text-xs text-muted-foreground">Só o que casou com os termos dos monitores vai para a IA. Cadeia sentinela → extrator → pesquisador → analista; alertas automáticos; Boletim e Agenda conforme a política abaixo. Token do gateway e chaves ficam no servidor.</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Assistente ligado" htmlFor="ia-ativo">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="ia-ativo" type="checkbox" checked={draft.preferencias.iaAtivo} onChange={(e) => setPref("iaAtivo", e.target.checked)} /> ligado</label>
            </Field>
            <Field label="Intervalo da fila (min)" htmlFor="ia-int"><Input id="ia-int" type="number" min={1} max={1440} value={draft.preferencias.iaIntervaloMin} onChange={(e) => setPref("iaIntervaloMin", Number(e.target.value))} /></Field>
            <Field label="Máx. itens por ciclo" htmlFor="ia-max"><Input id="ia-max" type="number" min={1} max={500} value={draft.preferencias.iaMaxItensCiclo} onChange={(e) => setPref("iaMaxItensCiclo", Number(e.target.value))} /></Field>
            <Field label="Teto diário (US$, 0 = sem teto)" htmlFor="ia-teto"><Input id="ia-teto" type="number" step={0.5} min={0} max={1000} value={draft.preferencias.iaCustoDiarioUsd} onChange={(e) => setPref("iaCustoDiarioUsd", Number(e.target.value))} /></Field>
            <Field label="Boletim" htmlFor="ia-bol" hint="o que fazer com itens RELEVANTE">
              <Select id="ia-bol" value={draft.preferencias.iaBoletim} onChange={(e) => setPref("iaBoletim", e.target.value as "auto" | "aprovar" | "nunca")}><option value="aprovar">só com aprovação</option><option value="auto">automático</option><option value="nunca">nunca</option></Select>
            </Field>
            <Field label="Agenda" htmlFor="ia-ag" hint="eventos extraídos com data">
              <Select id="ia-ag" value={draft.preferencias.iaAgenda} onChange={(e) => setPref("iaAgenda", e.target.value as "auto" | "aprovar" | "nunca")}><option value="aprovar">só com aprovação</option><option value="auto">automático</option><option value="nunca">nunca</option></Select>
            </Field>
            <Field label="Pesquisador automático a partir de" htmlFor="ia-pesq" hint="etapa mais cara: verifica fontes na web">
              <Select id="ia-pesq" value={draft.preferencias.iaPesquisarSeveridadeMin} onChange={(e) => setPref("iaPesquisarSeveridadeMin", e.target.value as Preferencias["iaPesquisarSeveridadeMin"])}><option value="baixa">qualquer RELEVANTE</option><option value="media">média</option><option value="alta">alta</option><option value="critica">crítica</option><option value="nunca">só sob pedido</option></Select>
            </Field>
            <Field label="Resumo dos OBSERVAR (horas)" htmlFor="ia-res"><Input id="ia-res" type="number" min={1} max={168} value={draft.preferencias.iaResumoHoras} onChange={(e) => setPref("iaResumoHoras", Number(e.target.value))} /></Field>
            <Field label="Modelo da triagem" htmlFor="ia-mt" hint="barato: 1 chamada por item"><Input id="ia-mt" value={draft.preferencias.iaModeloTriagem} onChange={(e) => setPref("iaModeloTriagem", e.target.value)} /></Field>
            <Field label="Modelo do pesquisador" htmlFor="ia-mp" hint="etapa com ferramentas; vazio = padrão do OpenClaw"><Input id="ia-mp" value={draft.preferencias.iaModeloPadrao ?? ""} onChange={(e) => setPref("iaModeloPadrao", e.target.value || null)} placeholder="anthropic/claude-sonnet-5-5" /></Field>
            <Field label="Modelo leve (extração e cartão)" htmlFor="ia-ml" hint="JSON curto: Haiku 5.5 custa 1/20 do Sonnet"><Input id="ia-ml" value={draft.preferencias.iaModeloLeve ?? ""} onChange={(e) => setPref("iaModeloLeve", e.target.value || null)} placeholder="anthropic/claude-haiku-5-5" /></Field>
            <Field label="Texto da matéria (máx. caracteres)" htmlFor="ia-txt"><Input id="ia-txt" type="number" min={500} max={30000} value={draft.preferencias.iaTextoMaxChars} onChange={(e) => setPref("iaTextoMaxChars", Number(e.target.value))} /></Field>
            <Field label="Checagem de aterramento (OOVS)" htmlFor="ia-oovs" hint="confere o cartão contra as fontes; 1 chamada barata, só RELEVANTE">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="ia-oovs" type="checkbox" checked={draft.preferencias.iaAterramento} onChange={(e) => setPref("iaAterramento", e.target.checked)} /> ligada</label>
            </Field>
            <Field label="Telegram imediato para RELEVANTE" htmlFor="ia-tg">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="ia-tg" type="checkbox" checked={draft.preferencias.iaTelegramRelevante} onChange={(e) => setPref("iaTelegramRelevante", e.target.checked)} /> sim</label>
            </Field>
            <Field label="Suprimir alerta bruto do Radar" htmlFor="ia-sup" hint="o 'N novos resultados' dá lugar ao cartão triado">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="ia-sup" type="checkbox" checked={draft.preferencias.iaSuprimirAlertasBrutos} onChange={(e) => setPref("iaSuprimirAlertasBrutos", e.target.checked)} /> sim</label>
            </Field>
            <Field label="Marcar DESCARTAR como lido" htmlFor="ia-lido">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="ia-lido" type="checkbox" checked={draft.preferencias.iaMarcarLidos} onChange={(e) => setPref("iaMarcarLidos", e.target.checked)} /> sim</label>
            </Field>
            <Field label="Ferramentas sensíveis (LGPD)" htmlFor="fer-sens" hint="holehe, h8mail, phoneinfoga: dados pessoais de terceiros; cada uso é auditado">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="fer-sens" type="checkbox" checked={draft.preferencias.ferramentasSensiveisAtivas} onChange={(e) => setPref("ferramentasSensiveisAtivas", e.target.checked)} /> habilitadas</label>
            </Field>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <CardTitle>Convites (verificação de links de grupo)</CardTitle>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Respeitar robots.txt ao testar" htmlFor="inv-robots" hint="t.me / whatsapp.com; pode ser ignorado por link, com aviso">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="inv-robots" type="checkbox" checked={draft.preferencias.convitesRespeitarRobots} onChange={(e) => setPref("convitesRespeitarRobots", e.target.checked)} /> sim</label>
            </Field>
            <Field label="Reverificação automática" htmlFor="inv-auto" hint="até 20 links por rodada, mais antigos primeiro">
              <label className="flex h-9 items-center gap-2 text-sm"><input id="inv-auto" type="checkbox" checked={draft.preferencias.convitesVerificarAuto} onChange={(e) => setPref("convitesVerificarAuto", e.target.checked)} /> ligada</label>
            </Field>
            <Field label="Intervalo (horas)" htmlFor="inv-int"><Input id="inv-int" type="number" min={1} max={720} value={draft.preferencias.convitesVerificarIntervaloHoras} onChange={(e) => setPref("convitesVerificarIntervaloHoras", Number(e.target.value))} /></Field>
          </div>
        </Card>
        <Card className="lg:col-span-2">
          <CardTitle>Preview ao vivo</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Button>Primária</Button>
            <Button variant="secondary">Secundária</Button>
            <Button variant="accent">Destaque</Button>
            <Button variant="outline">Contorno</Button>
            <Badge variant="default">badge</Badge>
            <Badge variant="accent">PDF</Badge>
          </div>
          <p className="mt-3">Texto normal no tamanho base. <span className="text-muted-foreground">Texto secundário.</span></p>
          <p className="code mt-2 rounded-md bg-muted p-2">(site:facebook.com OR site:instagram.com) #NomeHashTag</p>
          <div className="mt-2"><Alert variant="warning">Exemplo de aviso do validador.</Alert></div>
        </Card>
      </div>
    </>
  );
}
