import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, ExternalLink, Newspaper, Pause, Play, RefreshCw, Rss, Trash2, Zap } from "lucide-react";
import * as React from "react";
import { DeeplinkButtons, ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, TabPanel, Tabs, Textarea } from "@/components/ui";
import { api, qs, type Fonte, type FonteCatalogo, type FonteTeste, type Hit, type Monitor, type MonitorRun, type RadarStatus, type Template } from "@/lib/api";
import { formatDate, openExternal } from "@/lib/utils";

const CRONS = [
  { v: "*/30 * * * *", l: "a cada 30 min" },
  { v: "0 * * * *", l: "de hora em hora" },
  { v: "0 */6 * * *", l: "a cada 6 h" },
  { v: "0 8 * * *", l: "diário 08:00" },
];
const SECOES_BOLETIM = [
  { id: "noticia", l: "Notícias relevantes" },
  { id: "fake_news", l: "Fake news" },
  { id: "manifestacao", l: "Manifestações" },
  { id: "imagem_institucional", l: "Imagem institucional" },
  { id: "outro", l: "Outras" },
];

// ------------------------------------------------------------------ Radar: tira de status
function RadarStrip() {
  const qc = useQueryClient();
  const { data: st, error } = useQuery({ queryKey: ["radar-status"], queryFn: () => api.get<RadarStatus>("/api/radar/status"), refetchInterval: 15000 });
  const ciclo = useMutation({
    mutationFn: () => api.post<{ itens_novos: number; hits_novos: number }>("/api/radar/ciclo"),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["radar-status"] }); void qc.invalidateQueries({ queryKey: ["radar-hits"] }); void qc.invalidateQueries({ queryKey: ["monitors"] }); void qc.invalidateQueries({ queryKey: ["fontes"] }); },
  });
  if (!st) return <ErrorText error={error} />;
  const Stat = ({ v, l }: { v: React.ReactNode; l: string }) => (
    <div className="rounded-md border border-border px-3 py-2"><div className="text-lg font-bold leading-tight">{v}</div><div className="text-xs text-muted-foreground">{l}</div></div>
  );
  return (
    <Card className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle className="mb-0 flex items-center gap-2"><Rss size={18} aria-hidden /> Radar</CardTitle>
        <Badge variant={st.ativo && st.agendado ? "success" : st.ativo ? "warning" : "muted"}>
          {st.ativo ? (st.agendado ? `ligado · a cada ${st.intervalo_min} min` : "ligado (agendador desligado neste processo)") : "desligado em Tema"}
        </Badge>
        <span className="flex-1" />
        <Button size="sm" onClick={() => ciclo.mutate()} disabled={ciclo.isPending}>
          <RefreshCw size={14} className={ciclo.isPending ? "animate-spin" : ""} /> {ciclo.isPending ? "Coletando e casando…" : "Rodar ciclo agora"}
        </Button>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        Todos os monitores ativos pesquisam ao mesmo tempo: cada ciclo coleta as fontes (RSS/Atom públicos) e casa os itens novos com a query de cada monitor.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat v={st.monitores_ativos} l="monitores ativos" />
        <Stat v={`${st.fontes_ativas}/${st.fontes_total}`} l="fontes ativas" />
        <Stat v={st.itens_total} l="itens coletados" />
        <Stat v={<span className={st.hits_novos ? "text-warning" : ""}>{st.hits_novos}</span>} l={`hits não lidos (de ${st.hits_total})`} />
        <Stat v={st.ultimo_ciclo ? `${st.ultimo_ciclo.hits_novos} hit(s)` : "—"} l={st.ultimo_ciclo ? `último ciclo ${formatDate(st.ultimo_ciclo.executado_em)}` : "sem ciclo neste processo"} />
        <Stat v={st.proximo_ciclo ? formatDate(st.proximo_ciclo).split(", ")[1] ?? formatDate(st.proximo_ciclo) : "—"} l="próximo ciclo" />
      </div>
      <ErrorText error={ciclo.error} />
      {ciclo.data && <p className="mt-2 text-sm">Ciclo concluído: {ciclo.data.itens_novos} item(ns) novo(s), {ciclo.data.hits_novos} hit(s) novo(s).</p>}
    </Card>
  );
}

// ------------------------------------------------------------------ Hits
function HitLinha({ h, mostrarMonitor = true }: { h: Hit; mostrarMonitor?: boolean }) {
  const qc = useQueryClient();
  const [secao, setSecao] = React.useState("noticia");
  const inval = () => { void qc.invalidateQueries({ queryKey: ["radar-hits"] }); void qc.invalidateQueries({ queryKey: ["radar-status"] }); void qc.invalidateQueries({ queryKey: ["monitors"] }); void qc.invalidateQueries({ queryKey: ["boletim"] }); };
  const lido = useMutation({ mutationFn: () => api.patch(`/api/radar/hits/${h.id}`, { lido: !h.lido }), onSuccess: inval });
  const boletim = useMutation({ mutationFn: () => api.post(`/api/radar/hits/${h.id}/boletim`, { secao }), onSuccess: inval });
  return (
    <li className={`rounded-md border border-border p-2 text-sm ${h.lido ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-center gap-2">
        {!h.lido && <span className="h-2 w-2 rounded-full bg-warning" aria-label="não lido" />}
        <a href={h.url} target="_blank" rel="noopener noreferrer" className="font-medium text-primary underline">{h.titulo || h.url}</a>
        {mostrarMonitor && <Badge variant="accent">{h.monitor_nome}</Badge>}
        <Badge>{h.fonte_nome || "fonte"}</Badge>
        <span className="text-xs text-muted-foreground">{h.publicado_em ? `publicado ${formatDate(h.publicado_em)}` : `encontrado ${formatDate(h.encontrado_em)}`}</span>
        {h.boletim_item_id && <Badge variant="success">no boletim #{h.boletim_item_id}</Badge>}
      </div>
      {h.resumo && <p className="mt-1 text-muted-foreground">{h.resumo.slice(0, 280)}{h.resumo.length > 280 ? "…" : ""}</p>}
      <p className="code mt-1 text-xs text-muted-foreground">casou: {h.termos}</p>
      <div className="mt-1 flex flex-wrap items-center gap-1">
        <Button size="sm" variant="ghost" onClick={() => lido.mutate()}><Check size={14} /> {h.lido ? "Marcar não lido" : "Marcar lido"}</Button>
        {!h.boletim_item_id && (
          <>
            <Select aria-label="Seção do boletim" className="h-8 w-44 py-0 text-xs" value={secao} onChange={(e) => setSecao(e.target.value)}>
              {SECOES_BOLETIM.map((s) => <option key={s.id} value={s.id}>{s.l}</option>)}
            </Select>
            <Button size="sm" variant="outline" disabled={boletim.isPending} onClick={() => boletim.mutate()}><Newspaper size={14} /> Adicionar ao boletim</Button>
          </>
        )}
        <Button size="sm" variant="ghost" onClick={() => openExternal(h.url)}><ExternalLink size={14} /> Abrir</Button>
      </div>
      <ErrorText error={lido.error ?? boletim.error} />
    </li>
  );
}

function ItensColetados() {
  const [q, setQ] = React.useState("");
  const [busca, setBusca] = React.useState("");
  const { data: itens = [], isFetching } = useQuery({
    queryKey: ["radar-itens", busca],
    queryFn: () => api.get<{ id: number; fonte_nome: string; url: string; titulo: string; resumo: string; publicado_em: string | null }[]>(`/api/radar/itens${qs({ q: busca || undefined, limit: 50 })}`),
  });
  return (
    <Card className="mt-4">
      <CardTitle>Itens coletados {busca ? `— "${busca}"` : "(mais recentes)"} <Badge>{itens.length}</Badge></CardTitle>
      <form className="mb-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); setBusca(q.trim()); }}>
        <Input aria-label="Buscar nos itens coletados" placeholder="teste um termo (ex.: PRF, blitz, rodovia)…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit" size="sm" variant="outline" disabled={isFetching}>Buscar</Button>
      </form>
      <p className="mb-2 text-xs text-muted-foreground">Tudo o que o Radar coletou das fontes, antes de qualquer casamento — útil para calibrar a query de um monitor.</p>
      {itens.length === 0 ? <Empty>Nenhum item{busca ? " com esse termo" : ""}.</Empty> : (
        <ul className="space-y-1 text-sm">
          {itens.map((i) => (
            <li key={i.id}>
              <a href={i.url} target="_blank" rel="noopener noreferrer" className="text-primary underline">{i.titulo || i.url}</a>{" "}
              <Badge>{i.fonte_nome}</Badge> <span className="text-xs text-muted-foreground">{i.publicado_em ? formatDate(i.publicado_em) : ""}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function HitsTab({ monitores }: { monitores: Monitor[] }) {
  const qc = useQueryClient();
  const [monitorId, setMonitorId] = React.useState("");
  const [soNaoLidos, setSoNaoLidos] = React.useState(true);
  const { data: hits = [], error } = useQuery({
    queryKey: ["radar-hits", monitorId, soNaoLidos],
    queryFn: () => api.get<Hit[]>(`/api/radar/hits${qs({ monitor_id: monitorId || undefined, lidos: soNaoLidos ? "false" : undefined, limit: 200 })}`),
    refetchInterval: 20000,
  });
  const marcarTodos = useMutation({
    mutationFn: () => api.post(`/api/radar/hits/marcar-todos${qs({ monitor_id: monitorId || undefined })}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["radar-hits"] }); void qc.invalidateQueries({ queryKey: ["radar-status"] }); void qc.invalidateQueries({ queryKey: ["monitors"] }); },
  });
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-end gap-2">
        <CardTitle className="mb-0">Resultados dos monitores ({hits.length})</CardTitle>
        <span className="flex-1" />
        <Field label="Monitor" htmlFor="hits-monitor">
          <Select id="hits-monitor" value={monitorId} onChange={(e) => setMonitorId(e.target.value)}>
            <option value="">todos</option>
            {monitores.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
          </Select>
        </Field>
        <label className="flex h-9 items-center gap-2 text-sm"><input type="checkbox" checked={soNaoLidos} onChange={(e) => setSoNaoLidos(e.target.checked)} /> só não lidos</label>
        <Button size="sm" variant="outline" onClick={() => marcarTodos.mutate()}>Marcar todos como lidos</Button>
      </div>
      <ErrorText error={error ?? marcarTodos.error} />
      {hits.length === 0 ? <Empty>Nenhum hit{soNaoLidos ? " não lido" : ""}. Rode um ciclo do Radar ou aguarde o próximo.</Empty> : <ul className="space-y-2">{hits.map((h) => <HitLinha key={h.id} h={h} />)}</ul>}
    </Card>
  );
}

function HitsEItens({ monitores }: { monitores: Monitor[] }) {
  return (
    <>
      <HitsTab monitores={monitores} />
      <ItensColetados />
    </>
  );
}

// ------------------------------------------------------------------ Fontes
function FontesTab() {
  const qc = useQueryClient();
  const { data: fontes = [], error } = useQuery({ queryKey: ["fontes"], queryFn: () => api.get<Fonte[]>("/api/radar/fontes") });
  const { data: catalogo = [] } = useQuery({ queryKey: ["fontes-catalogo"], queryFn: () => api.get<FonteCatalogo[]>("/api/radar/fontes/catalogo") });
  const vazio = { nome: "", url: "", categoria: "imprensa", respeitar_robots: true, tipo: "feed" as "feed" | "pagina", intervalo_min: "" };
  const [f, setF] = React.useState(vazio);
  const [teste, setTeste] = React.useState<FonteTeste | null>(null);
  const inval = () => { void qc.invalidateQueries({ queryKey: ["fontes"] }); void qc.invalidateQueries({ queryKey: ["fontes-catalogo"] }); void qc.invalidateQueries({ queryKey: ["radar-status"] }); };
  const testar = useMutation({ mutationFn: () => api.post<FonteTeste>("/api/radar/fontes/testar", { url: f.url, respeitar_robots: f.respeitar_robots }), onSuccess: setTeste });
  const criar = useMutation({
    mutationFn: () => api.post<Fonte>("/api/radar/fontes", { ...f, intervalo_min: f.intervalo_min ? Number(f.intervalo_min) : null }),
    onSuccess: () => { setF(vazio); setTeste(null); inval(); },
  });
  const addCatalogo = useMutation({ mutationFn: (c: FonteCatalogo) => api.post<Fonte>("/api/radar/fontes", { nome: c.nome, url: c.url, categoria: c.categoria }), onSuccess: inval });
  const toggle = useMutation({ mutationFn: (x: Fonte) => api.patch(`/api/radar/fontes/${x.id}`, { ativa: !x.ativa }), onSuccess: inval });
  const coletar = useMutation({ mutationFn: (id: number) => api.post(`/api/radar/fontes/${id}/coletar`), onSuccess: () => { inval(); void qc.invalidateQueries({ queryKey: ["radar-hits"] }); void qc.invalidateQueries({ queryKey: ["monitors"] }); } });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/radar/fontes/${id}`), onSuccess: inval });
  const sugeridas = catalogo.filter((c) => !c.cadastrada && c.tipo === "feed");
  const modelos = catalogo.filter((c) => c.tipo === "modelo");
  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <div className="space-y-4 lg:col-span-3">
        <Card>
          <CardTitle>Fontes do Radar ({fontes.length})</CardTitle>
          <ErrorText error={error ?? toggle.error ?? del.error ?? coletar.error} />
          {fontes.length === 0 ? <Empty>Nenhuma fonte.</Empty> : (
            <ul className="divide-y divide-border">
              {fontes.map((x) => (
                <li key={x.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <strong>{x.nome}</strong>
                      <Badge>{x.categoria}</Badge>
                      {x.tipo === "pagina" && <Badge variant="accent">página</Badge>}
                      {x.intervalo_min ? <Badge variant="muted">a cada {x.intervalo_min} min</Badge> : null}
                      <Badge variant={x.ativa ? "success" : "muted"}>{x.ativa ? "ativa" : "inativa"}</Badge>
                      {!x.respeitar_robots && <Badge variant="warning">ignora robots.txt</Badge>}
                      {x.ultimo_erro && <Badge variant="danger">erro</Badge>}
                    </div>
                    <a className="code block truncate text-xs text-primary underline" href={x.url} target="_blank" rel="noopener noreferrer">{x.url}</a>
                    <span className="block text-xs text-muted-foreground">
                      {x.itens_total} item(ns) · última coleta {formatDate(x.ultima_coleta)}{x.ultimo_status ? ` · HTTP ${x.ultimo_status}` : ""}{x.ultimo_erro ? ` · ${x.ultimo_erro}` : ""}
                    </span>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => coletar.mutate(x.id)} disabled={coletar.isPending}><RefreshCw size={14} /> Coletar</Button>
                  <Button size="icon" variant="ghost" aria-label={x.ativa ? `Desativar ${x.nome}` : `Ativar ${x.nome}`} onClick={() => toggle.mutate(x)}>{x.ativa ? <Pause size={14} /> : <Play size={14} />}</Button>
                  <Button size="icon" variant="ghost" aria-label={`Excluir fonte ${x.nome}`} onClick={() => del.mutate(x.id)}><Trash2 size={14} /></Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
        {sugeridas.length > 0 && (
          <Card>
            <CardTitle>Sugeridas (verificadas)</CardTitle>
            <ul className="space-y-1 text-sm">
              {sugeridas.map((c) => (
                <li key={c.url} className="flex flex-wrap items-center gap-2"><span>{c.nome}</span><Badge>{c.categoria}</Badge><Button size="sm" variant="ghost" onClick={() => addCatalogo.mutate(c)}>Adicionar</Button></li>
              ))}
            </ul>
          </Card>
        )}
        <Card>
          <CardTitle>Modelos</CardTitle>
          <ul className="space-y-2 text-sm">
            {modelos.map((c) => (
              <li key={c.nome}>
                <strong>{c.nome}</strong> <Badge>{c.categoria}</Badge>
                <p className="text-muted-foreground">{c.descricao}</p>
                <p className="code text-xs">{c.url}</p>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <div className="space-y-4 lg:col-span-2">
        <Card>
          <CardTitle>Nova fonte (RSS/Atom ou página de notícias)</CardTitle>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); criar.mutate(); }}>
            <Field label="Nome da fonte" htmlFor="fo-nome"><Input id="fo-nome" required value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} placeholder="Google Alertas — PRF blitz" /></Field>
            <Field label="Tipo da fonte" htmlFor="fo-tipo" hint="página = HTML sem RSS; os links de matérias são extraídos a cada verificação (se a página anunciar um RSS, ele é adotado).">
              <Select id="fo-tipo" value={f.tipo} onChange={(e) => setF({ ...f, tipo: e.target.value as "feed" | "pagina" })}>
                <option value="feed">feed RSS/Atom</option>
                <option value="pagina">página de notícias (HTML)</option>
              </Select>
            </Field>
            <Field label={f.tipo === "pagina" ? "URL da página" : "URL do feed"} htmlFor="fo-url"><Input id="fo-url" type="url" required value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder={f.tipo === "pagina" ? "https://…/ultimas-noticias" : "https://…/feed.xml"} /></Field>
            <Field label="Intervalo próprio (min)" htmlFor="fo-int" hint="vazio = segue o intervalo global do Radar">
              <Input id="fo-int" type="number" min={1} max={10080} value={f.intervalo_min} onChange={(e) => setF({ ...f, intervalo_min: e.target.value })} placeholder="ex.: 60" />
            </Field>
            <Field label="Categoria da fonte" htmlFor="fo-cat">
              <Select id="fo-cat" value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })}>
                {["imprensa", "oficial", "rede", "alerta", "outro"].map((c) => <option key={c}>{c}</option>)}
              </Select>
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!f.respeitar_robots} onChange={(e) => setF({ ...f, respeitar_robots: !e.target.checked })} />
              Ignorar robots.txt (só para feeds pessoais, ex.: Google Alertas)
            </label>
            <div className="flex gap-2">
              <Button type="button" variant="outline" disabled={!f.url || testar.isPending} onClick={() => testar.mutate()}>{testar.isPending ? "Testando…" : "Testar"}</Button>
              <Button type="submit" disabled={criar.isPending}>Cadastrar fonte</Button>
            </div>
            <ErrorText error={testar.error ?? criar.error} />
            {teste && (
              <Alert variant={teste.ok ? "success" : "error"}>
                {teste.ok ? `${teste.itens} item(ns) lidos (HTTP ${teste.status})${teste.tipo_detectado === "pagina" ? " — reconhecida como página HTML" : ""}.` : `Falhou: ${teste.erro}`} {teste.robots_permite ? "" : " robots.txt não permite esta URL."}
                {teste.feed_descoberto && <span className="block">A página anuncia um RSS: <span className="code">{teste.feed_descoberto}</span> (será adotado automaticamente).</span>}
                {teste.ok && teste.amostra.length > 0 && <ul className="mt-1 list-disc pl-5 text-xs">{teste.amostra.map((a) => <li key={a.url}>{a.titulo}</li>)}</ul>}
              </Alert>
            )}
          </form>
        </Card>
        <Alert variant="info">
          Feeds existem para leitura por máquina, por isso são a forma ética de "pesquisar" continuamente. Buscadores (Google/Bing/X) bloqueiam coleta automática; o <strong>Google Alertas</strong> entrega a busca do Google por feed pessoal.
        </Alert>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Monitores (como antes) + hits
function NovoMonitor() {
  const qc = useQueryClient();
  const { data: templates = [] } = useQuery({ queryKey: ["templates"], queryFn: () => api.get<Template[]>("/api/query/templates") });
  const [f, setF] = React.useState({ nome: "", query: "", cron: "0 */6 * * *", canal_alerta: "jsonl", webhook_url: "", radar_modo: "termos", ia: true });
  const criar = useMutation({
    mutationFn: () => api.post<Monitor>("/api/monitors", { ...f, webhook_url: f.webhook_url || null }),
    onSuccess: () => {
      setF({ ...f, nome: "", query: "" });
      void qc.invalidateQueries({ queryKey: ["monitors"] });
      void qc.invalidateQueries({ queryKey: ["radar-hits"] });
      void qc.invalidateQueries({ queryKey: ["radar-status"] });
    },
  });
  return (
    <Card>
      <CardTitle>Novo monitor</CardTitle>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); criar.mutate(); }}>
        <Field label="Atalho: template" htmlFor="mtpl">
          <Select id="mtpl" value="" onChange={(e) => { const t = templates.find((x) => String(x.id) === e.target.value); if (t) setF({ ...f, nome: f.nome || t.nome, query: t.query }); }}>
            <option value="">— escolher template —</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.nome}</option>
            ))}
          </Select>
        </Field>
        <Field label="Nome" htmlFor="mnome">
          <Input id="mnome" required value={f.nome} onChange={(e) => setF({ ...f, nome: e.target.value })} />
        </Field>
        <Field label="Query" htmlFor="mquery">
          <Textarea id="mquery" required rows={3} value={f.query} onChange={(e) => setF({ ...f, query: e.target.value })} />
        </Field>
        <Field label="Casamento no Radar" htmlFor="mradar" hint="'termos' ignora site:/-site: (recomendado para feeds de imprensa); 'estrito' exige o domínio.">
          <Select id="mradar" value={f.radar_modo} onChange={(e) => setF({ ...f, radar_modo: e.target.value })}>
            <option value="termos">termos (recomendado)</option>
            <option value="estrito">estrito (respeita site:)</option>
          </Select>
        </Field>
        <Field label="Triagem pela IA" htmlFor="mia" hint="hits deste monitor entram na fila do assistente (quando ele estiver ligado em Tema)">
          <label className="flex h-9 items-center gap-2 text-sm"><input id="mia" type="checkbox" checked={f.ia} onChange={(e) => setF({ ...f, ia: e.target.checked })} /> sim</label>
        </Field>
        <Field label="Cron (min hora dia mês dia-semana) — America/Sao_Paulo" htmlFor="mcron">
          <Input id="mcron" value={f.cron} onChange={(e) => setF({ ...f, cron: e.target.value })} className="font-mono" />
          <div className="mt-1 flex flex-wrap gap-1">
            {CRONS.map((c) => (
              <Button key={c.v} size="sm" variant="ghost" onClick={() => setF({ ...f, cron: c.v })}>{c.l}</Button>
            ))}
          </div>
        </Field>
        <Field label="Canal de alerta (local)" htmlFor="mcanal">
          <Select id="mcanal" value={f.canal_alerta} onChange={(e) => setF({ ...f, canal_alerta: e.target.value })}>
            <option value="jsonl">Arquivo JSONL (data/alerts/)</option>
            <option value="webhook">Webhook HTTP</option>
            <option value="telegram">Telegram (bot configurado no .env)</option>
            <option value="nenhum">Nenhum</option>
          </Select>
        </Field>
        {f.canal_alerta === "webhook" && (
          <Field label="URL do webhook" htmlFor="mhook">
            <Input id="mhook" type="url" required value={f.webhook_url} onChange={(e) => setF({ ...f, webhook_url: e.target.value })} placeholder="http://127.0.0.1:9000/hook" />
          </Field>
        )}
        <Button type="submit" disabled={criar.isPending}>Criar monitor</Button>
        <ErrorText error={criar.error} />
      </form>
    </Card>
  );
}

function Timeline({ monitor }: { monitor: Monitor }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["runs", monitor.id],
    queryFn: () => api.get<MonitorRun[]>(`/api/monitors/${monitor.id}/results`),
    refetchInterval: 15000,
  });
  if (isLoading) return <Empty>Carregando…</Empty>;
  if (!data.length) return <Empty>Nenhuma execução ainda. Use “Executar agora”.</Empty>;
  return (
    <ol className="relative space-y-3 border-l border-border pl-4">
      {data.map((r) => (
        <li key={r.id}>
          <span className={`absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full ${r.status === "ok" ? "bg-success" : "bg-danger"}`} aria-hidden />
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <strong>{formatDate(r.executado_em)}</strong>
            <Badge variant={r.status === "ok" ? "success" : "danger"}>{r.status}</Badge>
          </div>
          <p className="code text-xs text-muted-foreground">{r.log}</p>
          <div className="mt-1">
            <DeeplinkButtons deeplinks={r.deeplinks} query={monitor.query} origem="monitor" />
          </div>
          {Object.keys(r.resultado).length > 0 && (
            <details className="mt-1 text-xs">
              <summary className="cursor-pointer">Resultado</summary>
              <pre className="code max-h-48 overflow-auto rounded bg-muted p-2">{JSON.stringify(r.resultado, null, 2)}</pre>
            </details>
          )}
        </li>
      ))}
    </ol>
  );
}

function HitsDoMonitor({ monitor }: { monitor: Monitor }) {
  const { data: hits = [] } = useQuery({ queryKey: ["radar-hits", "monitor", monitor.id], queryFn: () => api.get<Hit[]>(`/api/monitors/${monitor.id}/hits?limit=30`), refetchInterval: 20000 });
  return (
    <Card>
      <CardTitle>Resultados (hits do Radar) — {monitor.nome} <Badge>{monitor.hits_total}</Badge>{monitor.hits_novos > 0 && <Badge variant="warning">{monitor.hits_novos} não lidos</Badge>}</CardTitle>
      {hits.length === 0 ? (
        <Empty>
          Nada casou ainda com esta query nos itens coletados. Queries com vários grupos (AND) são restritivas: confira os termos em
          "Resultados → Itens coletados" e, para hashtags, veja a fonte Mastodon automática em "Fontes do radar".
        </Empty>
      ) : <ul className="space-y-2">{hits.map((h) => <HitLinha key={h.id} h={h} mostrarMonitor={false} />)}</ul>}
    </Card>
  );
}

function MonitoresTab({ monitores, error }: { monitores: Monitor[]; error: unknown }) {
  const qc = useQueryClient();
  const [sel, setSel] = React.useState<number | null>(null);
  const atual = monitores.find((m) => m.id === sel) ?? monitores[0];
  const inval = () => {
    void qc.invalidateQueries({ queryKey: ["monitors"] });
    void qc.invalidateQueries({ queryKey: ["runs"] });
    void qc.invalidateQueries({ queryKey: ["radar-hits"] });
    void qc.invalidateQueries({ queryKey: ["radar-status"] });
  };
  const run = useMutation({ mutationFn: (id: number) => api.post(`/api/monitors/${id}/run-now`), onSuccess: inval });
  const toggle = useMutation({ mutationFn: (m: Monitor) => api.patch(`/api/monitors/${m.id}`, { ativo: !m.ativo }), onSuccess: inval });
  const toggleIa = useMutation({ mutationFn: (m: Monitor) => api.patch(`/api/monitors/${m.id}`, { ia: !m.ia }), onSuccess: inval });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/monitors/${id}`), onSuccess: inval });
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4"><NovoMonitor /></div>
      <div className="space-y-4 lg:col-span-2">
        <Card>
          <CardTitle>Monitores</CardTitle>
          <ErrorText error={error} />
          {monitores.length === 0 ? (
            <Empty>Nenhum monitor cadastrado.</Empty>
          ) : (
            <ul className="divide-y divide-border">
              {monitores.map((m) => (
                <li key={m.id} className={`flex flex-wrap items-center gap-2 py-2 ${atual?.id === m.id ? "font-semibold" : ""}`}>
                  <button type="button" className="flex-1 text-left" onClick={() => setSel(m.id)} aria-pressed={atual?.id === m.id}>
                    <span className="text-sm">{m.nome}</span> <Badge>{m.tipo}</Badge> <Badge variant={m.ativo ? "success" : "muted"}>{m.ativo ? "ativo" : "pausado"}</Badge>{" "}
                    <Badge variant={m.hits_novos ? "warning" : "muted"}>{m.hits_novos ? `${m.hits_novos} novo(s)` : `${m.hits_total} hit(s)`}</Badge>
                    {m.radar_modo === "estrito" && <Badge variant="accent">estrito</Badge>}
                    {m.ia && <Badge variant="accent">IA</Badge>}
                    <span className="code block text-xs font-normal text-muted-foreground">{m.query}</span>
                    <span className="block text-xs font-normal text-muted-foreground">
                      cron <code>{m.cron}</code> · última {formatDate(m.ultima_execucao)} · próxima {formatDate(m.proxima_execucao)}
                    </span>
                  </button>
                  <Button size="sm" variant="outline" onClick={() => run.mutate(m.id)} disabled={run.isPending} aria-label={`Executar ${m.nome} agora`}>
                    <Zap size={14} /> Executar agora
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => toggleIa.mutate(m)} aria-label={m.ia ? `Tirar ${m.nome} da IA` : `Enviar ${m.nome} à IA`} title={m.ia ? "hits vão para o assistente de IA" : "fora do assistente de IA"}>
                    <Bot size={14} className={m.ia ? "" : "opacity-40"} />
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => toggle.mutate(m)} aria-label={m.ativo ? `Pausar ${m.nome}` : `Ativar ${m.nome}`}>
                    {m.ativo ? <Pause size={14} /> : <Play size={14} />}
                  </Button>
                  <Button size="icon" variant="ghost" onClick={() => del.mutate(m.id)} aria-label={`Excluir ${m.nome}`}>
                    <Trash2 size={14} />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <ErrorText error={run.error ?? toggle.error ?? toggleIa.error ?? del.error} />
        </Card>
        {atual && <HitsDoMonitor monitor={atual} />}
        {atual && (
          <Card>
            <CardTitle>Timeline / logs — {atual.nome}</CardTitle>
            <Timeline monitor={atual} />
          </Card>
        )}
      </div>
    </div>
  );
}

export default function MonitorsPage() {
  const [tab, setTab] = React.useState("monitores");
  const { data: monitores = [], error } = useQuery({ queryKey: ["monitors"], queryFn: () => api.get<Monitor[]>("/api/monitors"), refetchInterval: 15000 });
  const naoLidos = monitores.reduce((n, m) => n + m.hits_novos, 0);
  return (
    <>
      <PageHeader title="Monitores e Radar" description="Vários monitores pesquisando ao mesmo tempo: o Radar coleta fontes públicas e casa cada item novo com a query de cada monitor ativo; cada execução também gera os deeplinks e registra a timeline." />
      <RadarStrip />
      <Tabs
        label="Monitores e Radar"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "monitores", label: "Monitores" },
          { id: "hits", label: naoLidos ? `Resultados (${naoLidos} novos)` : "Resultados" },
          { id: "fontes", label: "Fontes do radar" },
        ]}
      />
      <TabPanel id="monitores" active={tab === "monitores"}><MonitoresTab monitores={monitores} error={error} /></TabPanel>
      <TabPanel id="hits" active={tab === "hits"}><HitsEItens monitores={monitores} /></TabPanel>
      <TabPanel id="fontes" active={tab === "fontes"}><FontesTab /></TabPanel>
    </>
  );
}
