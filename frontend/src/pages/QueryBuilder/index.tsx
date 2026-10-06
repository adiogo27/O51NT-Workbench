import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, RotateCcw, Save, Trash2 } from "lucide-react";
import * as React from "react";
import {
  DeeplinkButtons,
  ENGINES,
  EnginePicker,
  EthicsNotice,
  SearxngSearchButton,
  SearxngStatus,
  ErrorText,
  ListInput,
  ModeTabs,
  ProblemList,
  ScrapeExecucoes,
  useDebounced,
} from "@/components/shared";
import { Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";
import { api, qs, type ComposeResponse, type HistoryItem, type ScrapeExecucao, type Template, type ValidateResponse } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { BLOCOS_VAZIOS, toPayload, useQueryBuilderStore, type Blocos } from "@/store/useQueryBuilderStore";

function GruposOr({ grupos, onChange }: { grupos: string[][]; onChange: (g: string[][]) => void }) {
  return (
    <div className="space-y-2">
      {grupos.map((g, i) => (
        <div key={i} className="flex items-start gap-2">
          <div className="flex-1">
            <ListInput id={`or-${i}`} values={g} onChange={(v) => onChange(grupos.map((x, j) => (j === i ? v : x)))} placeholder="alternativa" />
          </div>
          <Button size="icon" variant="ghost" aria-label={`Remover grupo ${i + 1}`} onClick={() => onChange(grupos.filter((_, j) => j !== i))}>
            <Trash2 size={14} />
          </Button>
        </div>
      ))}
      <Button size="sm" variant="outline" onClick={() => onChange([...grupos, []])}>
        + grupo (A OR B)
      </Button>
    </div>
  );
}

function Curingas({ pares, onChange }: { pares: string[][]; onChange: (p: string[][]) => void }) {
  return (
    <div className="space-y-2">
      {pares.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input aria-label={`Curinga ${i + 1} termo 1`} value={p[0] ?? ""} onChange={(e) => onChange(pares.map((x, j) => (j === i ? [e.target.value, x[1] ?? ""] : x)))} />
          <span aria-hidden>*</span>
          <Input aria-label={`Curinga ${i + 1} termo 2`} value={p[1] ?? ""} onChange={(e) => onChange(pares.map((x, j) => (j === i ? [x[0] ?? "", e.target.value] : x)))} />
          <Button size="icon" variant="ghost" aria-label={`Remover curinga ${i + 1}`} onClick={() => onChange(pares.filter((_, j) => j !== i))}>
            <Trash2 size={14} />
          </Button>
        </div>
      ))}
      <Button size="sm" variant="outline" onClick={() => onChange([...pares, ["", ""]])}>
        + "Termo * Termo2"
      </Button>
    </div>
  );
}

function Localidades({ onAdd }: { onAdd: (termo: string) => void }) {
  const [q, setQ] = React.useState("");
  const dq = useDebounced(q);
  const { data } = useQuery({
    queryKey: ["locations", dq],
    queryFn: () => api.get<{ nome: string; tipo: string; uf: string; termo: string }[]>(`/api/locations${qs({ q: dq })}`),
    enabled: dq.length >= 2,
  });
  return (
    <Field label="Localidades (IBGE/DNIT — base local)" htmlFor="loc">
      <Input id="loc" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ex.: Curitiba, BR-116, SC" />
      {!!data?.length && (
        <ul className="mt-1 max-h-40 overflow-auto rounded-md border border-border">
          {data.slice(0, 12).map((l) => (
            <li key={`${l.tipo}-${l.nome}`}>
              <button type="button" className="w-full px-3 py-1 text-left text-sm hover:bg-muted" onClick={() => onAdd(l.termo)}>
                {l.nome} <span className="text-xs text-muted-foreground">({l.tipo} · {l.uf})</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Field>
  );
}

function TemplatesPanel({ onLoad, query }: { onLoad: (t: Template) => void; query: string }) {
  const qc = useQueryClient();
  const { data: templates = [] } = useQuery({ queryKey: ["templates"], queryFn: () => api.get<Template[]>("/api/query/templates") });
  const [nome, setNome] = React.useState("");
  const salvar = useMutation({
    mutationFn: () => api.post<Template>("/api/query/templates", { nome, query, categoria: "custom" }),
    onSuccess: () => {
      setNome("");
      void qc.invalidateQueries({ queryKey: ["templates"] });
    },
  });
  const remover = useMutation({
    mutationFn: (id: number) => api.del(`/api/query/templates/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["templates"] }),
  });
  return (
    <Card>
      <CardTitle>Templates</CardTitle>
      <ul className="max-h-80 space-y-1 overflow-auto pr-1">
        {templates.map((t) => (
          <li key={t.id} className="flex items-start gap-2 rounded-md p-1 hover:bg-muted">
            <button type="button" className="flex-1 text-left" onClick={() => onLoad(t)} title={t.query}>
              <span className="text-sm font-medium">{t.nome}</span>{" "}
              <Badge variant={t.origem_pdf ? "accent" : "muted"}>
                {t.origem_pdf ? (t.categoria === "x_tweetdeck" ? "Op. Eleições" : "PDF") : t.categoria}
              </Badge>
              <span className="code block text-xs text-muted-foreground">{t.query}</span>
            </button>
            {!t.origem_pdf && (
              <Button size="icon" variant="ghost" aria-label={`Excluir template ${t.nome}`} onClick={() => remover.mutate(t.id)}>
                <Trash2 size={14} />
              </Button>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <Input aria-label="Nome do novo template" placeholder="Nome do template" value={nome} onChange={(e) => setNome(e.target.value)} />
        <Button size="sm" disabled={!nome.trim() || !query} onClick={() => salvar.mutate()}>
          <Save size={14} /> Salvar
        </Button>
      </div>
      <ErrorText error={salvar.error} />
    </Card>
  );
}

function HistoryPanel({ onLoad }: { onLoad: (q: string) => void }) {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["history"], queryFn: () => api.get<HistoryItem[]>("/api/query/history?limit=50"), refetchInterval: 10000 });
  const limpar = useMutation({ mutationFn: () => api.del("/api/query/history"), onSuccess: () => qc.invalidateQueries({ queryKey: ["history"] }) });
  return (
    <Card>
      <div className="flex items-center justify-between">
        <CardTitle>Histórico</CardTitle>
        {data.length > 0 && (
          <Button size="sm" variant="ghost" onClick={() => limpar.mutate()}>
            Limpar
          </Button>
        )}
      </div>
      {data.length === 0 ? (
        <Empty>Nenhuma busca aberta ainda.</Empty>
      ) : (
        <ul className="max-h-64 space-y-1 overflow-auto">
          {data.map((h) => (
            <li key={h.id}>
              <button type="button" className="w-full rounded-md p-1 text-left hover:bg-muted" onClick={() => onLoad(h.query)}>
                <span className="code block text-xs">{h.query}</span>
                <span className="text-xs text-muted-foreground">
                  {h.motor} · {formatDate(h.criado_em)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ScrapingPanel({ query }: { query: string }) {
  const [engines, setEngines] = React.useState<string[]>([...ENGINES]);
  const m = useMutation({
    mutationFn: () => api.post<{ execucoes: ScrapeExecucao[]; erro?: string; erros?: string[] }>("/api/query/scrape", { query, engines }),
  });
  return (
    <div className="space-y-3">
      <EthicsNotice />
      <SearxngStatus />
      <p className="code rounded-md bg-muted p-2">{query || "(monte uma query primeiro)"}</p>
      <EnginePicker value={engines} onChange={setEngines} />
      <SearxngSearchButton queries={[query]} disabled={!query || !engines.length} pending={m.isPending} onClick={() => m.mutate()} />
      <ErrorText error={m.error} />
      {m.data?.erro && <ErrorText error={`${m.data.erro}: ${m.data.erros?.join("; ")}`} />}
      {m.data && <ScrapeExecucoes execucoes={m.data.execucoes} />}
    </div>
  );
}

export default function QueryBuilderPage() {
  const { blocos, set, reset } = useQueryBuilderStore();
  const [modoCru, setModoCru] = React.useState(false);
  const [cru, setCru] = React.useState("");
  const [template, setTemplate] = React.useState<Template | null>(null);
  const payload = useDebounced(toPayload(blocos), 250);
  const cruDeb = useDebounced(cru, 250);

  const compose = useQuery({
    queryKey: ["compose", payload],
    queryFn: () => api.post<ComposeResponse>("/api/query/compose", payload),
    enabled: !modoCru,
  });
  const validate = useQuery({
    queryKey: ["validate", cruDeb],
    queryFn: () => api.post<ValidateResponse>("/api/query/validate", { query: cruDeb }),
    enabled: modoCru && !!cruDeb.trim(),
  });
  const res = modoCru ? validate.data : compose.data;
  const query = res?.query ?? "";

  const upd = <K extends keyof Blocos>(k: K, v: Partial<Blocos[K]> | Blocos[K]) =>
    set((b) => ({ ...b, [k]: typeof v === "object" && !Array.isArray(v) && v !== null ? { ...(b[k] as object), ...v } : v }));

  const carregarTemplate = (t: Template) => {
    setModoCru(false);
    setTemplate(t);
    set(() => ({ ...BLOCOS_VAZIOS, template_id: t.id, valores_template: {} }));
  };

  const builder = (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <div className="flex flex-wrap gap-2">
          <Button variant={modoCru ? "outline" : "default"} size="sm" onClick={() => setModoCru(false)}>
            Construtor por blocos
          </Button>
          <Button variant={modoCru ? "default" : "outline"} size="sm" onClick={() => { setCru(query); setModoCru(true); }}>
            Editar query crua
          </Button>
          <Button variant="ghost" size="sm" onClick={() => { reset(); setTemplate(null); }}>
            <RotateCcw size={14} /> Limpar
          </Button>
        </div>

        {modoCru ? (
          <Field label="Query" htmlFor="cru">
            <Textarea id="cru" rows={4} value={cru} onChange={(e) => setCru(e.target.value)} />
          </Field>
        ) : (
          <>
            {template && blocos.template_id === template.id && (
              <Card>
                <CardTitle>
                  Template: {template.nome} <Badge variant="accent">{template.categoria}</Badge>
                </CardTitle>
                <p className="mb-2 text-sm text-muted-foreground">{template.descricao}</p>
                <p className="code mb-3 text-xs">{template.query}</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {template.placeholders.map((ph) => (
                    <Field key={ph} label={`Substituir “${ph}”`} htmlFor={`ph-${ph}`}>
                      <Input
                        id={`ph-${ph}`}
                        type={/^\d{4}-\d{2}-\d{2}$/.test(ph) ? "date" : "text"}
                        value={blocos.valores_template[ph] ?? ""}
                        onChange={(e) => upd("valores_template", { ...blocos.valores_template, [ph]: e.target.value })}
                      />
                    </Field>
                  ))}
                </div>
                <Button className="mt-2" size="sm" variant="ghost" onClick={() => { setTemplate(null); upd("template_id", null as never); }}>
                  Remover template
                </Button>
              </Card>
            )}
            <Card>
              <CardTitle>Precisão</CardTitle>
              <div className="grid gap-3 md:grid-cols-2">
                <Field label='Frases exatas ("…")' htmlFor="frases">
                  <ListInput id="frases" values={blocos.precisao.frases_exatas} onChange={(v) => upd("precisao", { frases_exatas: v })} placeholder="Polícia Rodoviária Federal" />
                </Field>
                <Field label="Termos (E)" htmlFor="termos">
                  <ListInput id="termos" values={blocos.precisao.termos} onChange={(v) => upd("precisao", { termos: v })} placeholder="PRF" />
                </Field>
                <Field label="Excluir (-termo)" htmlFor="excluir">
                  <ListInput id="excluir" values={blocos.precisao.excluir} onChange={(v) => upd("precisao", { excluir: v })} placeholder="concurso" />
                </Field>
                <div className="md:row-span-2">
                  <Field label="Alternativas agrupadas — ( A OR B )" htmlFor="or-0">
                    <GruposOr grupos={blocos.precisao.grupos_or} onChange={(g) => upd("precisao", { grupos_or: g })} />
                  </Field>
                </div>
                <Field label="Curinga (*)" htmlFor="cur">
                  <Curingas pares={blocos.precisao.curingas} onChange={(p) => upd("precisao", { curingas: p })} />
                </Field>
              </div>
              <div className="mt-3">
                <Localidades onAdd={(t) => upd("extra", (blocos.extra ? `${blocos.extra} ` : "") + t)} />
              </div>
            </Card>
            <Card>
              <CardTitle>Temporal</CardTitle>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="after: (posterior a)" htmlFor="after">
                  <Input id="after" type="date" value={blocos.temporal.after} onChange={(e) => upd("temporal", { after: e.target.value })} />
                </Field>
                <Field label="before: (anterior a)" htmlFor="before">
                  <Input id="before" type="date" value={blocos.temporal.before} onChange={(e) => upd("temporal", { before: e.target.value })} />
                </Field>
              </div>
            </Card>
            <Card>
              <CardTitle>
                X / TweetDeck <Badge variant="accent">Op. Eleições</Badge>
              </CardTitle>
              <p className="mb-3 text-xs text-muted-foreground">
                Operadores do X (strings do boletim). Só funcionam no X/TweetDeck; nos demais motores viram texto.
              </p>
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="since: (a partir de)" htmlFor="since">
                  <Input id="since" type="date" value={blocos.x.since} onChange={(e) => upd("x", { since: e.target.value })} />
                </Field>
                <Field label="until: (até)" htmlFor="until">
                  <Input id="until" type="date" value={blocos.x.until} onChange={(e) => upd("x", { until: e.target.value })} />
                </Field>
                <Field label="from: (autores)" htmlFor="xfrom">
                  <ListInput id="xfrom" values={blocos.x.from} onChange={(v) => upd("x", { from: v })} placeholder="PRFBrasil" />
                </Field>
                <Field label="to: (destinatários)" htmlFor="xto">
                  <ListInput id="xto" values={blocos.x.to} onChange={(v) => upd("x", { to: v })} placeholder="PRFBrasil" />
                </Field>
                <Field label="@menções" htmlFor="xmencoes">
                  <ListInput id="xmencoes" values={blocos.x.mencoes} onChange={(v) => upd("x", { mencoes: v })} placeholder="PRFBrasil" />
                </Field>
                <fieldset className="space-y-1 text-sm">
                  <legend className="mb-1 text-xs font-medium text-muted-foreground">Filtros</legend>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={blocos.x.excluir_retweets} onChange={(e) => upd("x", { excluir_retweets: e.target.checked })} />
                    Excluir retweets (-is:retweet)
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={blocos.x.apenas_respostas} onChange={(e) => upd("x", { apenas_respostas: e.target.checked })} />
                    Apenas respostas (is:reply)
                  </label>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={blocos.x.apenas_verificados} onChange={(e) => upd("x", { apenas_verificados: e.target.checked })} />
                    Apenas verificados (is:verified)
                  </label>
                </fieldset>
                <fieldset className="text-sm">
                  <legend className="mb-1 text-xs font-medium text-muted-foreground">has: (conteúdo)</legend>
                  <div className="flex flex-wrap gap-3">
                    {["media", "images", "videos", "links"].map((h) => (
                      <label key={h} className="flex items-center gap-1">
                        <input
                          type="checkbox"
                          checked={blocos.x.has.includes(h)}
                          onChange={(e) => upd("x", { has: e.target.checked ? [...blocos.x.has, h] : blocos.x.has.filter((v) => v !== h) })}
                        />
                        {h}
                      </label>
                    ))}
                  </div>
                </fieldset>
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  <Field label="lang:" htmlFor="xlang">
                    <Input id="xlang" value={blocos.x.lang} onChange={(e) => upd("x", { lang: e.target.value })} placeholder="pt" maxLength={8} />
                  </Field>
                  <Field label="min_faves:" htmlFor="xfaves">
                    <Input id="xfaves" type="number" min={0} value={blocos.x.min_faves} onChange={(e) => upd("x", { min_faves: e.target.value })} />
                  </Field>
                  <Field label="min_retweets:" htmlFor="xrts">
                    <Input id="xrts" type="number" min={0} value={blocos.x.min_retweets} onChange={(e) => upd("x", { min_retweets: e.target.value })} />
                  </Field>
                  <Field label="min_replies:" htmlFor="xreplies">
                    <Input id="xreplies" type="number" min={0} value={blocos.x.min_replies} onChange={(e) => upd("x", { min_replies: e.target.value })} />
                  </Field>
                </div>
              </div>
            </Card>
            <Card>
              <CardTitle>Escopo</CardTitle>
              <div className="grid gap-3 md:grid-cols-2">
                <Field label="site: (agrupados com OR)" htmlFor="sites" hint="Atalho redes sociais do PDF abaixo">
                  <ListInput id="sites" values={blocos.escopo.sites} onChange={(v) => upd("escopo", { sites: v })} placeholder="uol.com.br" />
                  <Button size="sm" variant="ghost" className="mt-1" onClick={() => upd("escopo", { sites: ["facebook.com", "instagram.com", "x.com", "tiktok.com"] })}>
                    + Facebook/Instagram/X/TikTok
                  </Button>
                </Field>
                <Field label="-site: (excluir domínio)" htmlFor="xsites">
                  <ListInput id="xsites" values={blocos.escopo.excluir_sites} onChange={(v) => upd("escopo", { excluir_sites: v })} placeholder="gov.br" />
                </Field>
                <Field label="filetype:" htmlFor="ft">
                  <Select id="ft" value={blocos.escopo.filetype} onChange={(e) => upd("escopo", { filetype: e.target.value })}>
                    <option value="">—</option>
                    {["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "csv", "odt"].map((f) => (
                      <option key={f}>{f}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="inurl:" htmlFor="inurl">
                  <ListInput id="inurl" values={blocos.escopo.inurl} onChange={(v) => upd("escopo", { inurl: v })} placeholder="PRF" />
                </Field>
                <Field label="intitle:" htmlFor="intitle">
                  <ListInput id="intitle" values={blocos.escopo.intitle} onChange={(v) => upd("escopo", { intitle: v })} placeholder="Policia Rodoviária Federal" />
                </Field>
                <Field label="intext:" htmlFor="intext">
                  <ListInput id="intext" values={blocos.escopo.intext} onChange={(v) => upd("escopo", { intext: v })} placeholder="Termo" />
                </Field>
              </div>
              <div className="mt-3">
                <Field label="Trecho livre adicional" htmlFor="extra">
                  <Input id="extra" value={blocos.extra} onChange={(e) => upd("extra", e.target.value)} />
                </Field>
              </div>
            </Card>
          </>
        )}
      </div>

      <div className="space-y-4">
        <Card className="sticky top-4">
          <CardTitle>Preview ao vivo</CardTitle>
          <output aria-live="polite" className="code block min-h-[3rem] rounded-md bg-muted p-2">
            {query || "—"}
          </output>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="outline" disabled={!query} onClick={() => void navigator.clipboard.writeText(query)}>
              <Copy size={14} /> Copiar
            </Button>
          </div>
          {res && (
            <div className="mt-3 space-y-3">
              <ProblemList erros={res.erros} avisos={res.avisos} />
              {query && <DeeplinkButtons deeplinks={res.deeplinks} query={query} compatibilidade={res.compatibilidade} />}
              {query && res.deeplinks_extra && Object.keys(res.deeplinks_extra).length > 0 && (
                <div>
                  <p className="mb-1 text-xs text-muted-foreground">Redes e notícias</p>
                  <DeeplinkButtons deeplinks={res.deeplinks_extra} query={query} compatibilidade={res.compatibilidade_extra} />
                </div>
              )}
            </div>
          )}
          <ErrorText error={compose.error ?? validate.error} />
        </Card>
        <TemplatesPanel onLoad={carregarTemplate} query={query} />
        <HistoryPanel onLoad={(q) => { setCru(q); setModoCru(true); }} />
      </div>
    </div>
  );

  return (
    <>
      <PageHeader title="Query Builder" description="Operadores de precisão, temporais e de escopo do documento O51NT, mais os operadores do X/TweetDeck do boletim Op. Eleições 2026." />
      <ModeTabs label="Modo do Query Builder" deeplinks={builder} scraping={<ScrapingPanel query={query} />} />
    </>
  );
}
