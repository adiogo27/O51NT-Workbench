import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Trash2 } from "lucide-react";
import * as React from "react";
import { DeeplinkButtons, ENGINES, EnginePicker, EthicsNotice, ErrorText, ModeTabs, ScrapeExecucoes, SearxngSearchButton, SearxngStatus, useDebounced } from "@/components/shared";
import { Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader } from "@/components/ui";
import { api, qs, type Invite, type ScrapeExecucao } from "@/lib/api";
import { downloadBlob, formatDate } from "@/lib/utils";

interface QueriesResp {
  queries: Record<string, string>;
  deeplinks: Record<string, Record<string, string>>;
}

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
  const queries = plats.map((p) => qsResp?.queries[p]).filter((q): q is string => !!q);
  const scan = useMutation({
    mutationFn: () => api.post<{ novos: number; atualizados: number; execucoes: ScrapeExecucao[] }>("/api/invites/scan", { termo, plataformas: plats, engines }),
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
      <SearxngSearchButton
        queries={queries}
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

function Tabela() {
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["invites"], queryFn: () => api.get<Invite[]>("/api/invites") });
  const del = useMutation({ mutationFn: (id: number) => api.del(`/api/invites/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }) });
  const exportar = async (formato: "csv" | "json") => downloadBlob(await api.blob("GET", `/api/invites/export?formato=${formato}`), `convites.${formato}`);
  return (
    <Card className="mt-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="mb-0">Convites coletados ({data.length})</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => void exportar("csv")}><Download size={14} /> CSV</Button>
          <Button size="sm" variant="outline" onClick={() => void exportar("json")}><Download size={14} /> JSON</Button>
        </div>
      </div>
      {data.length === 0 ? (
        <Empty>Nenhum convite armazenado.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Convites encontrados</caption>
            <thead className="text-xs text-muted-foreground">
              <tr><th scope="col" className="p-2">Plataforma</th><th scope="col" className="p-2">URL</th><th scope="col" className="p-2">Termo</th><th scope="col" className="p-2">Primeira / última</th><th scope="col" className="p-2">Hash da página</th><th scope="col" className="p-2"><span className="sr-only">Ações</span></th></tr>
            </thead>
            <tbody>
              {data.map((i) => (
                <tr key={i.id} className="border-t border-border align-top">
                  <td className="p-2"><Badge variant={i.plataforma === "whatsapp" ? "success" : "default"}>{i.plataforma}</Badge></td>
                  <td className="code p-2 text-xs">{i.url}</td>
                  <td className="p-2">{i.termo}</td>
                  <td className="p-2 text-xs">{formatDate(i.first_seen)}<br />{formatDate(i.last_seen)}</td>
                  <td className="code p-2 text-xs" title={`origem: ${i.origem}`}>{i.hash_conteudo.slice(0, 16)}…</td>
                  <td className="p-2"><Button size="icon" variant="ghost" aria-label={`Excluir ${i.url}`} onClick={() => del.mutate(i.id)}><Trash2 size={14} /></Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export default function InvitesPage() {
  const [termo, setTermo] = React.useState("");
  return (
    <>
      <PageHeader title="Caçador de convites" description="Grupos WhatsApp (chat.whatsapp.com) e Telegram (t.me/joinchat) divulgados em redes sociais." />
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
