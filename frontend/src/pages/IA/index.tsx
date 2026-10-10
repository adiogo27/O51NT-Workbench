import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, ExternalLink, RefreshCw, Search, Send, Trash2, X } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, TabPanel, Tabs } from "@/components/ui";
import { api, qs, type EtiquetaConfianca, type IaCustoDia, type IaStatus, type IaTarefa, type Severidade } from "@/lib/api";
import { formatDate, openExternal } from "@/lib/utils";
import { SEV_LABEL, SEV_VARIANT } from "@/pages/Alertas";

const VEREDITO_VARIANT: Record<string, "success" | "warning" | "muted" | "danger"> = { RELEVANTE: "danger", OBSERVAR: "warning", DESCARTAR: "muted" };
// Etiqueta de confiança da camada OOVS (derivada mecanicamente de origens distintas + verificação + aterramento)
const CONFIANCA_VARIANT: Record<EtiquetaConfianca, "success" | "warning" | "muted" | "danger"> = { alta: "success", media: "warning", baixa: "danger", nao_verificada: "muted", refutada: "danger" };
const CONFIANCA_LABEL: Record<EtiquetaConfianca, string> = { alta: "alta", media: "média", baixa: "baixa", nao_verificada: "não verificada", refutada: "REFUTADA" };
const STATUS_LABEL: Record<IaTarefa["status"], string> = { pendente: "na fila", em_processo: "processando", concluida: "concluída", erro: "erro" };
const APROVACAO_LABEL: Record<IaTarefa["aprovacao"], string> = { nao_se_aplica: "—", pendente: "aguardando aprovação", aprovada: "aprovada", rejeitada: "rejeitada" };
const SECOES = [
  { id: "noticia", l: "Notícias relevantes" },
  { id: "fake_news", l: "Fake news" },
  { id: "manifestacao", l: "Manifestações" },
  { id: "imagem_institucional", l: "Imagem institucional" },
  { id: "outro", l: "Outras" },
];

function useInval() {
  const qc = useQueryClient();
  return () => {
    for (const k of ["ia-tarefas", "ia-status", "ia-custo", "alertas", "alertas-contagem", "boletim", "agenda", "radar-hits"]) void qc.invalidateQueries({ queryKey: [k] });
  };
}

// ------------------------------------------------------------------ faixa de status
function StatusStrip() {
  const inval = useInval();
  const { data: st, error } = useQuery({ queryKey: ["ia-status"], queryFn: () => api.get<IaStatus>("/api/ia/status"), refetchInterval: 15000 });
  const ciclo = useMutation({ mutationFn: () => api.post<IaStatus["ultimo_ciclo"]>("/api/ia/ciclo", {}), onSuccess: inval });
  const resumo = useMutation({ mutationFn: () => api.post<{ enviados: number; erro?: string | null }>("/api/ia/resumo"), onSuccess: inval });
  if (!st) return <ErrorText error={error} />;
  const Stat = ({ v, l }: { v: React.ReactNode; l: string }) => (
    <div className="rounded-md border border-border px-3 py-2"><div className="text-lg font-bold leading-tight">{v}</div><div className="text-xs text-muted-foreground">{l}</div></div>
  );
  const custo = st.custo_hoje;
  return (
    <Card className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle className="mb-0 flex items-center gap-2"><Bot size={18} aria-hidden /> Assistente de IA</CardTitle>
        <Badge variant={st.ativo && st.agendado ? "success" : st.ativo ? "warning" : "muted"}>
          {st.ativo ? (st.agendado ? `ligado · a cada ${st.intervalo_min} min` : "ligado (agendador desligado neste processo)") : "desligado em Tema"}
        </Badge>
        <Badge variant={st.openclaw_configurado ? "success" : "danger"}>{st.openclaw_configurado ? "OpenClaw configurado" : "sem token do OpenClaw"}</Badge>
        {custo.bloqueado && <Badge variant="danger">teto diário atingido</Badge>}
        <span className="flex-1" />
        <Button size="sm" variant="outline" onClick={() => resumo.mutate()} disabled={resumo.isPending}><Send size={14} /> Enviar resumo agora</Button>
        <Button size="sm" onClick={() => ciclo.mutate()} disabled={ciclo.isPending || !st.openclaw_configurado}>
          <RefreshCw size={14} className={ciclo.isPending ? "animate-spin" : ""} /> {ciclo.isPending ? "Processando…" : "Processar fila agora"}
        </Button>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Só entra na fila o que já casou com os termos dos monitores (ou passou do limiar do detector de convocações). Cadeia: sentinela → extrator → pesquisador → analista.
        Política: boletim <strong>{st.politica.boletim}</strong>, agenda <strong>{st.politica.agenda}</strong>, pesquisa automática a partir de <strong>{st.politica.pesquisar_min}</strong>.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat v={<span className={st.fila.pendente ? "text-warning" : ""}>{st.fila.pendente}</span>} l="na fila" />
        <Stat v={st.fila.concluida} l={`concluídas (${st.fila.erro} com erro)`} />
        <Stat v={<span className={st.aprovacoes_pendentes ? "text-warning" : ""}>{st.aprovacoes_pendentes}</span>} l="aguardando aprovação" />
        <Stat v={`US$ ${custo.custo_usd.toFixed(2)} / ${custo.teto_usd.toFixed(2)}`} l={`custo hoje (${custo.chamadas} chamadas)`} />
        <Stat v={st.ultimo_ciclo ? `${st.ultimo_ciclo.concluidas}/${st.ultimo_ciclo.processadas}` : "—"} l={st.ultimo_ciclo ? `último ciclo ${formatDate(st.ultimo_ciclo.executado_em)}` : "sem ciclo neste processo"} />
        <Stat v={st.proximo_ciclo ? formatDate(st.proximo_ciclo).split(", ")[1] ?? formatDate(st.proximo_ciclo) : "—"} l="próximo ciclo" />
      </div>
      {st.ultimo_ciclo?.motivo_parada && <div className="mt-2"><Alert variant="warning">Último ciclo parou: {st.ultimo_ciclo.motivo_parada}</Alert></div>}
      {resumo.data && <p className="mt-2 text-sm">Resumo: {resumo.data.enviados} item(ns) enviado(s){resumo.data.erro ? ` — ${resumo.data.erro}` : ""}.</p>}
      <ErrorText error={ciclo.error ?? resumo.error} />
    </Card>
  );
}

// ------------------------------------------------------------------ tarefa
function Tarefa({ t, destaque }: { t: IaTarefa; destaque?: boolean }) {
  const inval = useInval();
  const [secao, setSecao] = React.useState(t.secao_sugerida ?? "noticia");
  const [data, setData] = React.useState(t.evento?.data ?? "");
  const [aberta, setAberta] = React.useState(!!destaque);
  const aprovar = useMutation({ mutationFn: (destino: "boletim" | "agenda" | "ambos") => api.post(`/api/ia/tarefas/${t.id}/aprovar`, { destino, secao, data: data || null }), onSuccess: inval });
  const rejeitar = useMutation({ mutationFn: () => api.post(`/api/ia/tarefas/${t.id}/rejeitar`, { motivo: "" }), onSuccess: inval });
  const pesquisar = useMutation({ mutationFn: () => api.post(`/api/ia/tarefas/${t.id}/pesquisar`), onSuccess: inval });
  const reprocessar = useMutation({ mutationFn: () => api.post(`/api/ia/tarefas/${t.id}/reprocessar`, { desde: "triagem" }), onSuccess: inval });
  const del = useMutation({ mutationFn: () => api.del(`/api/ia/tarefas/${t.id}`), onSuccess: inval });
  const titulo = t.cartao?.titulo || t.titulo || t.url;
  const podeAprovar = t.status === "concluida" && (t.veredito === "RELEVANTE" || t.veredito === "OBSERVAR") && t.aprovacao !== "aprovada";
  const temEvento = t.eh_evento && Object.keys(t.evento ?? {}).length > 0;
  return (
    <li className={`rounded-md border p-3 text-sm ${destaque ? "border-primary" : "border-border"} ${t.veredito === "DESCARTAR" ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="muted">#{t.id}</Badge>
        {t.veredito && <Badge variant={VEREDITO_VARIANT[t.veredito]}>{t.veredito}</Badge>}
        {t.severidade && <Badge variant={SEV_VARIANT[t.severidade as Severidade]}>{SEV_LABEL[t.severidade as Severidade]}</Badge>}
        <Badge>{STATUS_LABEL[t.status]}{t.status === "em_processo" && t.etapa ? ` · ${t.etapa}` : ""}</Badge>
        {t.aprovacao !== "nao_se_aplica" && <Badge variant={t.aprovacao === "pendente" ? "warning" : t.aprovacao === "aprovada" ? "success" : "muted"}>{APROVACAO_LABEL[t.aprovacao]}</Badge>}
        {t.eh_evento && <Badge variant="accent">evento</Badge>}
        {t.verificacao?.etiqueta && <Badge variant={CONFIANCA_VARIANT[t.verificacao.etiqueta]} title={(t.verificacao.motivos ?? []).join("; ")}>confiança {CONFIANCA_LABEL[t.verificacao.etiqueta]}</Badge>}
        {t.boletim_item_id && <Badge variant="success">boletim #{t.boletim_item_id}</Badge>}
        {t.agenda_evento_id && <Badge variant="success">agenda #{t.agenda_evento_id}</Badge>}
        <span className="ml-auto text-xs text-muted-foreground">{formatDate(t.concluido_em ?? t.criado_em)}</span>
      </div>
      <button type="button" className="mt-1 block text-left font-medium text-primary underline" onClick={() => setAberta(!aberta)} aria-expanded={aberta}>{titulo}</button>
      <p className="text-xs text-muted-foreground">
        {t.origem === "deteccao" ? "detector de convocações" : t.monitor_nome || t.origem} · {t.fonte_nome || "—"} {t.termos && <>· casou: <span className="code">{t.termos}</span></>}
      </p>
      {t.justificativa && <p className="mt-1">{t.justificativa}</p>}
      {t.erro && <Alert variant="error">{t.erro}</Alert>}
      {aberta && (
        <div className="mt-2 space-y-2 rounded-md bg-muted p-2 text-xs">
          {t.cartao?.resumo && <p><strong>Resumo:</strong> {t.cartao.resumo}</p>}
          {t.cartao?.impacto_rodovia && <p><strong>Impacto em rodovia federal:</strong> {t.cartao.impacto_rodovia}</p>}
          {t.cartao?.acao && <p><strong>Ação sugerida:</strong> {t.cartao.acao}</p>}
          {temEvento && (
            <p><strong>Evento:</strong> {[t.evento.tipo, t.evento.data, t.evento.hora, t.evento.cidade && `${t.evento.cidade}/${t.evento.uf ?? ""}`, t.evento.local, t.evento.rodovias?.join(", "), t.evento.organizador].filter(Boolean).join(" · ")}{typeof t.evento.confianca === "number" ? ` (confiança ${Math.round(t.evento.confianca * 100)}%)` : ""}</p>
          )}
          {t.pesquisa?.resposta && (
            <p><strong>Pesquisa{t.pesquisa.verificacao ? ` (${t.pesquisa.verificacao})` : ""}:</strong> {t.pesquisa.resposta}{t.pesquisa.lacunas ? ` Lacunas: ${t.pesquisa.lacunas}` : ""}</p>
          )}
          {t.verificacao?.etiqueta && (
            <p>
              <strong>Verificação ({t.verificacao.norma ?? "OOVS"}):</strong> {t.verificacao.origens_distintas ?? 0} origem(ns) distinta(s), {t.verificacao.corroboracoes ?? 0} corroboração(ões) além da fonte do item
              {typeof t.verificacao.duplicadas === "number" && t.verificacao.duplicadas > 0 ? `, ${t.verificacao.duplicadas} republicação(ões) descontada(s)` : ""}
              {t.verificacao.aterramento?.total ? ` · aterramento ${t.verificacao.aterramento.sustentadas}/${t.verificacao.aterramento.total}` : ""}
              {(t.verificacao.motivos?.length ?? 0) > 0 && <span className="block text-muted-foreground">{t.verificacao.motivos!.join(" · ")}</span>}
            </p>
          )}
          {(t.aterramento?.afirmacoes?.length ?? 0) > 0 && (
            <ul className="list-disc pl-5">{t.aterramento!.afirmacoes!.map((a, i) => <li key={i}><span className={a.sustentada === "sim" ? "text-success" : a.sustentada === "parcial" ? "text-warning" : "text-danger"}>{a.sustentada === "sim" ? "✓" : a.sustentada === "parcial" ? "~" : "✗"}</span> {a.texto}{typeof a.fonte === "number" ? ` (fonte ${a.fonte + 1})` : ""}</li>)}</ul>
          )}
          {(t.cartao?.fontes?.length ?? 0) > 0 && (
            <ul className="list-disc pl-5">{t.cartao.fontes!.map((u) => <li key={u}><a href={u} target="_blank" rel="noopener noreferrer" className="text-primary underline">{u}</a></li>)}</ul>
          )}
          <p className="text-muted-foreground">{t.tokens_entrada + t.tokens_saida} tokens · US$ {t.custo_usd.toFixed(4)} · {t.modelos || "—"} · texto {t.texto_chars} caracteres</p>
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-1">
        {podeAprovar && (
          <>
            <Select aria-label="Seção do boletim (IA)" className="h-8 w-44 py-0 text-xs" value={secao} onChange={(e) => setSecao(e.target.value)}>
              {SECOES.map((s) => <option key={s.id} value={s.id}>{s.l}</option>)}
            </Select>
            {!t.boletim_item_id && <Button size="sm" onClick={() => aprovar.mutate("boletim")} disabled={aprovar.isPending}><Check size={14} /> Aprovar no boletim</Button>}
            {temEvento && !t.agenda_evento_id && (
              <>
                <Input aria-label="Data do evento (IA)" type="date" className="h-8 w-40 py-0 text-xs" value={data} onChange={(e) => setData(e.target.value)} />
                <Button size="sm" onClick={() => aprovar.mutate("agenda")} disabled={aprovar.isPending}><Check size={14} /> Aprovar na agenda</Button>
              </>
            )}
            {t.aprovacao === "pendente" && <Button size="sm" variant="outline" onClick={() => rejeitar.mutate()} disabled={rejeitar.isPending}><X size={14} /> Rejeitar</Button>}
          </>
        )}
        {t.status === "concluida" && t.veredito !== "DESCARTAR" && !t.pesquisa?.resposta && (
          <Button size="sm" variant="outline" onClick={() => pesquisar.mutate()} disabled={pesquisar.isPending}><Search size={14} /> {pesquisar.isPending ? "Pesquisando…" : "Aprofundar"}</Button>
        )}
        {(t.status === "concluida" || t.status === "erro") && <Button size="sm" variant="ghost" onClick={() => reprocessar.mutate()} disabled={reprocessar.isPending}><RefreshCw size={14} /> Reprocessar</Button>}
        {t.url.startsWith("http") && <Button size="sm" variant="ghost" onClick={() => openExternal(t.url)}><ExternalLink size={14} /> Abrir</Button>}
        <Button size="icon" variant="ghost" aria-label={`Excluir tarefa ${t.id}`} onClick={() => del.mutate()}><Trash2 size={14} /></Button>
      </div>
      <ErrorText error={aprovar.error ?? rejeitar.error ?? pesquisar.error ?? reprocessar.error ?? del.error} />
    </li>
  );
}

function Fila({ aprovacao, alertaId }: { aprovacao?: "pendente"; alertaId?: number | null }) {
  const [veredito, setVeredito] = React.useState("");
  const [status, setStatus] = React.useState("");
  const { data = [], error } = useQuery({
    queryKey: ["ia-tarefas", aprovacao ?? "", veredito, status],
    queryFn: () => api.get<IaTarefa[]>(`/api/ia/tarefas${qs({ aprovacao, veredito: veredito || undefined, status: status || undefined, limit: 200 })}`),
    refetchInterval: 15000,
  });
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <CardTitle className="mb-0">{aprovacao ? "Aguardando sua aprovação" : "Fila e resultados"} ({data.length})</CardTitle>
        <span className="flex-1" />
        {!aprovacao && (
          <>
            <Field label="Veredito" htmlFor="ia-ver">
              <Select id="ia-ver" value={veredito} onChange={(e) => setVeredito(e.target.value)}>
                <option value="">todos</option>
                <option value="RELEVANTE">RELEVANTE</option>
                <option value="OBSERVAR">OBSERVAR</option>
                <option value="DESCARTAR">DESCARTAR</option>
              </Select>
            </Field>
            <Field label="Estado" htmlFor="ia-st">
              <Select id="ia-st" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">todos</option>
                <option value="pendente">na fila</option>
                <option value="em_processo">processando</option>
                <option value="concluida">concluída</option>
                <option value="erro">erro</option>
              </Select>
            </Field>
          </>
        )}
      </div>
      <ErrorText error={error} />
      {data.length === 0 ? (
        <Empty>{aprovacao ? "Nada aguardando aprovação." : "Fila vazia. Hits dos monitores e detecções de convocação entram aqui automaticamente quando o assistente está ligado."}</Empty>
      ) : (
        <ul className="space-y-2">{data.map((t) => <Tarefa key={t.id} t={t} destaque={alertaId != null && t.alerta_id === alertaId} />)}</ul>
      )}
    </Card>
  );
}

function Custo() {
  const { data, error } = useQuery({ queryKey: ["ia-custo"], queryFn: () => api.get<{ dias: IaCustoDia[]; total_usd: number; total_chamadas: number }>("/api/ia/custo?dias=14") });
  return (
    <Card>
      <CardTitle>Custo (14 dias): US$ {data?.total_usd.toFixed(2) ?? "—"} · {data?.total_chamadas ?? 0} chamadas</CardTitle>
      <ErrorText error={error} />
      {data && data.dias.length === 0 && <Empty>Nenhuma chamada registrada.</Empty>}
      {data && data.dias.length > 0 && (
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-1 pr-3">Dia</th><th className="py-1 pr-3">Chamadas</th><th className="py-1 pr-3">Tokens (entrada / saída)</th><th className="py-1">US$ (estimado)</th></tr></thead>
          <tbody>{data.dias.map((d) => <tr key={d.data} className="border-t border-border"><td className="py-1 pr-3">{d.data}</td><td className="py-1 pr-3">{d.chamadas}</td><td className="py-1 pr-3">{d.tokens_entrada} / {d.tokens_saida}</td><td className="py-1">{d.custo_usd.toFixed(4)}</td></tr>)}</tbody>
        </table>
      )}
      <p className="mt-2 text-xs text-muted-foreground">Valores estimados por tabela de preços por modelo (ajuste o teto diário em Tema → Assistente de IA). O consumo exato está no console do provedor.</p>
    </Card>
  );
}

export default function IaPage() {
  const [params] = useSearchParams();
  const alertaId = params.get("alerta") ? Number(params.get("alerta")) : null;
  const [tab, setTab] = React.useState(params.get("tab") ?? "fila");
  const { data: st } = useQuery({ queryKey: ["ia-status"], queryFn: () => api.get<IaStatus>("/api/ia/status") });
  return (
    <>
      <PageHeader title="Assistente de IA" description="O OpenClaw trabalha os termos dos monitores: tria, extrai o evento, verifica fontes e redige o cartão. Alertas saem sozinhos; Boletim e Agenda só com a sua aprovação (ou conforme a política em Tema)." />
      <StatusStrip />
      <Tabs
        label="Assistente de IA"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "fila", label: "Fila e resultados" },
          { id: "aprovacoes", label: st?.aprovacoes_pendentes ? `Aprovações (${st.aprovacoes_pendentes})` : "Aprovações" },
          { id: "custo", label: "Custo" },
        ]}
      />
      <TabPanel id="fila" active={tab === "fila"}><Fila alertaId={alertaId} /></TabPanel>
      <TabPanel id="aprovacoes" active={tab === "aprovacoes"}><Fila aprovacao="pendente" alertaId={alertaId} /></TabPanel>
      <TabPanel id="custo" active={tab === "custo"}><Custo /></TabPanel>
    </>
  );
}
