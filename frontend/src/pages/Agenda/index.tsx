import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, ChevronLeft, ChevronRight, Download, Pencil, Search, Trash2, TriangleAlert } from "lucide-react";
import * as React from "react";
import { DeeplinkButtons, ErrorText, ListInput, useDebounced } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";
import { api, qs, type AgendaDia, type AgendaEvento, type AgendaQueries, type Monitor } from "@/lib/api";
import { downloadBlob, hojeISO, openExternal, somarDias } from "@/lib/utils";

const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");
const TIPOS = ["caminhada", "carreata", "motociata", "comicio", "ato", "debate", "entrevista", "reuniao", "outro"];
const STATUS = ["previsto", "confirmado", "cancelado", "realizado"];
const CARGOS = ["presidente", "governador", "senador", "deputado", "outro"];

interface FormState {
  candidato: string;
  partido: string;
  cargo: string;
  titulo: string;
  tipo: string;
  data: string;
  hora_inicio: string;
  hora_fim: string;
  cidade: string;
  uf: string;
  local: string;
  rodovias: string[];
  impacto_rodovia: boolean;
  descricao: string;
  fonte_url: string;
  status: string;
}

const formVazio = (data: string): FormState => ({
  candidato: "",
  partido: "",
  cargo: "presidente",
  titulo: "",
  tipo: "outro",
  data,
  hora_inicio: "",
  hora_fim: "",
  cidade: "",
  uf: "",
  local: "",
  rodovias: [],
  impacto_rodovia: false,
  descricao: "",
  fonte_url: "",
  status: "previsto",
});

const deEvento = (e: AgendaEvento): FormState => ({
  candidato: e.candidato,
  partido: e.partido,
  cargo: e.cargo,
  titulo: e.titulo,
  tipo: e.tipo,
  data: e.data,
  hora_inicio: e.hora_inicio ?? "",
  hora_fim: e.hora_fim ?? "",
  cidade: e.cidade,
  uf: e.uf,
  local: e.local,
  rodovias: e.rodovias,
  impacto_rodovia: e.impacto_rodovia,
  descricao: e.descricao,
  fonte_url: e.fonte_url ?? "",
  status: e.status,
});

function RodoviasInput({ values, onChange }: { values: string[]; onChange: (v: string[]) => void }) {
  const [q, setQ] = React.useState("");
  const dq = useDebounced(q);
  const { data } = useQuery({
    queryKey: ["locations-rodovia", dq],
    queryFn: () => api.get<{ nome: string; uf: string }[]>(`/api/locations${qs({ q: dq, tipo: "rodovia" })}`),
    enabled: dq.length >= 2,
  });
  return (
    <div>
      <ListInput id="rodovias" values={values} onChange={onChange} placeholder="BR-116" />
      <div className="mt-1 flex gap-2">
        <Input aria-label="Buscar rodovia na base DNIT" placeholder="buscar na base DNIT (ex.: 116, SC)" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {!!data?.length && (
        <ul className="mt-1 flex flex-wrap gap-1">
          {data.slice(0, 10).map((l) => (
            <li key={l.nome}>
              <button type="button" className="rounded-sm border border-border px-2 py-0.5 text-xs hover:bg-muted" onClick={() => { if (!values.includes(l.nome)) onChange([...values, l.nome]); setQ(""); }}>
                {l.nome} <span className="text-muted-foreground">({l.uf.split(",").slice(0, 4).join(",")}{l.uf.split(",").length > 4 ? "…" : ""})</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EventoForm({ inicial, editandoId, onSalvo, onCancelar }: { inicial: FormState; editandoId: number | null; onSalvo: () => void; onCancelar: () => void }) {
  const [f, setF] = React.useState<FormState>(inicial);
  React.useEffect(() => setF(inicial), [inicial]);
  const m = useMutation({
    mutationFn: () => {
      const body = {
        ...f,
        hora_inicio: f.hora_inicio || null,
        hora_fim: f.hora_fim || null,
        fonte_url: f.fonte_url || null,
      };
      return editandoId ? api.patch<AgendaEvento>(`/api/agenda/${editandoId}`, body) : api.post<AgendaEvento>("/api/agenda", body);
    },
    onSuccess: onSalvo,
  });
  const set = (k: keyof FormState, v: FormState[keyof FormState]) => setF({ ...f, [k]: v });
  return (
    <Card>
      <CardTitle>{editandoId ? `Editar compromisso #${editandoId}` : "Novo compromisso"}</CardTitle>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Candidato(a)" htmlFor="ag-candidato"><Input id="ag-candidato" required value={f.candidato} onChange={(e) => set("candidato", e.target.value)} /></Field>
          <Field label="Partido" htmlFor="ag-partido"><Input id="ag-partido" value={f.partido} onChange={(e) => set("partido", e.target.value)} /></Field>
          <Field label="Cargo" htmlFor="ag-cargo">
            <Select id="ag-cargo" value={f.cargo} onChange={(e) => set("cargo", e.target.value)}>{CARGOS.map((c) => <option key={c}>{c}</option>)}</Select>
          </Field>
          <Field label="Tipo" htmlFor="ag-tipo">
            <Select id="ag-tipo" value={f.tipo} onChange={(e) => set("tipo", e.target.value)}>{TIPOS.map((t) => <option key={t}>{t}</option>)}</Select>
          </Field>
        </div>
        <Field label="Título" htmlFor="ag-titulo"><Input id="ag-titulo" required value={f.titulo} onChange={(e) => set("titulo", e.target.value)} placeholder="Carreata de encerramento" /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Data" htmlFor="ag-data"><Input id="ag-data" type="date" required value={f.data} onChange={(e) => set("data", e.target.value)} /></Field>
          <Field label="Início (HH:MM)" htmlFor="ag-hi"><Input id="ag-hi" type="time" value={f.hora_inicio} onChange={(e) => set("hora_inicio", e.target.value)} /></Field>
          <Field label="Fim (HH:MM)" htmlFor="ag-hf"><Input id="ag-hf" type="time" value={f.hora_fim} onChange={(e) => set("hora_fim", e.target.value)} /></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Cidade" htmlFor="ag-cidade"><Input id="ag-cidade" value={f.cidade} onChange={(e) => set("cidade", e.target.value)} /></Field>
          <Field label="UF" htmlFor="ag-uf">
            <Select id="ag-uf" value={f.uf} onChange={(e) => set("uf", e.target.value)}><option value="">—</option>{UFS.map((u) => <option key={u}>{u}</option>)}</Select>
          </Field>
          <Field label="Local" htmlFor="ag-local"><Input id="ag-local" value={f.local} onChange={(e) => set("local", e.target.value)} /></Field>
        </div>
        <Field label="Rodovias federais envolvidas" htmlFor="rodovias" hint="Trajeto ou concentração em BR. Cruzadas com a base DNIT na query de monitoramento.">
          <RodoviasInput values={f.rodovias} onChange={(v) => set("rodovias", v)} />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.impacto_rodovia} onChange={(e) => set("impacto_rodovia", e.target.checked)} />
          Poderá impactar o fluxo viário em rodovia federal
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Fonte (URL)" htmlFor="ag-fonte"><Input id="ag-fonte" type="url" value={f.fonte_url} onChange={(e) => set("fonte_url", e.target.value)} placeholder="https://…" /></Field>
          <Field label="Status" htmlFor="ag-status">
            <Select id="ag-status" value={f.status} onChange={(e) => set("status", e.target.value)}>{STATUS.map((s) => <option key={s}>{s}</option>)}</Select>
          </Field>
        </div>
        <Field label="Descrição" htmlFor="ag-desc"><Textarea id="ag-desc" rows={2} value={f.descricao} onChange={(e) => set("descricao", e.target.value)} /></Field>
        <div className="flex gap-2">
          <Button type="submit" disabled={m.isPending}>{editandoId ? "Salvar alterações" : "Cadastrar compromisso"}</Button>
          {editandoId && <Button type="button" variant="ghost" onClick={onCancelar}>Cancelar edição</Button>}
        </div>
        <ErrorText error={m.error} />
      </form>
    </Card>
  );
}

function QueriesPanel({ evento }: { evento: AgendaEvento }) {
  const { data, error } = useQuery({ queryKey: ["agenda-queries", evento.id], queryFn: () => api.get<AgendaQueries>(`/api/agenda/${evento.id}/queries`) });
  if (error) return <ErrorText error={error} />;
  if (!data) return null;
  return (
    <div className="mt-2 space-y-2 rounded-md border border-border p-2 text-sm">
      <p className="text-xs text-muted-foreground">Google (after: véspera)</p>
      <p className="code rounded bg-muted p-1 text-xs">{data.query}</p>
      <DeeplinkButtons deeplinks={data.deeplinks} query={data.query} origem="agenda" />
      <p className="text-xs text-muted-foreground">X / TweetDeck (since: véspera, sem retweets)</p>
      <p className="code rounded bg-muted p-1 text-xs">{data.query_x}</p>
      <DeeplinkButtons deeplinks={data.deeplinks_x} query={data.query_x} origem="agenda-x" />
    </div>
  );
}

function EventoCard({ e, onEditar }: { e: AgendaEvento; onEditar: (e: AgendaEvento) => void }) {
  const qc = useQueryClient();
  const [verQueries, setVerQueries] = React.useState(false);
  const inval = () => void qc.invalidateQueries({ queryKey: ["agenda"] });
  const del = useMutation({ mutationFn: () => api.del(`/api/agenda/${e.id}`), onSuccess: inval });
  const mon = useMutation({ mutationFn: () => api.post<Monitor>(`/api/agenda/${e.id}/monitor`, { cron: "0 */2 * * *" }), onSuccess: inval });
  const horario = e.hora_inicio ? `${e.hora_inicio}${e.hora_fim ? `–${e.hora_fim}` : ""}` : "horário não informado";
  return (
    <li className="rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <strong>{horario}</strong>
        <span>{e.titulo}</span>
        <Badge>{e.tipo}</Badge>
        <Badge variant={e.status === "cancelado" ? "danger" : e.status === "confirmado" ? "success" : "muted"}>{e.status}</Badge>
        {e.impacto_rodovia && (
          <Badge variant="warning"><TriangleAlert size={12} aria-hidden /> impacto em rodovia federal</Badge>
        )}
        {e.monitor_id && <Badge variant="accent">monitor #{e.monitor_id}</Badge>}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        {[e.local, e.cidade && `${e.cidade}${e.uf ? `/${e.uf}` : ""}`].filter(Boolean).join(" · ") || "local não informado"}
        {e.rodovias.length > 0 && <> · {e.rodovias.join(", ")}</>}
      </p>
      {e.descricao && <p className="mt-1 text-sm">{e.descricao}</p>}
      <div className="mt-2 flex flex-wrap gap-1">
        <Button size="sm" variant="outline" onClick={() => setVerQueries((v) => !v)} aria-expanded={verQueries}><Search size={14} /> Queries</Button>
        <Button size="sm" variant="outline" disabled={!!e.monitor_id || mon.isPending} onClick={() => mon.mutate()}><Bell size={14} /> Monitorar</Button>
        {e.fonte_url && <Button size="sm" variant="ghost" onClick={() => openExternal(e.fonte_url!)}>Fonte</Button>}
        <Button size="icon" variant="ghost" aria-label={`Editar ${e.titulo}`} onClick={() => onEditar(e)}><Pencil size={14} /></Button>
        <Button size="icon" variant="ghost" aria-label={`Excluir ${e.titulo}`} onClick={() => del.mutate()}><Trash2 size={14} /></Button>
      </div>
      <ErrorText error={del.error ?? mon.error} />
      {verQueries && <QueriesPanel evento={e} />}
    </li>
  );
}

export default function AgendaPage() {
  const qc = useQueryClient();
  const [data, setData] = React.useState(hojeISO());
  const [editando, setEditando] = React.useState<AgendaEvento | null>(null);
  const { data: dia, error } = useQuery({ queryKey: ["agenda", "dia", data], queryFn: () => api.get<AgendaDia>(`/api/agenda/dia/${data}`) });
  const { data: proximos = [] } = useQuery({
    queryKey: ["agenda", "impacto", data],
    queryFn: () => api.get<AgendaEvento[]>(`/api/agenda${qs({ de: data, ate: somarDias(data, 7), impacto_rodovia: "true" })}`),
  });
  const inicial = React.useMemo(() => (editando ? deEvento(editando) : formVazio(data)), [editando, data]);
  const exportar = async (formato: "csv" | "json" | "ics") =>
    downloadBlob(await api.blob("GET", `/api/agenda/export${qs({ formato, data })}`), `agenda_${data}.${formato}`);

  return (
    <>
      <PageHeader title="Agenda dos candidatos" description="Compromissos por dia, com destaque para carreatas/motociatas que possam impactar rodovias federais. Gera queries de monitoramento e monitores.">
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => void exportar("csv")}><Download size={14} /> CSV</Button>
          <Button size="sm" variant="outline" onClick={() => void exportar("json")}><Download size={14} /> JSON</Button>
          <Button size="sm" variant="outline" onClick={() => void exportar("ics")}><Download size={14} /> ICS (calendário)</Button>
        </div>
      </PageHeader>
      <ErrorText error={error} />
      <div className="mb-4 flex flex-wrap items-end gap-2">
        <Button size="icon" variant="outline" aria-label="Dia anterior" onClick={() => setData(somarDias(data, -1))}><ChevronLeft size={16} /></Button>
        <Field label="Dia" htmlFor="ag-dia"><Input id="ag-dia" type="date" value={data} onChange={(e) => e.target.value && setData(e.target.value)} /></Field>
        <Button size="icon" variant="outline" aria-label="Próximo dia" onClick={() => setData(somarDias(data, 1))}><ChevronRight size={16} /></Button>
        <Button size="sm" variant="ghost" onClick={() => setData(hojeISO())}>Hoje</Button>
      </div>
      <div className="grid gap-4 lg:grid-cols-5">
        <div className="space-y-4 lg:col-span-3">
          <Card>
            <CardTitle>
              {dia ? `${dia.dia_semana}, ${data.split("-").reverse().join("/")}` : data} {dia && <Badge>{dia.total} compromisso(s)</Badge>}{" "}
              {dia && dia.com_impacto_rodovia > 0 && <Badge variant="warning">{dia.com_impacto_rodovia} com impacto em rodovia</Badge>}
            </CardTitle>
            {!dia || dia.total === 0 ? (
              <Empty>Nenhum compromisso cadastrado para este dia.</Empty>
            ) : (
              Object.entries(dia.por_candidato).map(([cand, evs]) => (
                <section key={cand} className="mb-4" aria-labelledby={`cand-${cand}`}>
                  <h3 id={`cand-${cand}`} className="mb-2 font-semibold">
                    {cand} {evs[0].partido && <span className="text-muted-foreground">({evs[0].partido})</span>}
                  </h3>
                  <ul className="space-y-2">{evs.map((e) => <EventoCard key={e.id} e={e} onEditar={setEditando} />)}</ul>
                </section>
              ))
            )}
          </Card>
          <Card>
            <CardTitle>Próximos 7 dias com impacto em rodovia federal</CardTitle>
            {proximos.length === 0 ? (
              <Empty>Nada com impacto em rodovia no período.</Empty>
            ) : (
              <ul className="space-y-1 text-sm">
                {proximos.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center gap-2">
                    <button type="button" className="text-primary underline" onClick={() => setData(e.data)}>{e.data.split("-").reverse().join("/")}</button>
                    <span>{e.hora_inicio ?? "—"}</span> <strong>{e.candidato}</strong> <span>{e.titulo}</span>
                    <span className="text-muted-foreground">{e.cidade}{e.uf && `/${e.uf}`} {e.rodovias.join(", ")}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Alert variant="info">
            Dados inseridos pelo analista a partir de fontes públicas (sites de campanha, imprensa). A base fica só nesta máquina.
          </Alert>
        </div>
        <div className="lg:col-span-2">
          <EventoForm
            inicial={inicial}
            editandoId={editando?.id ?? null}
            onSalvo={() => { setEditando(null); void qc.invalidateQueries({ queryKey: ["agenda"] }); }}
            onCancelar={() => setEditando(null)}
          />
        </div>
      </div>
    </>
  );
}
