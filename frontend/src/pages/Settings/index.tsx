import { useQuery } from "@tanstack/react-query";
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
              <Select id="conv-canal" value={draft.preferencias.convocacoesCanalAlerta} onChange={(e) => setPref("convocacoesCanalAlerta", e.target.value as "jsonl" | "webhook" | "nenhum")}><option value="jsonl">JSONL (data/alerts)</option><option value="webhook">webhook</option><option value="nenhum">só inbox</option></Select>
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
