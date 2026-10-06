import { useQuery } from "@tanstack/react-query";
import { RotateCcw, Save } from "lucide-react";
import * as React from "react";
import { ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Field, Input, PageHeader, Select } from "@/components/ui";
import { api, type AppSettings } from "@/lib/api";
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
