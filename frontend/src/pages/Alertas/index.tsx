import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCheck, ExternalLink, Trash2 } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { ErrorText } from "@/components/shared";
import { Badge, Button, Card, Empty, PageHeader, Select } from "@/components/ui";
import { api, qs, type Alerta, type Severidade } from "@/lib/api";
import { formatDate, openExternal } from "@/lib/utils";

export const SEV_VARIANT: Record<Severidade, "muted" | "default" | "warning" | "danger"> = { baixa: "muted", media: "default", alta: "warning", critica: "danger" };
export const SEV_LABEL: Record<Severidade, string> = { baixa: "baixa", media: "média", alta: "alta", critica: "CRÍTICA" };
const TIPO_LABEL: Record<Alerta["tipo"], string> = { convocacao: "Convocação", convite: "Convite", radar: "Radar" };

function Linha({ a }: { a: Alerta }) {
  const qc = useQueryClient();
  const inval = () => { void qc.invalidateQueries({ queryKey: ["alertas"] }); void qc.invalidateQueries({ queryKey: ["alertas-contagem"] }); };
  const lido = useMutation({ mutationFn: () => api.patch(`/api/alertas/${a.id}`, { lido: !a.lido }), onSuccess: inval });
  const del = useMutation({ mutationFn: () => api.del(`/api/alertas/${a.id}`), onSuccess: inval });
  const destino = a.deteccao_id ? `/convocacoes?deteccao=${a.deteccao_id}` : a.invite_id ? "/invites" : a.monitor_id ? "/monitors" : null;
  return (
    <li className={`rounded-md border border-border p-3 text-sm ${a.lido ? "opacity-60" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        {!a.lido && <span className="h-2 w-2 rounded-full bg-warning" aria-label="não lido" />}
        <Badge variant={SEV_VARIANT[a.severidade]}>{SEV_LABEL[a.severidade]}</Badge>
        <Badge variant="accent">{TIPO_LABEL[a.tipo]}</Badge>
        <strong>{a.titulo}</strong>
        <span className="ml-auto text-xs text-muted-foreground">{formatDate(a.criado_em)}</span>
      </div>
      {a.resumo && <p className="mt-1 text-muted-foreground">{a.resumo.slice(0, 300)}{a.resumo.length > 300 ? "…" : ""}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <Button size="sm" variant="ghost" onClick={() => lido.mutate()}><Check size={14} /> {a.lido ? "Marcar não lido" : "Marcar lido"}</Button>
        {destino && <Link to={destino} className="inline-flex h-8 items-center rounded-md px-3 text-xs font-medium hover:bg-muted">Ver detalhe</Link>}
        {a.url && <Button size="sm" variant="ghost" onClick={() => openExternal(a.url)}><ExternalLink size={14} /> Abrir post</Button>}
        <Button size="icon" variant="ghost" aria-label="Excluir alerta" onClick={() => del.mutate()}><Trash2 size={14} /></Button>
        <span className="ml-auto code text-[11px] text-muted-foreground">{a.canal_log}</span>
      </div>
      <ErrorText error={lido.error ?? del.error} />
    </li>
  );
}

export default function AlertasPage() {
  const qc = useQueryClient();
  const [tipo, setTipo] = React.useState("");
  const [soNaoLidos, setSoNaoLidos] = React.useState(true);
  const { data = [], error } = useQuery({
    queryKey: ["alertas", tipo, soNaoLidos],
    queryFn: () => api.get<Alerta[]>(`/api/alertas${qs({ tipo, lidos: soNaoLidos ? "false" : undefined, limit: 300 })}`),
    refetchInterval: 20000,
  });
  const todos = useMutation({
    mutationFn: () => api.post<{ marcados: number }>(`/api/alertas/marcar-todos${qs({ tipo })}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["alertas"] }); void qc.invalidateQueries({ queryKey: ["alertas-contagem"] }); },
  });
  return (
    <>
      <PageHeader title="Alertas" description="Caixa de entrada: convocações detectadas, convites relevantes e resultados do Radar. O JSONL em data/alerts/ e o webhook continuam sendo emitidos.">
        <Button variant="outline" size="sm" onClick={() => todos.mutate()} disabled={todos.isPending}><CheckCheck size={14} /> Marcar todos como lidos</Button>
      </PageHeader>
      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <Select aria-label="Tipo" className="w-44" value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">Todos os tipos</option>
            <option value="convocacao">Convocações</option>
            <option value="convite">Convites</option>
            <option value="radar">Radar</option>
          </Select>
          <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={soNaoLidos} onChange={(e) => setSoNaoLidos(e.target.checked)} /> só não lidos</label>
          <span className="text-xs text-muted-foreground">{data.length} alerta(s)</span>
        </div>
        <ErrorText error={error} />
        {data.length === 0 ? <Empty>Nenhum alerta{soNaoLidos ? " não lido" : ""}.</Empty> : <ul className="space-y-2">{data.map((a) => <Linha key={a.id} a={a} />)}</ul>}
      </Card>
    </>
  );
}
