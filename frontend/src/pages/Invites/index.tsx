import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, RefreshCw, Trash2 } from "lucide-react";
import * as React from "react";
import { DeeplinkButtons, ENGINES, EnginePicker, EthicsNotice, ErrorText, ModeTabs, ScrapeExecucoes, SearxngSearchButton, SearxngStatus, useDebounced } from "@/components/shared";
import { Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader } from "@/components/ui";
import { api, qs, type Invite, type InviteVerificacao, type ScrapeExecucao } from "@/lib/api";
import { downloadBlob, formatDate, openExternal } from "@/lib/utils";

interface QueriesResp {
  queries: Record<string, string>;
  deeplinks: Record<string, Record<string, string>>;
  queries_searxng: Record<string, string[]>;
}

const STATUS_VARIANT: Record<Invite["status"], "success" | "danger" | "muted"> = { ativo: "success", revogado: "danger", desconhecido: "muted" };
const PLAT_LABEL: Record<string, string> = { whatsapp: "WhatsApp grupo", whatsapp_canal: "WhatsApp canal", telegram: "Telegram privado", telegram_publico: "Telegram público" };

function DeeplinksPanel({ termo }: { termo: string }) {
  const t = useDebounced(termo);
  const { data } = useQuery({ queryKey: ["invq", t], queryFn: () => api.get<QueriesResp>(`/api/invites/queries${qs({ termo: t })}`), enabled: !!t.trim() });
  if (!t.trim()) return <Empty>Digite um termo para gerar as queries do PDF.</Empty>;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {data &&
        Object.entries(data.queries).map(([plat, q]) => (
          <Card key={plat}>
            <CardTitle className="capitalize">{plat}</CardTitle>
            <p className="code mb-3 rounded-md bg-muted p-2 text-xs">{q}</p>
            <DeeplinkButtons deeplinks={data.deeplinks[plat]} query={q} origem={`invites-${plat}`} />
          </Card>
        ))}
    </div>
  );
}

function ScrapingPanel({ termo }: { termo: string }) {
  const qc = useQueryClient();
  const [plats, setPlats] = React.useState(["whatsapp", "telegram"]);
  const [engines, setEngines] = React.useState<string[]>([...ENGINES]);
  const t = useDebounced(termo);
  // as queries de convite do PDF (as mesmas dos deeplinks) decidem se o SearXNG é utilizável
  const { data: qsResp } = useQuery({
    queryKey: ["invq", t],
    queryFn: () => api.get<QueriesResp>(`/api/invites/queries${qs({ termo: t })}`),
    enabled: !!t.trim(),
  });
  // v2: as consultas enviadas ao SearXNG são as variantes simples (só `site:` e aspas, que Bing/DDG honram), não os dorks do PDF
  const queries = plats.flatMap((p) => qsResp?.queries_searxng?.[p] ?? []);
  const scan = useMutation({
    mutationFn: () => api.post<{ novos: number; atualizados: number; execucoes: ScrapeExecucao[] }>("/api/invites/scan", { termo, plataformas: plats, engines, max_consultas: 3 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
  });
  const check = (arr: string[], set: (v: string[]) => void, v: string) => (
    <label key={v} className="flex items-center gap-1 text-sm">
      <input type="checkbox" checked={arr.includes(v)} onChange={(e) => set(e.target.checked ? [...arr, v] : arr.filter((x) => x !== v))} /> {v}
    </label>
  );
  return (
    <div className="space-y-3">
      <EthicsNotice />
      <SearxngStatus />
      <div className="flex flex-wrap gap-6">
        <fieldset className="flex gap-3"><legend className="mb-1 text-xs text-muted-foreground">Plataformas</legend>{["whatsapp", "telegram"].map((v) => check(plats, setPlats, v))}</fieldset>
        <EnginePicker value={engines} onChange={setEngines} />
      </div>
      {queries.length > 0 && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Consultas que serão enviadas ({queries.length}; até 3 por plataforma)</summary>
          <ul className="code mt-1 space-y-0.5">{queries.map((q) => <li key={q}>{q}</li>)}</ul>
        </details>
      )}
      <SearxngSearchButton
        queries={queries}
        permitirOperadores
        disabled={!termo.trim() || !plats.length || !engines.length}
        pending={scan.isPending}
        onClick={() => scan.mutate()}
        label="Buscar convites via SearXNG"
      />
      <ErrorText error={scan.error} />
      {scan.data && (
        <>
          <p className="text-sm">
            <strong>{scan.data.novos}</strong> novo(s), <strong>{scan.data.atualizados}</strong> atualizado(s).
          </p>
          <ScrapeExecucoes execucoes={scan.data.execucoes} />
        </>
      )}
    </div>
  );
}

function LinhaConvite({ i, respeitarRobots }: { i: Invite; respeitarRobots: boolean }) {
  const qc = useQueryClient();
  const [ignorarRobots, setIgnorarRobots] = React.useState(false);
  const inval = () => { void qc.invalidateQueries({ queryKey: ["invites"] }); void qc.invalidateQueries({ queryKey: ["alertas-contagem"] }); };
  const del = useMutation({ mutationFn: () => api.del(`/api/invites/${i.id}`), onSuccess: inval });
  const testar = useMutation({
    mutationFn: () => api.post<{ convite: Invite; verificacao: InviteVerificacao }>(`/api/invites/${i.id}/testar${qs({ ignorar_robots: ignorarRobots ? "true" : undefined })}`),
    onSuccess: inval,
  });
  const v = testar.data?.verificacao;
  const robotsNegou = v ? !v.robots_permite : false;
  return (
    <tr className="border-t border-border align-top">
      <td className="p-2"><Badge variant={i.plataforma.startsWith("whatsapp") ? "success" : "default"}>{PLAT_LABEL[i.plataforma] ?? i.plataforma}</Badge></td>
      <td className="p-2 text-xs">
        <span className="code">{i.url}</span>
        {i.fonte_url && <p className="text-muted-foreground">visto em: <a className="underline" href={i.fonte_url} target="_blank" rel="noopener noreferrer">{i.fonte_url.slice(0, 60)}{i.fonte_url.length > 60 ? "…" : ""}</a></p>}
      </td>
      <td className="p-2">
        <Badge variant={STATUS_VARIANT[i.status]}>{i.status}</Badge>
        {i.verificado_em && <p className="text-xs text-muted-foreground">{formatDate(i.verificado_em)}{i.http_status ? ` · HTTP ${i.http_status}` : ""}</p>}
        {i.erro_verificacao && <p className="text-xs text-danger" title={i.erro_verificacao}>{i.erro_verificacao.slice(0, 60)}</p>}
      </td>
      <td className="p-2 text-xs">
        {i.nome_grupo ? <strong>{i.nome_grupo}</strong> : <span className="text-muted-foreground">—</span>}
        {i.descricao && <p className="text-muted-foreground">{i.descricao.slice(0, 120)}</p>}
        {i.evidencia_id && <a className="text-primary underline" href={`/api/evidence/${i.evidencia_id}/download?inline=true`} target="_blank" rel="noopener noreferrer">foto</a>}
      </td>
      <td className="p-2 text-xs">{i.membros ?? (i.plataforma.startsWith("whatsapp") ? <span title="WhatsApp não expõe o número de membros">—</span> : "—")}</td>
      <td className="p-2 text-xs">{i.score_relevancia ? <Badge variant={i.score_relevancia >= 55 ? "warning" : "muted"}>{i.score_relevancia}</Badge> : "—"}</td>
      <td className="p-2 text-xs">{i.termo}<br /><span className="text-muted-foreground">{formatDate(i.first_seen)}</span></td>
      <td className="p-2">
        <div className="flex flex-col items-start gap-1">
          <div className="flex gap-1">
            <Button size="sm" variant="outline" disabled={testar.isPending} onClick={() => testar.mutate()} title="GET da página pública do convite (nome, membros, ativo/revogado). Nunca entra no grupo."><RefreshCw size={14} className={testar.isPending ? "animate-spin" : ""} /> Testar</Button>
            <Button size="icon" variant="ghost" aria-label={`Abrir ${i.url}`} onClick={() => openExternal(i.url)}><ExternalLink size={14} /></Button>
            <Button size="icon" variant="ghost" aria-label={`Excluir ${i.url}`} onClick={() => del.mutate()}><Trash2 size={14} /></Button>
          </div>
          {(robotsNegou || !respeitarRobots) && (
            <label className="flex items-center gap-1 text-[11px] text-warning"><input type="checkbox" checked={ignorarRobots} onChange={(e) => setIgnorarRobots(e.target.checked)} /> ignorar robots.txt (decisão do analista)</label>
          )}
          <ErrorText error={testar.error ?? del.error} />
        </div>
      </td>
    </tr>
  );
}

function Tabela() {
  const qc = useQueryClient();
  const [status, setStatus] = React.useState("");
  const { data = [], refetch } = useQuery({ queryKey: ["invites", status], queryFn: () => api.get<Invite[]>(`/api/invites${qs({ status })}`), refetchInterval: 15000 });
  const { data: cfg } = useQuery({ queryKey: ["settings"], queryFn: () => api.get<{ preferencias: { convitesRespeitarRobots: boolean } }>("/api/settings") });
  const [novo, setNovo] = React.useState("");
  const registrar = useMutation({ mutationFn: () => api.post("/api/invites/registrar", { url: novo.trim(), termo: "colado" }), onSuccess: () => { setNovo(""); void qc.invalidateQueries({ queryKey: ["invites"] }); } });
  const testarTodos = useMutation({ mutationFn: (apenasNao: boolean) => api.post<{ agendados: number }>("/api/invites/testar-todos", { apenas_nao_verificados: apenasNao }), onSuccess: () => setTimeout(() => void refetch(), 2000) });
  const exportar = async (formato: "csv" | "json") => downloadBlob(await api.blob("GET", `/api/invites/export?formato=${formato}`), `convites.${formato}`);
  return (
    <Card className="mt-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="mb-0">Convites coletados ({data.length})</CardTitle>
        <div className="flex flex-wrap gap-2">
          <select aria-label="Filtrar por status" className="h-8 rounded-md border border-border bg-background px-2 text-xs" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">todos os status</option><option value="ativo">ativos</option><option value="revogado">revogados</option><option value="desconhecido">não verificados</option>
          </select>
          <Button size="sm" variant="outline" disabled={testarTodos.isPending} onClick={() => testarTodos.mutate(true)} title="Verifica em sequência, em segundo plano (1 req / 3 s por domínio)"><RefreshCw size={14} /> Testar não verificados</Button>
          <Button size="sm" variant="outline" disabled={testarTodos.isPending} onClick={() => testarTodos.mutate(false)}><RefreshCw size={14} /> Testar todos</Button>
          <Button size="sm" variant="outline" onClick={() => void exportar("csv")}><Download size={14} /> CSV</Button>
          <Button size="sm" variant="outline" onClick={() => void exportar("json")}><Download size={14} /> JSON</Button>
        </div>
      </div>
      {testarTodos.data && <p className="mb-2 text-xs text-muted-foreground">{testarTodos.data.agendados} verificação(ões) em andamento; a tabela atualiza sozinha.</p>}
      <div className="mb-3 flex max-w-xl gap-2">
        <Input aria-label="Colar link de convite" value={novo} onChange={(e) => setNovo(e.target.value)} placeholder="Colar um link: chat.whatsapp.com/… · t.me/+… · t.me/canal" />
        <Button size="sm" disabled={!novo.trim() || registrar.isPending} onClick={() => registrar.mutate()}>Registrar</Button>
      </div>
      <ErrorText error={registrar.error ?? testarTodos.error} />
      {data.length === 0 ? (
        <Empty>Nenhum convite armazenado.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Convites encontrados</caption>
            <thead className="text-xs text-muted-foreground">
              <tr><th scope="col" className="p-2">Plataforma</th><th scope="col" className="p-2">URL</th><th scope="col" className="p-2">Status</th><th scope="col" className="p-2">Nome do grupo</th><th scope="col" className="p-2">Membros</th><th scope="col" className="p-2">Relev.</th><th scope="col" className="p-2">Termo / 1ª vez</th><th scope="col" className="p-2"><span className="sr-only">Ações</span></th></tr>
            </thead>
            <tbody>{data.map((i) => <LinhaConvite key={i.id} i={i} respeitarRobots={cfg?.preferencias.convitesRespeitarRobots ?? true} />)}</tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-muted-foreground">"Testar" faz um GET da página pública do convite — o mesmo que qualquer pré-visualização de link — e registra nome, nº de membros (Telegram) e se foi revogado. Nunca entra no grupo nem lista membros.</p>
    </Card>
  );
}

export default function InvitesPage() {
  const [termo, setTermo] = React.useState("");
  return (
    <>
      <PageHeader title="Caçador de convites" description="Grupos e canais de WhatsApp (chat.whatsapp.com, whatsapp.com/channel) e Telegram (t.me/+, joinchat, canais públicos) divulgados em redes sociais, cartazes (QR/OCR) e páginas públicas — com teste de cada link." />
      <div className="mb-4 max-w-md">
        <Field label="Termo a ser pesquisado" htmlFor="termo">
          <Input id="termo" value={termo} onChange={(e) => setTermo(e.target.value)} placeholder="ex.: bloqueio rodovia" />
        </Field>
      </div>
      <ModeTabs label="Modo de busca de convites" deeplinks={<DeeplinksPanel termo={termo} />} scraping={<ScrapingPanel termo={termo} />} />
      <Tabela />
    </>
  );
}
