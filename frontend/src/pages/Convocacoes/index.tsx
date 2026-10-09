import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Check, ExternalLink, ImageUp, Link2, Megaphone, Newspaper, Play, RefreshCw, Search, ShieldCheck, Trash2, X } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorText, SearxngStatus } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select, Tabs, TabPanel, Textarea } from "@/components/ui";
import {
  api,
  qs,
  type AnaliseOut,
  type AnaliseResultado,
  type ConvocacoesStatus,
  type Deteccao,
  type FonteConvocacao,
  type FonteConvocacaoTeste,
  type Ocorrencia,
  type ReferenciaCartaz,
  type Severidade,
  type TipoFonteConvocacao,
} from "@/lib/api";
import { cn, formatDate, openExternal } from "@/lib/utils";
import { SEV_LABEL, SEV_VARIANT } from "@/pages/Alertas";
import { BuscaDeteccao } from "@/pages/Convocacoes/Busca";

const CAT_LABEL: Record<string, string> = { convocacao: "convocação", nao_pacifico: "não pacífico", temporal: "quando", local: "onde", distribuicao: "distribuição" };
const CAT_VARIANT: Record<string, "muted" | "default" | "warning" | "danger" | "accent" | "success"> = { convocacao: "default", nao_pacifico: "danger", temporal: "accent", local: "muted", distribuicao: "warning" };
const COMP_LABEL: Record<string, string> = { lexico: "Léxico (OCR + texto)", visual: "Visual (CLIP)", referencia: "Semelhança c/ confirmados", monitor: "Queries dos monitores" };
const PLATAFORMAS = ["desconhecida", "x", "instagram", "facebook", "bluesky", "telegram", "tiktok", "mastodon", "web"];
const TIPOS_FONTE: { id: TipoFonteConvocacao; l: string; placeholder: string; dica: string }[] = [
  { id: "bluesky_busca", l: "Bluesky — busca", placeholder: 'ex.: "ato não pacífico" OR "revolta nas ruas"', dica: "API pública do Bluesky, sem login. Texto + alt-text + imagens dos posts." },
  { id: "telegram_canal", l: "Telegram — canal público", placeholder: "ex.: @movimentobrasil ou https://t.me/canal", dica: "Pré-visualização pública t.me/s/<canal> (sem login). Posts, fotos e links de grupo." },
  { id: "searxng_imagens", l: "SearXNG — imagens (X/Instagram/Facebook via Bing/DDG)", placeholder: 'ex.: site:x.com "ato não pacífico"', dica: "Imagens indexadas pelos buscadores. Rendimento baixo e irregular para X/Instagram/Facebook — use também a aba Analisar." },
  { id: "feed_midia", l: "Feeds do Radar com imagem (Mastodon, imprensa)", placeholder: "(sem parâmetro)", dica: "Analisa as imagens (enclosure/media:content) dos itens novos das fontes RSS do Radar." },
];

const inval = (qc: ReturnType<typeof useQueryClient>) => {
  for (const k of ["convocacoes", "convocacoes-status", "alertas", "alertas-contagem", "referencias", "fontes-conv", "invites", "boletim", "agenda"]) void qc.invalidateQueries({ queryKey: [k] });
};

// ------------------------------------------------------------------ pontuação
function ScoreBar({ score, severidade }: { score: number; severidade: Severidade }) {
  const cor = severidade === "critica" ? "bg-danger" : severidade === "alta" ? "bg-warning" : severidade === "media" ? "bg-primary" : "bg-muted-foreground";
  return (
    <div className="flex items-center gap-2" aria-label={`score ${score} de 100`}>
      <div className="h-2 w-28 overflow-hidden rounded bg-muted"><div className={cn("h-2", cor)} style={{ width: `${score}%` }} /></div>
      <span className="text-sm font-bold tabular-nums">{score}</span>
      <Badge variant={SEV_VARIANT[severidade]}>{SEV_LABEL[severidade]}</Badge>
    </div>
  );
}

export function ScoreBreakdown({ r }: { r: AnaliseResultado }) {
  const comps = Object.entries(r.decomposicao.componentes);
  return (
    <div className="space-y-2 text-sm">
      <ul className="space-y-1">
        {comps.map(([k, c]) => (
          <li key={k} className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1">
            <span>{COMP_LABEL[k] ?? k}</span>
            <span className="code text-xs text-muted-foreground">{c.valor} × {c.peso} = <strong className="text-foreground">{c.parcela}</strong></span>
          </li>
        ))}
        {r.decomposicao.bonus_distribuicao > 0 && (
          <li className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1"><span>Bônus: QR code / link de grupo no cartaz</span><strong>+{r.decomposicao.bonus_distribuicao}</strong></li>
        )}
      </ul>
      <p className="text-xs text-muted-foreground">
        {r.lexico.noticiando ? "Parece cobertura jornalística (não convocação): " + r.lexico.pistas_noticiando.join(", ") + "." : r.lexico.pistas_convocando.length ? "Pistas de convocação: " + r.lexico.pistas_convocando.join(", ") + "." : ""}
        {!r.capacidades.ocr && r.imagem && " OCR indisponível neste perfil — o texto da imagem não foi lido."}
        {r.ocr && r.ocr.confianca < 0.4 && " OCR fraco — confira o print."}
        {r.referencia && r.referencia.id && ` Semelhante à referência #${r.referencia.id} (${r.referencia.motivo}).`}
      </p>
    </div>
  );
}

function TermosChips({ termos }: { termos: Record<string, string[]> }) {
  const cats = Object.entries(termos).filter(([, v]) => v.length);
  if (!cats.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {cats.map(([cat, ts]) => ts.slice(0, 6).map((t) => <Badge key={cat + t} variant={CAT_VARIANT[cat] ?? "muted"} title={CAT_LABEL[cat] ?? cat}>{t}</Badge>))}
    </div>
  );
}

// ------------------------------------------------------------------ status
function StatusStrip() {
  const qc = useQueryClient();
  const { data: st, error } = useQuery({ queryKey: ["convocacoes-status"], queryFn: () => api.get<ConvocacoesStatus>("/api/convocacoes/status"), refetchInterval: 15000 });
  const ciclo = useMutation({ mutationFn: () => api.post<{ analisados: number; novos: number; alertas: number }>("/api/convocacoes/ciclo"), onSuccess: () => inval(qc) });
  if (!st) return <ErrorText error={error} />;
  const Stat = ({ v, l }: { v: React.ReactNode; l: string }) => (
    <div className="rounded-md border border-border px-3 py-2"><div className="text-lg font-bold leading-tight">{v}</div><div className="text-xs text-muted-foreground">{l}</div></div>
  );
  const c = st.capacidades;
  return (
    <Card className="mb-4">
      <div className="flex flex-wrap items-center gap-2">
        <CardTitle className="mb-0 flex items-center gap-2"><Megaphone size={18} aria-hidden /> Convocações</CardTitle>
        <Badge variant={st.ativo && st.agendado ? "success" : st.ativo ? "warning" : "muted"}>
          {st.ativo ? (st.agendado ? `coletor ligado · a cada ${st.intervalo_min} min` : "ligado (agendador desligado neste processo)") : "coletor desligado em Tema"}
        </Badge>
        <Badge variant={c.perfil === "completo" ? "accent" : "muted"} title={`OCR ${c.ocr_instalado ? "instalado" : "ausente"} · CLIP ${c.clip_instalado ? "instalado" : "ausente"} · ${c.rss_mb} MB RSS`}>
          perfil {c.perfil} · OCR {c.ocr_instalado ? (c.ocr_modelo ?? "ok") : "ausente"} · CLIP {c.clip_instalado ? "ok" : "ausente"}
        </Badge>
        <span className="flex-1" />
        <Button size="sm" onClick={() => ciclo.mutate()} disabled={ciclo.isPending}>
          <RefreshCw size={14} className={ciclo.isPending ? "animate-spin" : ""} /> {ciclo.isPending ? "Coletando e analisando…" : "Rodar ciclo agora"}
        </Button>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat v={<span className={st.por_severidade.critica ? "text-danger" : ""}>{st.por_severidade.critica}</span>} l="críticas na fila" />
        <Stat v={<span className={st.por_severidade.alta ? "text-warning" : ""}>{st.por_severidade.alta}</span>} l="altas na fila" />
        <Stat v={st.novas} l={`novas (de ${st.deteccoes_total})`} />
        <Stat v={`${st.fontes_ativas}/${st.fontes_total}`} l="fontes ativas" />
        <Stat v={st.referencias} l="cartazes confirmados" />
        <Stat v={st.ultimo_ciclo ? `${st.ultimo_ciclo.analisados} img` : "—"} l={st.ultimo_ciclo ? `último ciclo ${formatDate(st.ultimo_ciclo.executado_em)}` : st.proximo_ciclo ? `próximo ${formatDate(st.proximo_ciclo)}` : "sem ciclo neste processo"} />
      </div>
      {c.rss_mb > 1500 && <div className="mt-2"><Alert variant="warning">Processo usando {c.rss_mb} MB. Os modelos são descarregados após ociosidade; para liberar agora use "Descarregar modelos" em Fontes.</Alert></div>}
      <ErrorText error={ciclo.error} />
      {ciclo.data && <p className="mt-2 text-sm">Ciclo concluído: {ciclo.data.analisados} imagem(ns) analisada(s), {ciclo.data.novos} nova(s), {ciclo.data.alertas} alerta(s).</p>}
    </Card>
  );
}

// ------------------------------------------------------------------ fila
function DeteccaoLinha({ d, destaque }: { d: Deteccao; destaque?: boolean }) {
  const qc = useQueryClient();
  const [aberto, setAberto] = React.useState(!!destaque);
  const [busca, setBusca] = React.useState(false);
  const confirmar = useMutation({ mutationFn: () => api.post(`/api/convocacoes/${d.id}/confirmar`, { rotulo: "" }), onSuccess: () => inval(qc) });
  const descartar = useMutation({ mutationFn: () => api.post(`/api/convocacoes/${d.id}/descartar`, { motivo: "" }), onSuccess: () => inval(qc) });
  const boletim = useMutation({ mutationFn: () => api.post(`/api/convocacoes/${d.id}/boletim`, { secao: "manifestacao" }), onSuccess: () => inval(qc) });
  const agenda = useMutation({ mutationFn: () => api.post(`/api/convocacoes/${d.id}/agenda`, {}), onSuccess: () => inval(qc) });
  const remover = useMutation({ mutationFn: () => api.del(`/api/convocacoes/${d.id}`), onSuccess: () => inval(qc) });
  const { data: oc } = useQuery({ queryKey: ["ocorrencias", d.id], queryFn: () => api.get<Ocorrencia[]>(`/api/convocacoes/${d.id}/ocorrencias`), enabled: aberto && d.ocorrencias > 1 });
  const texto = d.texto_ocr || d.texto_post;
  return (
    <li id={`det-${d.id}`} className={cn("rounded-md border border-border p-3 text-sm", d.estado === "descartada" && "opacity-60", destaque && "ring-2 ring-accent")}>
      <div className="flex gap-3">
        {d.evidencia_id ? (
          <a href={`/api/evidence/${d.evidencia_id}/download?inline=true`} target="_blank" rel="noopener noreferrer" className="shrink-0">
            <img src={`/api/convocacoes/${d.id}/miniatura`} alt={`miniatura da detecção ${d.id}`} className="h-24 w-24 rounded object-cover" loading="lazy" />
          </a>
        ) : (
          <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded bg-muted text-xs text-muted-foreground">só texto</div>
        )}
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <ScoreBar score={d.score} severidade={d.severidade} />
            <Badge>{d.plataforma}</Badge>
            {d.nao_pacifico && <Badge variant="danger">não pacífico</Badge>}
            {d.noticiando && <Badge variant="muted">parece notícia</Badge>}
            {d.estado !== "nova" && <Badge variant={d.estado === "confirmada" ? "success" : "muted"}>{d.estado}</Badge>}
            {d.ocorrencias > 1 && <Badge variant="accent">{d.ocorrencias} ocorrências</Badge>}
            <span className="ml-auto text-xs text-muted-foreground">{formatDate(d.criado_em)}</span>
          </div>
          <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
            {d.data_evento && <span>📅 {d.data_evento.split("-").reverse().join("/")}{d.hora_evento ? ` ${d.hora_evento}` : ""} ({d.tempo})</span>}
            {d.local_evento && <span>📍 {d.local_evento}</span>}
            {d.autor && <span>{d.autor}</span>}
            {d.termos_monitor && <span className="code">monitores: {d.termos_monitor}</span>}
          </div>
          <TermosChips termos={d.termos_lexico} />
          {texto && <p className="text-muted-foreground">{texto.slice(0, aberto ? 2000 : 220)}{texto.length > 220 && !aberto ? "…" : ""}</p>}
          {(d.qr.length > 0 || d.convites.length > 0) && (
            <p className="code text-xs"><Link2 size={12} className="inline" /> {[...d.convites.map((c) => c.url), ...d.qr.filter((q) => !d.convites.some((c) => c.url === q))].join(" · ")} <Link to="/invites" className="text-primary underline">(ver em Convites)</Link></p>
          )}
          {aberto && oc && oc.length > 0 && (
            <ul className="rounded bg-muted p-2 text-xs">
              <li className="font-medium">Propagação (mesma arte em outros posts):</li>
              {oc.map((o) => <li key={o.id}><Badge variant="muted">{o.plataforma}</Badge> <a className="text-primary underline" href={o.post_url} target="_blank" rel="noopener noreferrer">{o.post_url}</a> {o.variante && "(variante)"} · {formatDate(o.visto_em)}</li>)}
            </ul>
          )}
          <div className="flex flex-wrap items-center gap-1 pt-1">
            {d.estado !== "confirmada" && <Button size="sm" variant="outline" disabled={confirmar.isPending} onClick={() => confirmar.mutate()} title="Marca como convocação real e usa como referência de semelhança"><Check size={14} /> Confirmar</Button>}
            {d.estado !== "descartada" && <Button size="sm" variant="ghost" disabled={descartar.isPending} onClick={() => descartar.mutate()}><X size={14} /> Descartar</Button>}
            {!d.boletim_item_id ? <Button size="sm" variant="ghost" disabled={boletim.isPending} onClick={() => boletim.mutate()}><Newspaper size={14} /> Boletim</Button> : <Badge variant="success">no boletim #{d.boletim_item_id}</Badge>}
            {!d.agenda_evento_id ? <Button size="sm" variant="ghost" disabled={agenda.isPending} onClick={() => agenda.mutate()}><CalendarPlus size={14} /> Agenda</Button> : <Badge variant="success">agenda #{d.agenda_evento_id}</Badge>}
            <Button size="sm" variant={busca ? "default" : "outline"} onClick={() => setBusca(!busca)} aria-expanded={busca} title="Termos do cartaz → convites abertos, menções e monitor"><Search size={14} /> Buscar na internet</Button>
            {d.post_url && <Button size="sm" variant="ghost" onClick={() => openExternal(d.post_url)}><ExternalLink size={14} /> Abrir post</Button>}
            <Button size="sm" variant="ghost" onClick={() => setAberto(!aberto)}>{aberto ? "Menos" : "Mais"}</Button>
            <Button size="icon" variant="ghost" aria-label="Excluir detecção" onClick={() => { if (confirm("Excluir esta detecção? A evidência permanece em Evidências.")) remover.mutate(); }}><Trash2 size={14} /></Button>
          </div>
          <ErrorText error={confirmar.error ?? descartar.error ?? boletim.error ?? agenda.error ?? remover.error} />
          {busca && <BuscaDeteccao d={d} />}
        </div>
      </div>
    </li>
  );
}

function FilaTab({ destaqueId }: { destaqueId: number | null }) {
  const [estado, setEstado] = React.useState("nova");
  const [sev, setSev] = React.useState("");
  const [plat, setPlat] = React.useState("");
  const { data = [], error } = useQuery({
    queryKey: ["convocacoes", estado, sev, plat],
    queryFn: () => api.get<Deteccao[]>(`/api/convocacoes${qs({ estado, severidade: sev, plataforma: plat, limit: 200 })}`),
    refetchInterval: 20000,
  });
  React.useEffect(() => {
    if (destaqueId) document.getElementById(`det-${destaqueId}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [destaqueId, data.length]);
  return (
    <Card>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Select aria-label="Estado" className="w-40" value={estado} onChange={(e) => setEstado(e.target.value)}>
          <option value="nova">Novas</option><option value="confirmada">Confirmadas</option><option value="descartada">Descartadas</option><option value="">Todas</option>
        </Select>
        <Select aria-label="Severidade" className="w-40" value={sev} onChange={(e) => setSev(e.target.value)}>
          <option value="">Qualquer severidade</option><option value="critica">Crítica</option><option value="alta">Alta</option><option value="media">Média</option><option value="baixa">Baixa</option>
        </Select>
        <Select aria-label="Plataforma" className="w-40" value={plat} onChange={(e) => setPlat(e.target.value)}>
          <option value="">Toda plataforma</option>{PLATAFORMAS.map((p) => <option key={p} value={p}>{p}</option>)}
        </Select>
        <span className="text-xs text-muted-foreground">{data.length} detecção(ões), ordenadas por score</span>
      </div>
      <ErrorText error={error} />
      {data.length === 0 ? <Empty>Nenhuma detecção. Use a aba Analisar (print/URL) ou cadastre fontes e rode um ciclo.</Empty> : <ul className="space-y-2">{data.map((d) => <DeteccaoLinha key={d.id} d={d} destaque={d.id === destaqueId} />)}</ul>}
    </Card>
  );
}

// ------------------------------------------------------------------ analisar
function AnalisarTab() {
  const qc = useQueryClient();
  const [file, setFile] = React.useState<File | null>(null);
  const [preview, setPreview] = React.useState<string | null>(null);
  const [url, setUrl] = React.useState("");
  const [texto, setTexto] = React.useState("");
  const [plataforma, setPlataforma] = React.useState("");
  const [salvar, setSalvar] = React.useState(true);
  const [drag, setDrag] = React.useState(false);
  React.useEffect(() => {
    if (!file) return setPreview(null);
    const u = URL.createObjectURL(file);
    setPreview(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);
  const analisar = useMutation({
    mutationFn: () => {
      const fd = new FormData();
      if (file) fd.append("arquivo", file);
      if (url.trim()) fd.append("url", url.trim());
      if (texto.trim()) fd.append("texto", texto.trim());
      if (plataforma) fd.append("plataforma", plataforma);
      fd.append("salvar", String(salvar));
      return api.post<AnaliseOut>("/api/convocacoes/analisar", fd);
    },
    onSuccess: () => inval(qc),
  });
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer.files?.[0];
    if (f?.type.startsWith("image/")) setFile(f);
  };
  const onPaste = (e: React.ClipboardEvent) => {
    const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith("image/"));
    const f = item?.getAsFile();
    if (f) setFile(f);
  };
  const r = analisar.data;
  return (
    <div className="grid gap-4 lg:grid-cols-2" onPaste={onPaste}>
      <Card>
        <CardTitle>Print, URL ou texto</CardTitle>
        <div
          role="button"
          tabIndex={0}
          aria-label="Área para soltar ou colar um print"
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          onClick={() => document.getElementById("conv-file")?.click()}
          onKeyDown={(e) => e.key === "Enter" && document.getElementById("conv-file")?.click()}
          className={cn("mb-3 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-border p-4 text-center text-sm", drag && "border-primary bg-muted")}
        >
          {preview ? <img src={preview} alt="pré-visualização" className="max-h-72 rounded" /> : <><ImageUp size={28} aria-hidden /><p className="mt-2">Solte o print aqui, cole (Ctrl+V) ou clique para escolher</p><p className="text-xs text-muted-foreground">X, Instagram e Facebook não têm página pública sem login: o print é o caminho confiável.</p></>}
          <input id="conv-file" type="file" accept="image/*" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>
        {file && <Button size="sm" variant="ghost" onClick={() => setFile(null)}>Remover imagem</Button>}
        <div className="mt-3 space-y-3">
          <Field label="URL do post ou da imagem (opcional)" htmlFor="conv-url" hint="Imagem direta, post do Bluesky (API pública), t.me/<canal>/<id>, página com og:image. Com print, a URL vira a origem da evidência.">
            <Input id="conv-url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://bsky.app/profile/…/post/… · https://t.me/canal/123 · https://…/imagem.jpg" />
          </Field>
          <Field label="Texto do post / legenda (opcional)" htmlFor="conv-texto" hint="Entra na pontuação junto com o texto lido da imagem (OCR).">
            <Textarea id="conv-texto" rows={3} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="Cole aqui a legenda, o tweet, a descrição…" />
          </Field>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Plataforma" htmlFor="conv-plat">
              <Select id="conv-plat" value={plataforma} onChange={(e) => setPlataforma(e.target.value)}><option value="">auto</option>{PLATAFORMAS.map((p) => <option key={p} value={p}>{p}</option>)}</Select>
            </Field>
            <label className="flex h-9 items-center gap-1 text-sm"><input type="checkbox" checked={salvar} onChange={(e) => setSalvar(e.target.checked)} /> salvar na fila (evidência + alerta)</label>
            <Button onClick={() => analisar.mutate()} disabled={analisar.isPending || (!file && !url.trim() && !texto.trim())}>
              <Play size={14} className={analisar.isPending ? "animate-pulse" : ""} /> {analisar.isPending ? "Analisando (OCR em CPU)…" : "Analisar"}
            </Button>
          </div>
        </div>
        <ErrorText error={analisar.error} />
      </Card>
      <Card>
        <CardTitle>Resultado</CardTitle>
        {!r ? (
          <Empty>O resultado mostra a pontuação decomposta, o texto lido, QR codes, links de grupo e os monitores que casaram.</Empty>
        ) : (
          <div className="space-y-3 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <ScoreBar score={r.score} severidade={r.severidade} />
              {r.duplicada && <Badge variant="accent">imagem já conhecida → nova ocorrência</Badge>}
              {r.salva && r.deteccao && <Badge variant="success">salva #{r.deteccao.id}</Badge>}
              {r.alerta_id && <Link to="/alertas" className="text-primary underline">alerta #{r.alerta_id}</Link>}
              <span className="ml-auto text-xs text-muted-foreground">{r.resultado.ms} ms</span>
            </div>
            <ScoreBreakdown r={r.resultado} />
            <TermosChips termos={r.resultado.lexico.termos} />
            <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
              {r.resultado.lexico.data_evento && <span>📅 {r.resultado.lexico.data_evento.split("-").reverse().join("/")}{r.resultado.lexico.hora_evento ? ` ${r.resultado.lexico.hora_evento}` : ""} ({r.resultado.lexico.tempo})</span>}
              {r.resultado.lexico.local && <span>📍 {r.resultado.lexico.local}</span>}
              {r.resultado.visual && <span>CLIP: {Object.entries(r.resultado.visual).map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(" · ")}</span>}
            </div>
            {r.resultado.monitores.length > 0 && <p className="code text-xs">monitores: {r.resultado.monitores.map((m) => `${m.nome} (${m.termos.join(", ")})`).join("; ")}</p>}
            {r.resultado.ocr && (
              <details open>
                <summary className="cursor-pointer text-xs text-muted-foreground">Texto lido da imagem (OCR {r.resultado.ocr.modelo}, confiança {(r.resultado.ocr.confianca * 100).toFixed(0)}%, {r.resultado.ocr.ms} ms)</summary>
                <pre className="mt-1 whitespace-pre-wrap rounded bg-muted p-2 text-xs">{r.resultado.ocr.texto || "(nada legível)"}</pre>
              </details>
            )}
            {(r.resultado.qr.length > 0 || r.resultado.convites.length > 0) && (
              <div className="rounded border border-border p-2">
                <p className="mb-1 font-medium"><Link2 size={14} className="inline" /> Links/QR encontrados</p>
                <ul className="code space-y-1 text-xs">
                  {r.resultado.convites.map((c) => <li key={c.url}><Badge variant="success">{c.plataforma}</Badge> {c.url}</li>)}
                  {r.resultado.qr.filter((q) => !r.resultado.convites.some((c) => c.url === q)).map((q) => <li key={q}><Badge>QR</Badge> {q}</li>)}
                </ul>
                <p className="mt-1 text-xs text-muted-foreground">{r.salva ? "Convites já registrados na aba Convites (teste-os lá)." : "Marque \"salvar\" para registrar em Convites."} <Link to="/invites" className="text-primary underline">Abrir Convites</Link></p>
              </div>
            )}
            {r.resultado.passos && <p className="code text-[11px] text-muted-foreground">{r.resultado.passos.join(" → ")}</p>}
            {!r.resultado.capacidades.ocr && r.resultado.imagem && <Alert variant="warning">OCR não instalado: rode <span className="code">./run.sh</span> (instala rapidocr) para ler o texto das imagens.</Alert>}
          </div>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ referências
function ReferenciasTab() {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["referencias"], queryFn: () => api.get<ReferenciaCartaz[]>("/api/convocacoes/referencias") });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/convocacoes/referencias/${id}`), onSuccess: () => inval(qc) });
  return (
    <Card>
      <CardTitle>Cartazes confirmados ({data.length})</CardTitle>
      <p className="mb-3 text-xs text-muted-foreground">Cada cartaz confirmado vira referência: novas imagens iguais (pHash) ou semelhantes (CLIP, perfil completo) ganham pontos e aparecem como propagação.</p>
      {data.length === 0 ? <Empty>Nenhuma referência. Confirme uma detecção na Fila.</Empty> : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data.map((r) => (
            <li key={r.id} className="rounded-md border border-border p-2 text-sm">
              {r.deteccao_id && <img src={`/api/convocacoes/${r.deteccao_id}/miniatura`} alt={r.rotulo} className="mb-2 h-40 w-full rounded object-cover" loading="lazy" />}
              <div className="flex items-center gap-2"><strong className="truncate">{r.rotulo || `referência #${r.id}`}</strong>{r.tem_embedding && <Badge variant="accent">CLIP</Badge>}</div>
              <p className="code text-xs text-muted-foreground">phash {r.phash} · {formatDate(r.criado_em)}</p>
              <div className="mt-1 flex gap-1">
                {r.deteccao_id && <Link to={`/convocacoes?deteccao=${r.deteccao_id}`} className="inline-flex h-8 items-center rounded-md px-3 text-xs hover:bg-muted">Ver detecção</Link>}
                <Button size="icon" variant="ghost" aria-label="Remover referência" onClick={() => del.mutate(r.id)}><Trash2 size={14} /></Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ fontes
function FontesTab() {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["fontes-conv"], queryFn: () => api.get<FonteConvocacao[]>("/api/convocacoes/fontes") });
  const [tipo, setTipo] = React.useState<TipoFonteConvocacao>("bluesky_busca");
  const [nome, setNome] = React.useState("");
  const [parametro, setParametro] = React.useState("");
  const [rede, setRede] = React.useState("");
  const [robots, setRobots] = React.useState(true);
  const def = TIPOS_FONTE.find((t) => t.id === tipo)!;
  const criar = useMutation({
    mutationFn: () => api.post<FonteConvocacao>("/api/convocacoes/fontes", { nome: nome || `${def.l}: ${parametro}`.slice(0, 120), tipo, parametro, rede_alvo: rede, respeitar_robots: robots }),
    onSuccess: () => { setNome(""); setParametro(""); inval(qc); },
  });
  const testar = useMutation({ mutationFn: () => api.post<FonteConvocacaoTeste>("/api/convocacoes/fontes/testar", { tipo, parametro, respeitar_robots: robots }) });
  const patch = useMutation({ mutationFn: ({ id, body }: { id: number; body: Partial<FonteConvocacao> }) => api.patch(`/api/convocacoes/fontes/${id}`, body), onSuccess: () => inval(qc) });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/convocacoes/fontes/${id}`), onSuccess: () => inval(qc) });
  const coletar = useMutation({ mutationFn: (id: number) => api.post(`/api/convocacoes/fontes/${id}/coletar`), onSuccess: () => inval(qc) });
  const descarregar = useMutation({ mutationFn: () => api.post<{ liberados: string[] }>("/api/convocacoes/descarregar"), onSuccess: () => inval(qc) });
  const t = testar.data;
  return (
    <div className="space-y-4">
      <Alert variant="info">
        <span className="inline-flex items-center gap-1 font-medium"><ShieldCheck size={14} aria-hidden /> Só fontes públicas, sem login:</span> API pública do Bluesky, pré-visualização pública de canais do Telegram,
        feeds RSS e imagens indexadas pelo Bing/DDG via SearXNG local. <strong>X, Instagram e Facebook</strong> não expõem posts sem login — a cobertura automática por imagens indexadas é baixa e
        irregular; para essas redes use a aba <strong>Analisar</strong> (print ou URL) e os deeplinks de busca. Downloads passam pelo scraper ético (robots.txt, 1 req/3 s, backoff).
      </Alert>
      <SearxngStatus />
      <Card>
        <CardTitle>Nova fonte</CardTitle>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Tipo" htmlFor="f-tipo" hint={def.dica}>
            <Select id="f-tipo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoFonteConvocacao)}>{TIPOS_FONTE.map((x) => <option key={x.id} value={x.id}>{x.l}</option>)}</Select>
          </Field>
          <Field label="Parâmetro (termo, @canal ou dork)" htmlFor="f-param">
            <Input id="f-param" value={parametro} onChange={(e) => setParametro(e.target.value)} placeholder={def.placeholder} disabled={tipo === "feed_midia"} />
          </Field>
          <Field label="Nome (opcional)" htmlFor="f-nome"><Input id="f-nome" value={nome} onChange={(e) => setNome(e.target.value)} /></Field>
          <Field label="Rede alvo (rótulo)" htmlFor="f-rede">
            <Select id="f-rede" value={rede} onChange={(e) => setRede(e.target.value)}><option value="">—</option>{PLATAFORMAS.filter((p) => p !== "desconhecida").map((p) => <option key={p} value={p}>{p}</option>)}</Select>
          </Field>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={robots} onChange={(e) => setRobots(e.target.checked)} /> respeitar robots.txt</label>
          <Button variant="outline" size="sm" disabled={testar.isPending || (tipo !== "feed_midia" && !parametro.trim())} onClick={() => testar.mutate()}>{testar.isPending ? "Testando…" : "Testar (sem gravar)"}</Button>
          <Button size="sm" disabled={criar.isPending || (tipo !== "feed_midia" && !parametro.trim())} onClick={() => criar.mutate()}>Cadastrar fonte</Button>
          <span className="flex-1" />
          <Button size="sm" variant="ghost" onClick={() => descarregar.mutate()} title="Libera a RAM dos modelos de OCR/CLIP agora">Descarregar modelos</Button>
        </div>
        <ErrorText error={criar.error ?? testar.error} />
        {t && (
          <div className="mt-3 rounded-md border border-border p-2 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={t.ok ? "success" : "danger"}>{t.ok ? `HTTP ${t.status}` : t.erro ?? "falhou"}</Badge>
              <Badge variant={t.robots_permite ? "muted" : "warning"}>{t.robots_permite ? "robots.txt permite" : "robots.txt NÃO permite (decisão do analista: desmarque \"respeitar\")"}</Badge>
              <span>{t.candidatos} post(s), {t.com_imagem} com imagem</span>
            </div>
            {t.amostra.length > 0 && <ul className="mt-2 space-y-1 text-xs">{t.amostra.map((a) => <li key={a.post_url}><a className="text-primary underline" href={a.post_url} target="_blank" rel="noopener noreferrer">{a.post_url}</a> {a.autor} — {a.texto.slice(0, 120)} {a.imagens.length > 0 && <Badge>{a.imagens.length} img</Badge>}</li>)}</ul>}
          </div>
        )}
      </Card>
      <Card>
        <CardTitle>Fontes cadastradas ({data.length})</CardTitle>
        {data.length === 0 ? <Empty>Nenhuma fonte. A fonte "Feeds do Radar com imagem" é criada automaticamente no primeiro ciclo.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Fontes do coletor de convocações</caption>
              <thead className="text-xs text-muted-foreground"><tr><th className="p-2">Fonte</th><th className="p-2">Tipo</th><th className="p-2">Parâmetro</th><th className="p-2">Última coleta</th><th className="p-2">Total / últimos</th><th className="p-2"><span className="sr-only">Ações</span></th></tr></thead>
              <tbody>
                {data.map((f) => (
                  <tr key={f.id} className={cn("border-t border-border align-top", !f.ativa && "opacity-60")}>
                    <td className="p-2"><strong>{f.nome}</strong>{f.rede_alvo && <Badge className="ml-1">{f.rede_alvo}</Badge>}{!f.respeitar_robots && <Badge variant="warning" className="ml-1">ignora robots</Badge>}</td>
                    <td className="p-2 text-xs">{TIPOS_FONTE.find((x) => x.id === f.tipo)?.l ?? f.tipo}</td>
                    <td className="code p-2 text-xs">{f.parametro || "—"}</td>
                    <td className="p-2 text-xs">{formatDate(f.ultima_coleta)}{f.ultimo_status ? <> · HTTP {f.ultimo_status}</> : null}{f.ultimo_erro && <p className="text-danger">{f.ultimo_erro}</p>}</td>
                    <td className="p-2 text-xs">{f.itens_total} / {f.novos_ultima}</td>
                    <td className="p-2">
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => coletar.mutate(f.id)} disabled={coletar.isPending} title="Coletar só esta fonte agora"><Play size={14} /></Button>
                        <Button size="sm" variant="ghost" onClick={() => patch.mutate({ id: f.id, body: { ativa: !f.ativa } })}>{f.ativa ? "Desativar" : "Ativar"}</Button>
                        <Button size="icon" variant="ghost" aria-label={`Excluir ${f.nome}`} onClick={() => del.mutate(f.id)}><Trash2 size={14} /></Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <ErrorText error={coletar.error ?? patch.error} />
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ página
export default function ConvocacoesPage() {
  const [params] = useSearchParams();
  const destaque = params.get("deteccao") ? Number(params.get("deteccao")) : null;
  const [tab, setTab] = React.useState(destaque ? "fila" : "analisar");
  const { data: st } = useQuery({ queryKey: ["convocacoes-status"], queryFn: () => api.get<ConvocacoesStatus>("/api/convocacoes/status") });
  return (
    <>
      <PageHeader title="Convocações" description="Detecta cartazes e postagens que convocam para atos (em especial não pacíficos): OCR + léxico + QR + semelhança, com alerta por severidade. Só fontes públicas; nunca entra em grupo." />
      <StatusStrip />
      <Tabs
        label="Seções de Convocações"
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "analisar", label: "Analisar" },
          { id: "fila", label: `Fila${st?.novas ? ` (${st.novas})` : ""}` },
          { id: "referencias", label: "Referências" },
          { id: "fontes", label: "Fontes" },
        ]}
      />
      <TabPanel id="analisar" active={tab === "analisar"}><AnalisarTab /></TabPanel>
      <TabPanel id="fila" active={tab === "fila"}><FilaTab destaqueId={destaque} /></TabPanel>
      <TabPanel id="referencias" active={tab === "referencias"}><ReferenciasTab /></TabPanel>
      <TabPanel id="fontes" active={tab === "fontes"}><FontesTab /></TabPanel>
    </>
  );
}
