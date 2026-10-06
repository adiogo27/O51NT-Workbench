import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import * as React from "react";
import { DeeplinkButtons, EthicsNotice, ErrorText, ModeTabs, useDebounced } from "@/components/shared";
import { Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader } from "@/components/ui";
import { api, qs, type Hashtag, type Snapshot } from "@/lib/api";
import { formatDate, openExternal } from "@/lib/utils";

/** Gráfico SVG próprio (sem dependência): barras horizontais do top N. */
function BarChart({ itens }: { itens: Hashtag[] }) {
  const top = itens.slice(0, 15);
  const max = Math.max(1, ...top.map((h) => h.contagem));
  const rowH = 22;
  if (!top.length) return <Empty>Sem dados para o gráfico.</Empty>;
  return (
    <svg role="img" aria-label="Top hashtags por contagem" viewBox={`0 0 600 ${top.length * rowH}`} className="w-full">
      {top.map((h, i) => {
        const w = (h.contagem / max) * 380;
        return (
          <g key={h.id} transform={`translate(0 ${i * rowH})`}>
            <text x={0} y={15} fontSize={12} fill="var(--color-foreground)">{h.tag.slice(0, 24)}</text>
            <rect x={180} y={4} width={Math.max(w, 1)} height={14} rx={3} fill="var(--color-primary)" />
            <text x={186 + w} y={15} fontSize={11} fill="var(--color-muted-foreground)">{h.contagem}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Sparkline({ hid }: { hid: number }) {
  const { data = [] } = useQuery({ queryKey: ["series", hid], queryFn: () => api.get<Snapshot[]>(`/api/hashtags/${hid}/series`) });
  if (data.length < 2) return <span className="text-xs text-muted-foreground">{data.length} coleta(s)</span>;
  const max = Math.max(1, ...data.map((d) => d.contagem));
  const pts = data.map((d, i) => `${(i / (data.length - 1)) * 100},${28 - (d.contagem / max) * 26}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" className="h-6 w-24" role="img" aria-label={`Série: ${data.map((d) => d.contagem).join(", ")}`}>
      <polyline points={pts} fill="none" stroke="var(--color-accent)" strokeWidth={2} />
    </svg>
  );
}

function DeeplinksPanel({ tag }: { tag: string }) {
  const t = useDebounced(tag);
  const { data } = useQuery({
    queryKey: ["hq", t],
    queryFn: () => api.get<{ query: string; deeplinks: Record<string, string> }>(`/api/hashtags/queries${qs({ tag: t })}`),
    enabled: t.trim().length >= 2,
  });
  return (
    <div className="space-y-3">
      {data ? (
        <Card>
          <CardTitle>Acompanhamento por Hashtags (PDF)</CardTitle>
          <p className="code mb-3 rounded-md bg-muted p-2 text-xs">{data.query}</p>
          <DeeplinksPanelButtons q={data.query} links={data.deeplinks} />
        </Card>
      ) : (
        <Empty>Digite uma hashtag.</Empty>
      )}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={() => openExternal("https://trends24.in/brazil/")}>trends24 — Brasil</Button>
        <Button variant="outline" size="sm" onClick={() => openExternal("https://onemilliontweetmap.com/")}>OneMillionTweetMap</Button>
        <Button variant="outline" size="sm" onClick={() => openExternal("https://commentpicker.com/")}>Comment Picker</Button>
      </div>
    </div>
  );
}

function DeeplinksPanelButtons({ q, links }: { q: string; links: Record<string, string> }) {
  return <DeeplinkButtons deeplinks={links} query={q} origem="hashtags" />;
}

function ScrapingPanel({ tag }: { tag: string }) {
  const qc = useQueryClient();
  const [cron, setCron] = React.useState("0 */3 * * *");
  const [fontes, setFontes] = React.useState(["trends24"]);
  const inval = () => void qc.invalidateQueries({ queryKey: ["hashtags"] });
  const coletar = useMutation({
    mutationFn: () => api.post<{ ocorrencias_alvo: number; variantes_encontradas: string[]; fontes: Record<string, Record<string, unknown>> }>("/api/hashtags/collect", { tag, fontes }),
    onSuccess: inval,
  });
  const track = useMutation({ mutationFn: () => api.post<Hashtag>("/api/hashtags/track", { tag, cron }), onSuccess: inval });
  return (
    <div className="space-y-3">
      <EthicsNotice />
      <fieldset className="flex gap-4 text-sm">
        <legend className="mb-1 text-xs text-muted-foreground">Fontes públicas (PDF)</legend>
        <label className="flex items-center gap-1">
          <input type="checkbox" checked={fontes.includes("trends24")} onChange={(e) => setFontes(e.target.checked ? ["trends24"] : [])} /> trends24
        </label>
        <label className="flex items-center gap-1 text-muted-foreground" title="O HTML público não expõe hashtags (tweets carregam dinamicamente no mapa).">
          <input type="checkbox" disabled checked={false} onChange={() => undefined} /> onemilliontweetmap (encerrado)
        </label>
      </fieldset>
      <div className="flex flex-wrap items-end gap-2">
        <Button disabled={tag.trim().length < 2 || !fontes.length || coletar.isPending} onClick={() => coletar.mutate()}>
          {coletar.isPending ? "Coletando…" : "Coletar agora"}
        </Button>
        <div className="w-40">
          <Field label="Cron do rastreio" htmlFor="hcron"><Input id="hcron" className="font-mono" value={cron} onChange={(e) => setCron(e.target.value)} /></Field>
        </div>
        <Button variant="outline" disabled={tag.trim().length < 2 || track.isPending} onClick={() => track.mutate()}>Rastrear periodicamente</Button>
      </div>
      <ErrorText error={coletar.error ?? track.error} />
      {track.data && <p className="text-sm">Monitor #{track.data.monitor_id} criado (veja em Monitores).</p>}
      {coletar.data && (
        <Card>
          <p className="text-sm">Ocorrências de <strong>{tag}</strong> (ignorando acentos e caixa): {coletar.data.ocorrencias_alvo}</p>
          {coletar.data.variantes_encontradas.length > 0 && (
            <p className="mt-1 text-sm">
              Variantes encontradas:{" "}
              {coletar.data.variantes_encontradas.map((v) => <Badge key={v} variant="accent" className="mr-1">{v}</Badge>)}
            </p>
          )}
          <pre className="code mt-2 max-h-60 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(coletar.data.fontes, null, 2)}</pre>
        </Card>
      )}
    </div>
  );
}

export default function HashtagsPage() {
  const qc = useQueryClient();
  const [tag, setTag] = React.useState("");
  const { data = [], error } = useQuery({ queryKey: ["hashtags"], queryFn: () => api.get<Hashtag[]>("/api/hashtags") });
  const inval = () => void qc.invalidateQueries({ queryKey: ["hashtags"] });
  // variantes = mesmas chaves normalizadas (sem acento/caixa); agrupado no cliente para evitar N requisições
  const porChave = React.useMemo(() => {
    const m = new Map<string, Hashtag[]>();
    data.forEach((h) => m.set(h.chave_normalizada, [...(m.get(h.chave_normalizada) ?? []), h]));
    return m;
  }, [data]);
  const add = useMutation({ mutationFn: () => api.post("/api/hashtags", { tag }), onSuccess: inval });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/hashtags/${id}`), onSuccess: inval });
  return (
    <>
      <PageHeader title="Hashtags" description="Identificar e acompanhar hashtags marcadas em comentários/redes sociais." />
      <div className="mb-4 flex max-w-lg items-end gap-2">
        <div className="flex-1"><Field label="Hashtag" htmlFor="tag"><Input id="tag" value={tag} onChange={(e) => setTag(e.target.value)} placeholder="#NomeHashTag" /></Field></div>
        <Button variant="outline" disabled={tag.trim().length < 2} onClick={() => add.mutate()}>Cadastrar manualmente</Button>
      </div>
      <ErrorText error={error ?? add.error ?? del.error} />
      <ModeTabs label="Modo de hashtags" deeplinks={<DeeplinksPanel tag={tag} />} scraping={<ScrapingPanel tag={tag} />} />
      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Top hashtags</CardTitle>
          <BarChart itens={data} />
        </Card>
        <Card>
          <CardTitle>Tabela ({data.length})</CardTitle>
          {data.length === 0 ? (
            <Empty>Nenhuma hashtag.</Empty>
          ) : (
            <div className="max-h-[28rem] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted-foreground"><tr><th className="p-1">Tag</th><th className="p-1">Rede</th><th className="p-1">Contagem</th><th className="p-1">Série</th><th className="p-1">Última</th><th className="p-1"><span className="sr-only">Ações</span></th></tr></thead>
                <tbody>
                  {data.map((h) => (
                    <tr key={h.id} className="border-t border-border">
                      <td className="p-1">
                        <button type="button" className="text-primary underline" onClick={() => setTag(h.tag)}>{h.tag}</button>
                        {h.monitor_id && <Badge variant="accent" className="ml-1">rastreada</Badge>}
                        {(porChave.get(h.chave_normalizada) ?? []).filter((v) => v.id !== h.id).length > 0 && (
                          <span className="ml-1 inline-flex flex-wrap gap-1" aria-label={`Variantes de ${h.tag}`}>
                            {(porChave.get(h.chave_normalizada) ?? []).filter((v) => v.id !== h.id).map((v) => (
                              <Badge key={v.id} title={`variante (${v.contagem})`}>{v.tag}</Badge>
                            ))}
                          </span>
                        )}
                      </td>
                      <td className="p-1">{h.rede}</td>
                      <td className="p-1">{h.contagem}</td>
                      <td className="p-1"><Sparkline hid={h.id} /></td>
                      <td className="p-1 text-xs">{formatDate(h.ultima_vez)} <span className="text-muted-foreground">({h.fonte})</span></td>
                      <td className="p-1"><Button size="icon" variant="ghost" aria-label={`Excluir ${h.tag}`} onClick={() => del.mutate(h.id)}><Trash2 size={14} /></Button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
