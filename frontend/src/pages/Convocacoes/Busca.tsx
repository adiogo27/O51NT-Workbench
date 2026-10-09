import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Link2, Plus, Radar, Search, X } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { DeeplinkButtons, ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Input, Textarea } from "@/components/ui";
import { api, type Deteccao, type Invite, type Monitor } from "@/lib/api";

export interface TermosBusca {
  frases: string[];
  locais: string[];
  organizacoes: string[];
  hashtags: string[];
  mencoes: string[];
  datas: string[];
  termos: string[];
  query_mencoes: string;
  deeplinks: Record<string, string>;
  ia: boolean;
  observacoes: string;
}

interface Mencao { titulo: string; url: string; trecho: string; engines: string[]; publicado_em: string | null }
interface BuscaMencoes { query: string; erro: string | null; resultados: Mencao[]; deeplinks: Record<string, string>; engines_sem_resposta: unknown[] }
interface BuscaConvites { novos: number; atualizados: number; convites: Invite[]; execucoes: { query: string; encontrados: number; erro: string | null }[] }

/** Os termos lidos no cartaz viram buscas: convites abertos (WhatsApp/Telegram), menções na web/redes e um monitor contínuo. */
export function BuscaDeteccao({ d }: { d: Deteccao }) {
  const qc = useQueryClient();
  const { data: base, error } = useQuery({ queryKey: ["det-busca", d.id], queryFn: () => api.get<TermosBusca>(`/api/convocacoes/${d.id}/busca`) });
  const [termos, setTermos] = React.useState<string[] | null>(null);
  const [novo, setNovo] = React.useState("");
  const [query, setQuery] = React.useState<string | null>(null);
  const [sel, setSel] = React.useState<Set<string>>(new Set());
  const lista = termos ?? base?.termos ?? [];
  const q = query ?? base?.query_mencoes ?? "";
  React.useEffect(() => { if (base && termos === null) setSel(new Set(base.termos.slice(0, 3))); }, [base, termos]);

  const ia = useMutation({
    mutationFn: () => api.post<TermosBusca>(`/api/convocacoes/${d.id}/busca/ia`),
    onSuccess: (r) => { setTermos(r.termos); setQuery(r.query_mencoes); setSel(new Set(r.termos.slice(0, 3))); },
  });
  const convites = useMutation({
    mutationFn: () => api.post<BuscaConvites>(`/api/convocacoes/${d.id}/busca/convites`, { termos: [...sel].slice(0, 6) }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["invites"] }); void qc.invalidateQueries({ queryKey: ["convocacoes"] }); },
  });
  const mencoes = useMutation({ mutationFn: () => api.post<BuscaMencoes>(`/api/convocacoes/${d.id}/busca/mencoes`, { query: q }) });
  const monitor = useMutation({
    mutationFn: () => api.post<Monitor>(`/api/convocacoes/${d.id}/monitor`, { query: q }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["monitors"] }); void qc.invalidateQueries({ queryKey: ["convocacoes"] }); },
  });
  const alternar = (t: string) => { const s = new Set(sel); if (s.has(t)) s.delete(t); else s.add(t); setSel(s); };
  const remover = (t: string) => { setTermos(lista.filter((x) => x !== t)); const s = new Set(sel); s.delete(t); setSel(s); };
  const adicionar = () => { const t = novo.trim(); if (!t || lista.includes(t)) return; setTermos([...lista, t]); setSel(new Set([...sel, t])); setNovo(""); };

  if (error) return <ErrorText error={error} />;
  if (!base) return <p className="text-xs text-muted-foreground">Extraindo termos…</p>;
  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/40 p-3 text-sm" aria-label={`Busca a partir da detecção ${d.id}`}>
      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Termos lidos no cartaz (clique para selecionar os que vão à busca de convites; × remove)</p>
        <div className="flex flex-wrap gap-1">
          {lista.map((t) => (
            <span key={t} className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${sel.has(t) ? "border-primary bg-primary text-primary-foreground" : "border-border"}`}>
              <button type="button" onClick={() => alternar(t)} aria-pressed={sel.has(t)}>{t}</button>
              <button type="button" aria-label={`Remover termo ${t}`} onClick={() => remover(t)}><X size={12} /></button>
            </span>
          ))}
          {lista.length === 0 && <span className="text-xs text-muted-foreground">nenhum termo extraído; adicione manualmente ou peça à IA</span>}
        </div>
        <div className="mt-2 flex gap-2">
          <Input aria-label="Novo termo de busca" className="h-8 text-xs" placeholder="adicionar termo…" value={novo} onChange={(e) => setNovo(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), adicionar())} />
          <Button size="sm" variant="outline" onClick={adicionar}><Plus size={14} /> Adicionar</Button>
          <Button size="sm" variant="outline" onClick={() => ia.mutate()} disabled={ia.isPending} title="Pede ao agent extrator termos adicionais (1 chamada ao OpenClaw)"><Bot size={14} /> {ia.isPending ? "IA…" : "Refinar com IA"}</Button>
        </div>
        {(base.datas.length > 0 || base.locais.length > 0) && (
          <p className="mt-1 text-xs text-muted-foreground">
            {base.datas.length > 0 && <>datas: {base.datas.join(", ")} · </>}{base.locais.length > 0 && <>locais: {base.locais.join("; ")}</>}
          </p>
        )}
        {ia.data?.observacoes && <p className="mt-1 text-xs text-muted-foreground">IA: {ia.data.observacoes}</p>}
        <ErrorText error={ia.error} />
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Query de menções (sintaxe do Query Builder; edite à vontade)</p>
        <Textarea aria-label="Query de menções" rows={2} className="font-mono text-xs" value={q} onChange={(e) => setQuery(e.target.value)} />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => convites.mutate()} disabled={convites.isPending || sel.size === 0}><Link2 size={14} /> {convites.isPending ? "Buscando convites…" : `Convites abertos (${sel.size} termo(s))`}</Button>
          <Button size="sm" onClick={() => mencoes.mutate()} disabled={mencoes.isPending || !q}><Search size={14} /> {mencoes.isPending ? "Buscando…" : "Menções (SearXNG)"}</Button>
          <Button size="sm" variant="outline" onClick={() => monitor.mutate()} disabled={monitor.isPending || !q}><Radar size={14} /> Criar monitor contínuo</Button>
          <DeeplinkButtons deeplinks={base.deeplinks} query={q} origem="convocacao" />
        </div>
        <ErrorText error={convites.error ?? mencoes.error ?? monitor.error} />
      </div>

      {monitor.data && <Alert variant="success">Monitor #{monitor.data.id} criado ({monitor.data.hits_total} hit(s) no cache). O Radar casa as fontes a cada ciclo e o assistente de IA tria os hits. <Link to="/monitors" className="underline">Ver monitores</Link></Alert>}

      {convites.data && (
        <div>
          <Alert variant={convites.data.convites.length ? "success" : "info"}>
            Convites: {convites.data.novos} novo(s), {convites.data.atualizados} já conhecido(s) em {convites.data.execucoes.length} consulta(s).{convites.data.convites.length > 0 && <> <Link to="/invites" className="underline">Ver em Convites</Link></>}
          </Alert>
          {convites.data.convites.length > 0 && (
            <ul className="mt-1 space-y-1 text-xs">
              {convites.data.convites.map((c) => (
                <li key={c.url} className="flex flex-wrap items-center gap-2"><Badge>{c.plataforma}</Badge><a className="code text-primary underline" href={c.url} target="_blank" rel="noopener noreferrer">{c.url}</a>{c.nome_grupo && <span>{c.nome_grupo}</span>}{c.status !== "desconhecido" && <Badge variant={c.status === "ativo" ? "success" : "muted"}>{c.status}</Badge>}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {mencoes.data && (
        <div>
          <Alert variant={mencoes.data.erro ? "error" : "info"}>{mencoes.data.erro ? `SearXNG: ${mencoes.data.erro}` : `${mencoes.data.resultados.length} resultado(s) para a query`}</Alert>
          {mencoes.data.resultados.length > 0 && (
            <ul className="mt-1 space-y-1 text-xs">
              {mencoes.data.resultados.slice(0, 30).map((r) => (
                <li key={r.url}>
                  <a className="font-medium text-primary underline" href={r.url} target="_blank" rel="noopener noreferrer">{r.titulo}</a>
                  {r.publicado_em && <span className="text-muted-foreground"> · {r.publicado_em.slice(0, 10)}</span>}
                  {r.trecho && <p className="text-muted-foreground">{r.trecho}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
