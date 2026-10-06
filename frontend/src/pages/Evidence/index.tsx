import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileArchive, ShieldCheck, Trash2, Upload } from "lucide-react";
import * as React from "react";
import { ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Textarea } from "@/components/ui";
import { api, type Evidence } from "@/lib/api";
import { downloadBlob, formatDate } from "@/lib/utils";

function UploadForm() {
  const qc = useQueryClient();
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [origem, setOrigem] = React.useState("");
  const [notas, setNotas] = React.useState("");
  const up = useMutation({
    mutationFn: async () => {
      const files = fileRef.current?.files;
      if (!files?.length) throw new Error("Selecione ao menos um arquivo");
      for (const file of Array.from(files)) {
        const fd = new FormData();
        fd.append("arquivo", file);
        if (origem) fd.append("origem_url", origem);
        fd.append("notas", notas);
        await api.post("/api/evidence", fd);
      }
    },
    onSuccess: () => {
      if (fileRef.current) fileRef.current.value = "";
      setNotas("");
      void qc.invalidateQueries({ queryKey: ["evidence"] });
    },
  });
  return (
    <Card>
      <CardTitle>Adicionar evidência</CardTitle>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); up.mutate(); }}>
        <Field label="Arquivo(s)" htmlFor="evfile"><Input id="evfile" ref={fileRef} type="file" multiple className="h-auto py-1" /></Field>
        <Field label="URL de origem" htmlFor="evorigem"><Input id="evorigem" type="url" value={origem} onChange={(e) => setOrigem(e.target.value)} placeholder="https://…" /></Field>
        <Field label="Notas" htmlFor="evnotas"><Textarea id="evnotas" rows={2} value={notas} onChange={(e) => setNotas(e.target.value)} /></Field>
        <Button type="submit" disabled={up.isPending}><Upload size={14} /> Enviar e calcular SHA-256</Button>
        <ErrorText error={up.error} />
      </form>
    </Card>
  );
}

function HashLookup() {
  const [sha, setSha] = React.useState("");
  const m = useMutation({
    mutationFn: () =>
      api.get<{ total: number; primeira_coleta: Evidence; ocorrencias: Evidence[] }>(`/api/evidence/by-hash/${sha.trim()}`),
  });
  return (
    <Card className="mt-4">
      <CardTitle>Buscar por SHA-256</CardTitle>
      <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Input aria-label="SHA-256" className="font-mono text-xs" value={sha} onChange={(e) => setSha(e.target.value)} placeholder="64 caracteres hex" />
        <Button type="submit" size="sm" disabled={sha.trim().length !== 64 || m.isPending}>Verificar coleta anterior</Button>
      </form>
      {m.error && <div className="mt-2"><Alert variant="info">{(m.error as Error).message}</Alert></div>}
      {m.data && (
        <div className="mt-2 text-sm">
          <Alert variant="success">
            {m.data.total} ocorrência(s). Primeira coleta: #{m.data.primeira_coleta.id} em {formatDate(m.data.primeira_coleta.criado_em)}
          </Alert>
          <ul className="mt-1 list-disc pl-5 text-xs">
            {m.data.ocorrencias.map((o) => <li key={o.id}>#{o.id} · {o.nome_original} · {formatDate(o.criado_em)}</li>)}
          </ul>
        </div>
      )}
    </Card>
  );
}

function Item({ ev, selected, onToggle }: { ev: Evidence; selected: boolean; onToggle: () => void }) {
  const qc = useQueryClient();
  const [ver, setVer] = React.useState<{ integro: boolean; sha256_atual: string | null } | null>(null);
  const verificar = useMutation({ mutationFn: () => api.get<{ integro: boolean; sha256_atual: string | null }>(`/api/evidence/${ev.id}/verify`), onSuccess: setVer });
  const del = useMutation({ mutationFn: () => api.del(`/api/evidence/${ev.id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["evidence"] }) });
  const isImg = ev.mime.startsWith("image/");
  return (
    <Card className="flex flex-col gap-2">
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={selected} onChange={onToggle} /> Selecionar #{ev.id}
      </label>
      {isImg ? (
        <img src={`/api/evidence/${ev.id}/download?inline=true`} alt={ev.notas || ev.nome_original} className="h-36 w-full rounded-md object-cover" loading="lazy" />
      ) : (
        <div className="flex h-36 items-center justify-center rounded-md bg-muted text-xs text-muted-foreground">{ev.mime}</div>
      )}
      <p className="truncate text-sm font-medium" title={ev.nome_original}>{ev.nome_original}</p>
      <p className="text-xs text-muted-foreground">{formatDate(ev.criado_em)} · {(ev.tamanho / 1024).toFixed(1)} KB · <Badge>{ev.tipo}</Badge></p>
      {ev.origem_url && <a className="code text-xs text-primary underline" href={ev.origem_url} target="_blank" rel="noopener noreferrer">{ev.origem_url}</a>}
      <p className="code text-xs text-muted-foreground">sha256: {ev.sha256}</p>
      {ev.notas && <p className="text-xs">{ev.notas}</p>}
      {ver && <Alert variant={ver.integro ? "success" : "error"}>{ver.integro ? "Íntegro: hash confere." : `ADULTERADO/AUSENTE. Atual: ${ver.sha256_atual ?? "—"}`}</Alert>}
      <div className="mt-auto flex gap-1">
        <Button size="sm" variant="outline" onClick={() => verificar.mutate()}><ShieldCheck size={14} /> Verificar</Button>
        <Button size="icon" variant="ghost" aria-label={`Baixar ${ev.nome_original}`} onClick={() => window.open(`/api/evidence/${ev.id}/download`, "_blank")}><Download size={14} /></Button>
        <Button size="icon" variant="ghost" aria-label={`Excluir ${ev.nome_original}`} onClick={() => del.mutate()}><Trash2 size={14} /></Button>
      </div>
    </Card>
  );
}

export default function EvidencePage() {
  const { data = [], error } = useQuery({ queryKey: ["evidence"], queryFn: () => api.get<Evidence[]>("/api/evidence") });
  const [sel, setSel] = React.useState<number[]>([]);
  const exportar = useMutation({
    mutationFn: async () => downloadBlob(await api.blob("POST", "/api/evidence/export", { ids: sel }), `evidencias_${Date.now()}.zip`),
  });
  return (
    <>
      <PageHeader title="Coletor de evidências" description="Cadeia de custódia: SHA-256 no upload, manifesto JSONL e export ZIP com manifest.json + SHA256SUMS.">
        <Button onClick={() => exportar.mutate()} disabled={!data.length || exportar.isPending}>
          <FileArchive size={14} /> Exportar ZIP {sel.length ? `(${sel.length})` : "(todas)"}
        </Button>
      </PageHeader>
      <ErrorText error={error ?? exportar.error} />
      <div className="grid gap-4 lg:grid-cols-4">
        <div className="lg:col-span-1"><UploadForm /><HashLookup /></div>
        <div className="lg:col-span-3">
          {data.length === 0 ? (
            <Empty>Nenhuma evidência.</Empty>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data.map((ev) => (
                <Item key={ev.id} ev={ev} selected={sel.includes(ev.id)} onToggle={() => setSel(sel.includes(ev.id) ? sel.filter((x) => x !== ev.id) : [...sel, ev.id])} />
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
