import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronLeft, ChevronRight, Copy, Download, ExternalLink, Printer, Search, Trash2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { DeeplinkButtons, ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, TabPanel, Tabs, Textarea } from "@/components/ui";
import { api, qs, type Boletim, type BoletimItem, type Ferramenta, type Monitor, type Perfil, type PerfilDeeplinks, type Template } from "@/lib/api";
import { dataBR, downloadBlob, hojeISO, openExternal, somarDias } from "@/lib/utils";

const SECOES = [
  { id: "noticia", titulo: "Notícias relevantes" },
  { id: "fake_news", titulo: "Fake news" },
  { id: "manifestacao", titulo: "Manifestações identificadas" },
  { id: "imagem_institucional", titulo: "Imagem institucional" },
  { id: "outro", titulo: "Outras informações" },
] as const;
const REDES = ["x", "instagram", "facebook", "tiktok", "youtube", "telegram", "mastodon", "site", "outro"];
const CATEGORIAS = ["candidato", "partido", "institucional", "midia", "coletivo", "outro"];

async function abrirFerramenta(tool: string, q: string) {
  const r = await api.get<{ url: string }>(`/api/tools/deeplink${qs({ tool, q })}`);
  openExternal(r.url);
}

/** Atalhos de apoio por seção: reusam o hub de ferramentas e os templates do boletim. */
function Apoio({ secao }: { secao: string }) {
  const [termo, setTermo] = React.useState("");
  const { data: tools = [] } = useQuery({ queryKey: ["tools"], queryFn: () => api.get<Ferramenta[]>("/api/tools") });
  const { data: templates = [] } = useQuery({ queryKey: ["templates"], queryFn: () => api.get<Template[]>("/api/query/templates") });
  const checagem = tools.filter((t) => t.categoria === "Checagem de fatos");
  const strings = templates.filter((t) => t.categoria === "x_tweetdeck");
  if (secao === "noticia") {
    return (
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <Input aria-label="Termo para buscar notícias" placeholder="buscar notícias (ex.: PRF eleições)" className="w-64" value={termo} onChange={(e) => setTermo(e.target.value)} />
        <Button size="sm" variant="outline" disabled={!termo.trim()} onClick={() => void abrirFerramenta("google_news", termo)}><ExternalLink size={14} /> Google Notícias</Button>
        <Button size="sm" variant="outline" disabled={!termo.trim()} onClick={() => void abrirFerramenta("x_search", termo)}><ExternalLink size={14} /> X (recentes)</Button>
      </div>
    );
  }
  if (secao === "fake_news") {
    return (
      <div className="mt-2 space-y-2 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Input aria-label="Alegação para checar" placeholder="alegação a checar" className="w-64" value={termo} onChange={(e) => setTermo(e.target.value)} />
          <Button size="sm" variant="outline" disabled={!termo.trim()} onClick={() => void abrirFerramenta("google_factcheck", termo)}><ExternalLink size={14} /> Fact Check Explorer</Button>
        </div>
        <div className="flex flex-wrap gap-1">
          {checagem.map((t) => (
            <Button key={t.id} size="sm" variant="ghost" onClick={() => void abrirFerramenta(t.id, termo)}>{t.nome}</Button>
          ))}
        </div>
      </div>
    );
  }
  if (secao === "manifestacao" || secao === "imagem_institucional") {
    const alvo = secao === "manifestacao" ? strings.filter((t) => t.nome.includes("Mobilidade")) : strings.filter((t) => !t.nome.includes("Mobilidade"));
    return (
      <div className="mt-2 space-y-1 text-sm">
        {secao === "manifestacao" && (
          <p className="text-xs text-muted-foreground">
            Veja também a <Link to="/agenda" className="text-primary underline">Agenda</Link> (compromissos com impacto em rodovia federal).
          </p>
        )}
        {alvo.map((t) => (
          <div key={t.id} className="flex flex-wrap items-center gap-2">
            <span className="code max-w-xl truncate text-xs" title={t.query}>{t.nome}</span>
            <Button size="sm" variant="outline" onClick={() => void abrirFerramenta(t.nome.startsWith("TikTok") ? "tiktok_search" : "x_search", t.query)}>
              <ExternalLink size={14} /> {t.nome.startsWith("TikTok") ? "TikTok" : "X (recentes)"}
            </Button>
          </div>
        ))}
      </div>
    );
  }
  return null;
}

function ItemLinha({ i }: { i: BoletimItem }) {
  const qc = useQueryClient();
  const del = useMutation({ mutationFn: () => api.del(`/api/boletim/itens/${i.id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["boletim"] }) });
  return (
    <li className="flex items-start gap-2 text-sm">
      <div className="flex-1">
        {i.url ? <a href={i.url} target="_blank" rel="noopener noreferrer" className="font-medium text-primary underline">{i.titulo}</a> : <span className="font-medium">{i.titulo}</span>}
        {i.fonte && <Badge className="ml-1">{i.fonte}</Badge>}
        {i.evidence_id && (
          <a className="ml-1 text-xs text-accent underline" href={`/api/evidence/${i.evidence_id}/download?inline=true`} target="_blank" rel="noopener noreferrer">evidência #{i.evidence_id}</a>
        )}
        {i.resumo && <p className="text-muted-foreground">{i.resumo}</p>}
      </div>
      <Button size="icon" variant="ghost" aria-label={`Excluir item ${i.titulo}`} onClick={() => del.mutate()}><Trash2 size={14} /></Button>
    </li>
  );
}

function NovoItem({ data }: { data: string }) {
  const qc = useQueryClient();
  const [f, setF] = React.useState({ secao: "noticia", titulo: "", url: "", fonte: "", resumo: "", evidence_id: "" });
  const m = useMutation({
    mutationFn: () => api.post<BoletimItem>("/api/boletim/itens", { ...f, data, evidence_id: f.evidence_id ? Number(f.evidence_id) : null }),
    onSuccess: () => { setF({ ...f, titulo: "", url: "", resumo: "", evidence_id: "" }); void qc.invalidateQueries({ queryKey: ["boletim"] }); },
  });
  return (
    <Card>
      <CardTitle>Adicionar ao boletim de {dataBR(data)}</CardTitle>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label="Seção" htmlFor="bi-secao">
          <Select id="bi-secao" value={f.secao} onChange={(e) => setF({ ...f, secao: e.target.value })}>{SECOES.map((s) => <option key={s.id} value={s.id}>{s.titulo}</option>)}</Select>
        </Field>
        <Field label="Título / manchete" htmlFor="bi-titulo"><Input id="bi-titulo" required value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} /></Field>
        <Field label="URL" htmlFor="bi-url"><Input id="bi-url" type="url" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://…" /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Fonte / veículo" htmlFor="bi-fonte"><Input id="bi-fonte" value={f.fonte} onChange={(e) => setF({ ...f, fonte: e.target.value })} placeholder="AFP, g1, Metrópoles…" /></Field>
          <Field label="Nº da evidência (opcional)" htmlFor="bi-ev" hint="Faça o upload do print em Evidências e informe o número aqui."><Input id="bi-ev" type="number" min={1} value={f.evidence_id} onChange={(e) => setF({ ...f, evidence_id: e.target.value })} /></Field>
        </div>
        <Field label="Resumo / observação" htmlFor="bi-resumo"><Textarea id="bi-resumo" rows={2} value={f.resumo} onChange={(e) => setF({ ...f, resumo: e.target.value })} /></Field>
        <Button type="submit" disabled={m.isPending}>Adicionar item</Button>
        <ErrorText error={m.error} />
      </form>
    </Card>
  );
}

function BoletimDia({ data, setData }: { data: string; setData: (d: string) => void }) {
  const { data: b, error } = useQuery({ queryKey: ["boletim", data], queryFn: () => api.get<Boletim>(`/api/boletim/${data}`) });
  const exportar = async (formato: "md" | "json") => downloadBlob(await api.blob("GET", `/api/boletim/${data}/export?formato=${formato}`), `boletim_${data}.${formato}`);
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <Button size="icon" variant="outline" aria-label="Dia anterior" onClick={() => setData(somarDias(data, -1))}><ChevronLeft size={16} /></Button>
        <Field label="Dia do boletim" htmlFor="bo-dia"><Input id="bo-dia" type="date" value={data} onChange={(e) => e.target.value && setData(e.target.value)} /></Field>
        <Button size="icon" variant="outline" aria-label="Próximo dia" onClick={() => setData(somarDias(data, 1))}><ChevronRight size={16} /></Button>
        <Button size="sm" variant="ghost" onClick={() => setData(hojeISO())}>Hoje</Button>
        <span className="flex-1" />
        <Button size="sm" variant="outline" onClick={() => void exportar("md")}><Download size={14} /> Markdown</Button>
        <Button size="sm" variant="outline" onClick={() => void exportar("json")}><Download size={14} /> JSON</Button>
        <Button size="sm" onClick={() => openExternal(`/api/boletim/${data}/export?formato=html`)}><Printer size={14} /> Abrir para imprimir (PDF)</Button>
      </div>
      <ErrorText error={error} />
      {b && (
        <div className="grid gap-4 lg:grid-cols-5">
          <div className="space-y-4 lg:col-span-3">
            <h2 className="text-lg font-bold">{b.titulo}</h2>
            <Card>
              <CardTitle>Hashtags</CardTitle>
              {b.hashtags.length === 0 ? <Empty>Nenhuma hashtag com contagem. Colete na aba <Link className="text-primary underline" to="/hashtags">Hashtags</Link>.</Empty> : (
                <div className="flex flex-wrap gap-1">{b.hashtags.map((h) => <Badge key={h.tag} variant="accent" title={`${h.contagem} (${h.fonte})`}>{h.tag}</Badge>)}</div>
              )}
            </Card>
            {SECOES.map((s) => {
              const itens = b.secoes[s.id] ?? [];
              return (
                <Card key={s.id}>
                  <CardTitle>{s.titulo} <Badge>{itens.length}</Badge></CardTitle>
                  {itens.length === 0 ? <p className="text-sm text-muted-foreground">—</p> : <ul className="space-y-2">{itens.map((i) => <ItemLinha key={i.id} i={i} />)}</ul>}
                  <Apoio secao={s.id} />
                </Card>
              );
            })}
            <Card>
              <CardTitle>Agenda dos candidatos <Badge>{b.agenda.total}</Badge> {b.agenda.com_impacto_rodovia > 0 && <Badge variant="warning">{b.agenda.com_impacto_rodovia} com impacto em rodovia</Badge>}</CardTitle>
              {b.agenda.total === 0 ? <Empty>Sem compromissos cadastrados. Cadastre na <Link className="text-primary underline" to="/agenda">Agenda</Link>.</Empty> : (
                Object.entries(b.agenda.por_candidato).map(([cand, evs]) => (
                  <div key={cand} className="mb-2 text-sm">
                    <strong>{cand}</strong>
                    <ul className="ml-4 list-disc">
                      {evs.map((e) => <li key={e.id}>{e.hora_inicio ?? "—"} — {e.titulo} — {e.cidade}{e.uf && `/${e.uf}`} {e.impacto_rodovia && <Badge variant="warning">impacto em rodovia</Badge>}</li>)}
                    </ul>
                  </div>
                ))
              )}
            </Card>
            <Card>
              <CardTitle>Links de grupos identificados (7 dias) <Badge>{b.convites.length}</Badge></CardTitle>
              {b.convites.length === 0 ? <p className="text-sm text-muted-foreground">— (use a aba Convites)</p> : (
                <ul className="code space-y-1 text-xs">{b.convites.map((c) => <li key={c.url}>{c.plataforma} — {c.url} <span className="text-muted-foreground">({c.termo}, {c.last_seen})</span></li>)}</ul>
              )}
            </Card>
            <Card>
              <CardTitle>Perfis para acompanhar <Badge>{b.perfis.length}</Badge></CardTitle>
              {b.perfis.length === 0 ? <p className="text-sm text-muted-foreground">— (cadastre na subaba Perfis vigiados)</p> : (
                <ul className="space-y-1 text-sm">{b.perfis.map((p) => <li key={p.id}>{p.rotulo && <strong>{p.rotulo} — </strong>}<a className="text-primary underline" href={p.url} target="_blank" rel="noopener noreferrer">{p.url}</a> <Badge>{p.rede}</Badge></li>)}</ul>
              )}
            </Card>
          </div>
          <div className="space-y-4 lg:col-span-2">
            <NovoItem data={data} />
            <Card>
              <div className="flex items-center justify-between">
                <CardTitle className="mb-0">Prévia (Markdown)</CardTitle>
                <Button size="sm" variant="ghost" onClick={() => void navigator.clipboard.writeText(b.markdown)}><Copy size={14} /> Copiar</Button>
              </div>
              <pre className="code mt-2 max-h-[32rem] overflow-auto rounded bg-muted p-2 text-xs">{b.markdown}</pre>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function PerfilLinha({ p }: { p: Perfil }) {
  const qc = useQueryClient();
  const [ver, setVer] = React.useState(false);
  const inval = () => void qc.invalidateQueries({ queryKey: ["perfis"] });
  const { data: dl } = useQuery({ queryKey: ["perfil-dl", p.id], queryFn: () => api.get<PerfilDeeplinks>(`/api/perfis/${p.id}/deeplinks`), enabled: ver });
  const del = useMutation({ mutationFn: () => api.del(`/api/perfis/${p.id}`), onSuccess: inval });
  const mon = useMutation({ mutationFn: () => api.post<Monitor>(`/api/perfis/${p.id}/monitor`, {}), onSuccess: inval });
  const toggle = useMutation({ mutationFn: () => api.patch(`/api/perfis/${p.id}`, { ativo: !p.ativo }), onSuccess: inval });
  return (
    <li className="rounded-md border border-border p-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Badge>{p.rede}</Badge>
        <strong>{p.rotulo || p.handle}</strong>
        <a className="code text-xs text-primary underline" href={p.url} target="_blank" rel="noopener noreferrer">{p.url}</a>
        <Badge variant="muted">{p.categoria}</Badge>
        <Badge variant={p.ativo ? "success" : "muted"}>{p.ativo ? "ativo" : "inativo"}</Badge>
        {p.monitor_id && <Badge variant="accent">monitor #{p.monitor_id}</Badge>}
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        <Button size="sm" variant="outline" onClick={() => setVer((v) => !v)} aria-expanded={ver}><Search size={14} /> Menções</Button>
        <Button size="sm" variant="outline" disabled={!!p.monitor_id || mon.isPending} onClick={() => mon.mutate()}><Bell size={14} /> Monitorar</Button>
        <Button size="sm" variant="ghost" onClick={() => toggle.mutate()}>{p.ativo ? "Desativar" : "Ativar"}</Button>
        <Button size="icon" variant="ghost" aria-label={`Excluir perfil ${p.handle}`} onClick={() => del.mutate()}><Trash2 size={14} /></Button>
      </div>
      <ErrorText error={del.error ?? mon.error} />
      {ver && dl && (
        <div className="mt-2 space-y-1 rounded bg-muted p-2">
          <p className="code text-xs">{dl.query_mencoes_x}</p>
          <DeeplinkButtons deeplinks={dl.deeplinks_x} query={dl.query_mencoes_x} origem="perfil-x" />
          <p className="code text-xs">{dl.query_mencoes}</p>
          <DeeplinkButtons deeplinks={dl.deeplinks} query={dl.query_mencoes} origem="perfil" />
        </div>
      )}
    </li>
  );
}

function Perfis() {
  const qc = useQueryClient();
  const { data: perfis = [], error } = useQuery({ queryKey: ["perfis"], queryFn: () => api.get<Perfil[]>("/api/perfis") });
  const [f, setF] = React.useState({ rede: "x", handle: "", rotulo: "", categoria: "outro", notas: "" });
  const criar = useMutation({
    mutationFn: () => api.post<Perfil>("/api/perfis", f),
    onSuccess: () => { setF({ ...f, handle: "", rotulo: "", notas: "" }); void qc.invalidateQueries({ queryKey: ["perfis"] }); },
  });
  const exportar = async (formato: "csv" | "json") => downloadBlob(await api.blob("GET", `/api/perfis/export?formato=${formato}`), `perfis.${formato}`);
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="lg:col-span-3">
        <Card>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="mb-0">Perfis vigiados ({perfis.length})</CardTitle>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => void exportar("csv")}><Download size={14} /> CSV</Button>
              <Button size="sm" variant="outline" onClick={() => void exportar("json")}><Download size={14} /> JSON</Button>
            </div>
          </div>
          <ErrorText error={error} />
          {perfis.length === 0 ? <Empty>Nenhum perfil cadastrado.</Empty> : <ul className="space-y-2">{perfis.map((p) => <PerfilLinha key={p.id} p={p} />)}</ul>}
        </Card>
      </div>
      <div className="lg:col-span-2">
        <Card>
          <CardTitle>Novo perfil</CardTitle>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); criar.mutate(); }}>
            <Field label="Rede" htmlFor="pf-rede"><Select id="pf-rede" value={f.rede} onChange={(e) => setF({ ...f, rede: e.target.value })}>{REDES.map((r) => <option key={r}>{r}</option>)}</Select></Field>
            <Field label="Usuário ou URL do perfil" htmlFor="pf-handle" hint="Aceita @usuario, usuario ou a URL completa."><Input id="pf-handle" required value={f.handle} onChange={(e) => setF({ ...f, handle: e.target.value })} placeholder="@PRFBrasil" /></Field>
            <Field label="Rótulo" htmlFor="pf-rotulo"><Input id="pf-rotulo" value={f.rotulo} onChange={(e) => setF({ ...f, rotulo: e.target.value })} placeholder="PRF Brasil" /></Field>
            <Field label="Categoria" htmlFor="pf-cat"><Select id="pf-cat" value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })}>{CATEGORIAS.map((c) => <option key={c}>{c}</option>)}</Select></Field>
            <Field label="Notas" htmlFor="pf-notas"><Textarea id="pf-notas" rows={2} value={f.notas} onChange={(e) => setF({ ...f, notas: e.target.value })} /></Field>
            <Button type="submit" disabled={criar.isPending}>Cadastrar perfil</Button>
            <ErrorText error={criar.error} />
          </form>
        </Card>
        <div className="mt-4">
          <Alert variant="info">Só perfis públicos. O app não faz login nem coleta dados pessoais além do identificador público do perfil (LGPD).</Alert>
        </div>
      </div>
    </div>
  );
}

export default function BoletimPage() {
  const [tab, setTab] = React.useState("dia");
  const [data, setData] = React.useState(hojeISO());
  return (
    <>
      <PageHeader title="Boletim diário" description="Consolida notícias, fake news, manifestações, imagem institucional, agenda, grupos e perfis no formato do boletim Op. Eleições 2026." />
      <Tabs label="Boletim" value={tab} onChange={setTab} tabs={[{ id: "dia", label: "Boletim do dia" }, { id: "perfis", label: "Perfis vigiados" }]} />
      <TabPanel id="dia" active={tab === "dia"}><BoletimDia data={data} setData={setData} /></TabPanel>
      <TabPanel id="perfis" active={tab === "perfis"}><Perfis /></TabPanel>
    </>
  );
}
