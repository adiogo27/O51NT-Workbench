import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Terminal } from "lucide-react";
import * as React from "react";
import { ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Field, Input, PageHeader, Select } from "@/components/ui";
import { api, qs, type Ferramenta, type FerramentaExecucao, type FerramentaResultado, type FerramentaServidor } from "@/lib/api";
import { formatDate, openExternal } from "@/lib/utils";

const GRUPO_LABEL: Record<FerramentaServidor["grupo"], string> = { infra: "domínio e infraestrutura", perfis: "perfis públicos", midia: "mídia e metadados", sensivel: "sensíveis (LGPD)" };

/** Ferramentas OSINT instaladas no servidor (as do Kali), com lista de permissão e auditoria. */
function FerramentasServidor() {
  const qc = useQueryClient();
  const { data, error } = useQuery({ queryKey: ["ferramentas-servidor"], queryFn: () => api.get<{ ferramentas: FerramentaServidor[]; instaladas: number; sensiveis_ativas: boolean }>("/api/ferramentas") });
  const { data: historico = [] } = useQuery({ queryKey: ["ferramentas-historico"], queryFn: () => api.get<FerramentaExecucao[]>("/api/ferramentas/historico?limit=20") });
  const [id, setId] = React.useState("whois");
  const [alvo, setAlvo] = React.useState("");
  const exec = useMutation({ mutationFn: () => api.post<FerramentaResultado>("/api/ferramentas/executar", { ferramenta: id, alvo }), onSuccess: () => void qc.invalidateQueries({ queryKey: ["ferramentas-historico"] }) });
  const atual = data?.ferramentas.find((f) => f.id === id);
  return (
    <Card className="mb-8">
      <CardTitle className="flex items-center gap-2"><Terminal size={18} aria-hidden /> Ferramentas OSINT do servidor ({data?.instaladas ?? 0} instaladas)</CardTitle>
      <p className="mb-3 text-xs text-muted-foreground">Rodam na VPS sem shell, com alvo validado, tempo limite e registro de quem pediu. Só OSINT passivo sobre dados públicos; varredura e ataque ficam fora.</p>
      <ErrorText error={error} />
      <form className="grid gap-3 sm:grid-cols-3" onSubmit={(e) => { e.preventDefault(); exec.mutate(); }}>
        <Field label="Ferramenta local" htmlFor="fs-id">
          <Select id="fs-id" value={id} onChange={(e) => setId(e.target.value)}>
            {(data?.ferramentas ?? []).map((f) => <option key={f.id} value={f.id} disabled={!f.instalada || !f.habilitada}>{f.nome}{!f.instalada ? " (não instalada)" : !f.habilitada ? " (desligada)" : ""}</option>)}
          </Select>
        </Field>
        <Field label="Alvo da ferramenta" htmlFor="fs-alvo" hint={atual ? `${atual.tipo_alvo} · ex.: ${atual.exemplo} · grupo: ${GRUPO_LABEL[atual.grupo]}` : undefined}>
          <Input id="fs-alvo" value={alvo} onChange={(e) => setAlvo(e.target.value)} placeholder={atual?.exemplo} />
        </Field>
        <div className="flex items-end"><Button type="submit" disabled={exec.isPending || !alvo || !atual?.instalada || !atual?.habilitada}>{exec.isPending ? "Executando…" : "Executar"}</Button></div>
      </form>
      {atual && <p className="mt-1 text-xs text-muted-foreground">{atual.descricao}{atual.sensivel ? " — dado pessoal de terceiros: use só com base legal e registre a finalidade." : ""}</p>}
      <ErrorText error={exec.error} />
      {exec.data && (
        <div className="mt-3">
          <Alert variant={exec.data.ok ? "success" : "error"}>{exec.data.ok ? `Concluído em ${exec.data.duracao_ms} ms` : `Falhou: ${exec.data.erro ?? `código ${exec.data.codigo}`}`}{exec.data.truncada ? " (saída truncada em 64 KB)" : ""} · <span className="code">{exec.data.comando.join(" ")}</span></Alert>
          <pre className="code mt-2 max-h-96 overflow-auto rounded bg-muted p-2 text-xs">{exec.data.saida || "(sem saída)"}</pre>
        </div>
      )}
      {historico.length > 0 && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer">Histórico ({historico.length})</summary>
          <ul className="mt-1 divide-y divide-border">{historico.map((h) => <li key={h.id} className="flex flex-wrap gap-2 py-1"><span className="text-muted-foreground">{formatDate(h.criado_em)}</span><Badge variant={h.ok ? "success" : "danger"}>{h.ferramenta}</Badge><span className="code">{h.alvo}</span><span className="text-muted-foreground">{h.solicitante} · {h.duracao_ms} ms</span></li>)}</ul>
        </details>
      )}
    </Card>
  );
}

function ToolCard({ f }: { f: Ferramenta }) {
  const [q, setQ] = React.useState("");
  const abrir = async () => {
    const r = await api.get<{ url: string }>(`/api/tools/deeplink${qs({ tool: f.id, q })}`);
    openExternal(r.url);
  };
  return (
    <Card className="flex flex-col gap-2">
      <h3 className="font-semibold">{f.nome}</h3>
      <p className="text-sm text-muted-foreground">{f.descricao}</p>
      <p className="code text-xs text-muted-foreground">{f.url}</p>
      <div className="flex flex-wrap gap-1">{f.tags.map((t) => <Badge key={t}>{t}</Badge>)}</div>
      <div className="mt-auto flex gap-2 pt-2">
        {f.deeplink && (
          <Input
            aria-label={`Termo para ${f.nome}`}
            placeholder={f.tipo_parametro === "url_imagem" ? "URL pública da imagem" : f.tipo_parametro === "hashtag" ? "#hashtag" : "termo"}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void abrir()}
          />
        )}
        <Button size="sm" onClick={() => void abrir()} aria-label={`Abrir ${f.nome}`}>
          <ExternalLink size={14} /> Abrir
        </Button>
      </div>
    </Card>
  );
}

export default function ToolsPage() {
  const { data = [], error } = useQuery({ queryKey: ["tools"], queryFn: () => api.get<Ferramenta[]>("/api/tools") });
  const [filtro, setFiltro] = React.useState("");
  const vis = data.filter((f) => !filtro || `${f.nome} ${f.descricao} ${f.tags.join(" ")}`.toLowerCase().includes(filtro.toLowerCase()));
  const cats = [...new Set(vis.map((f) => f.categoria))];
  return (
    <>
      <PageHeader title="Hub de ferramentas" description="Ferramentas externas listadas no documento O51NT. Tudo abre no navegador; nenhuma chave de API.">
        <Input aria-label="Filtrar ferramentas" placeholder="Filtrar…" className="w-56" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
      </PageHeader>
      <ErrorText error={error} />
      <FerramentasServidor />
      {cats.map((c) => (
        <section key={c} className="mb-8" aria-labelledby={`cat-${c}`}>
          <h2 id={`cat-${c}`} className="mb-3 rounded-md bg-primary px-3 py-1 text-lg font-bold text-primary-foreground">{c}</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {vis.filter((f) => f.categoria === c).map((f) => <ToolCard key={f.id} f={f} />)}
          </div>
        </section>
      ))}
    </>
  );
}
