import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import * as React from "react";
import { ErrorText } from "@/components/shared";
import { Badge, Button, Card, Input, PageHeader } from "@/components/ui";
import { api, qs, type Ferramenta } from "@/lib/api";
import { openExternal } from "@/lib/utils";

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
