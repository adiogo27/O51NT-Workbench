import { ExternalLink, ShieldCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { api, type Problema, type ScrapeExecucao } from "@/lib/api";
import { detectGoogleOperators, detectXOperators, MOTIVO_SEM_SEARXNG, MOTIVO_SEM_SEARXNG_X } from "@/lib/queryOperators";
import { formatDate, openExternal } from "@/lib/utils";
import { Alert, Badge, Button, Tabs, TabPanel } from "./ui";

export const MOTOR_LABEL: Record<string, string> = {
  google: "Google",
  bing: "Bing",
  duckduckgo: "DuckDuckGo",
  startpage: "Startpage",
  x: "X (recentes)",
  tiktok: "TikTok",
  youtube: "YouTube",
  google_news: "Google Notícias",
};

export function DeeplinkButtons({
  deeplinks,
  query,
  compatibilidade,
  origem = "builder",
}: {
  deeplinks: Record<string, string>;
  query?: string;
  compatibilidade?: Record<string, string[]>;
  origem?: string;
}) {
  const abrir = (motor: string, url: string) => {
    if (query) void api.post("/api/query/history", { query, motor, origem }).catch(() => undefined);
    openExternal(url);
  };
  return (
    <div className="flex flex-wrap gap-2">
      {Object.entries(deeplinks).map(([motor, url]) => {
        const nao = compatibilidade?.[motor];
        return (
          <Button
            key={motor}
            variant={motor === "google" ? "default" : "outline"}
            size="sm"
            onClick={() => abrir(motor, url)}
            title={nao?.length ? `Não suporta: ${nao.join(", ")}` : undefined}
            aria-label={`Abrir no ${MOTOR_LABEL[motor] ?? motor}${nao?.length ? ` (não suporta ${nao.join(", ")})` : ""}`}
          >
            <ExternalLink size={14} aria-hidden /> {MOTOR_LABEL[motor] ?? motor}
            {nao?.length ? <span className="text-warning" aria-hidden>⚠</span> : null}
          </Button>
        );
      })}
    </div>
  );
}

export function ProblemList({ erros, avisos }: { erros: Problema[]; avisos: Problema[] }) {
  if (!erros.length && !avisos.length) return <Alert variant="success">Query válida.</Alert>;
  return (
    <div className="space-y-1">
      {erros.map((e, i) => (
        <Alert key={`e${i}`} variant="error">
          <strong>Erro:</strong> {e.mensagem}
        </Alert>
      ))}
      {avisos.map((a, i) => (
        <Alert key={`a${i}`} variant="warning">
          <strong>Aviso:</strong> {a.mensagem}
        </Alert>
      ))}
    </div>
  );
}

export function EthicsNotice() {
  return (
    <Alert variant="info">
      <span className="inline-flex items-center gap-1 font-medium">
        <ShieldCheck size={14} aria-hidden /> Coleta assistida:
      </span>{" "}
      as buscas passam pela sua instância <strong>local</strong> do SearXNG (metabusca), uma consulta por clique. DuckDuckGo
      e Bing proíbem crawling direto no robots.txt; o SearXNG consulta-os como cliente de busca e <strong>não</strong> aplica
      esse robots.txt — use com baixo volume e finalidade legítima. Todo resultado é salvo com URL de origem, horário e
      SHA-256. Páginas públicas (trends24, OneMillionTweetMap) seguem o scraper ético: robots.txt, 1 req/3 s, backoff em 403/429.
    </Alert>
  );
}

export function SearxngStatus() {
  const { data, isLoading } = useQuery({
    queryKey: ["searxng-status"],
    queryFn: () => api.get<{ url: string; disponivel: boolean }>("/api/searxng/status"),
    refetchInterval: 30000,
  });
  if (isLoading || !data) return null;
  return data.disponivel ? (
    <p className="text-xs text-success" role="status">● SearXNG disponível em {data.url}</p>
  ) : (
    <Alert variant="warning">
      SearXNG indisponível em <span className="code">{data.url}</span>. Suba com <span className="code">./run.sh</span> (requer
      Docker) ou use a subaba Deeplinks.
    </Alert>
  );
}

export const ENGINES = ["duckduckgo", "bing", "startpage"] as const;

export function EnginePicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <fieldset className="flex flex-wrap gap-4 text-sm">
      <legend className="mb-1 text-xs text-muted-foreground">Buscadores (via SearXNG)</legend>
      {ENGINES.map((f) => (
        <label key={f} className="flex items-center gap-1">
          <input type="checkbox" checked={value.includes(f)} onChange={(e) => onChange(e.target.checked ? [...value, f] : value.filter((x) => x !== f))} />
          {f}
        </label>
      ))}
    </fieldset>
  );
}

export function ScrapeExecucoes({ execucoes }: { execucoes: ScrapeExecucao[] }) {
  return (
    <ul className="space-y-3">
      {execucoes.map((e, i) => (
        <li key={i} className="rounded-md border border-border p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={e.erro ? "danger" : "success"}>{e.erro ? "falhou" : `HTTP ${e.status}`}</Badge>
            <strong>{e.fonte}</strong>
            {e.plataforma && <Badge>{e.plataforma}</Badge>}
            {e.query && <span className="code text-xs text-muted-foreground">{e.query}</span>}
            {e.encontrados !== undefined && <span>{e.encontrados} convite(s)</span>}
            {e.resultados_busca !== undefined && <span className="text-muted-foreground">em {e.resultados_busca} resultado(s)</span>}
            <span className="text-muted-foreground">{formatDate(e.coletado_em)}</span>
          </div>
          {e.erro && <p className="mt-1 text-danger">{e.erro}</p>}
          {!!e.engines_sem_resposta?.length && (
            <p className="mt-1 text-warning">
              Sem resposta: {e.engines_sem_resposta.map((x) => (Array.isArray(x) ? x.join(" — ") : String(x))).join("; ")}
            </p>
          )}
          <p className="code mt-1 text-xs text-muted-foreground">origem: {e.url}</p>
          {e.sha256 && <p className="code text-xs text-muted-foreground">sha256: {e.sha256}</p>}
          {!!e.resultados?.length && (
            <ol className="mt-2 list-decimal space-y-1 pl-5">
              {e.resultados.map((r) => (
                <li key={r.url}>
                  <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-primary underline">
                    {r.titulo || r.url}
                  </a>
                </li>
              ))}
            </ol>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Subabas obrigatórias "Deeplinks" / "Scraping ético". */
export function ModeTabs({ deeplinks, scraping, label }: { deeplinks: React.ReactNode; scraping: React.ReactNode; label: string }) {
  const [tab, setTab] = React.useState("deeplinks");
  return (
    <>
      <Tabs
        label={label}
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "deeplinks", label: "Deeplinks" },
          { id: "scraping", label: "Scraping ético" },
        ]}
      />
      <TabPanel id="deeplinks" active={tab === "deeplinks"}>
        {deeplinks}
      </TabPanel>
      <TabPanel id="scraping" active={tab === "scraping"}>
        {scraping}
      </TabPanel>
    </>
  );
}

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <Alert variant="error">{error instanceof Error ? error.message : String(error)}</Alert>;
}

export function ListInput({
  id,
  values,
  onChange,
  placeholder,
}: {
  id: string;
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = React.useState("");
  const add = () => {
    const t = draft.trim();
    if (t && !values.includes(t)) onChange([...values, t]);
    setDraft("");
  };
  return (
    <div>
      <div className="flex gap-2">
        <input
          id={id}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="h-9 w-full rounded-md border border-border bg-background px-3 text-sm"
        />
        <Button size="sm" variant="outline" onClick={add} aria-label="Adicionar item">
          +
        </Button>
      </div>
      {values.length > 0 && (
        <ul className="mt-2 flex flex-wrap gap-1" aria-label="Itens adicionados">
          {values.map((v) => (
            <li key={v}>
              <button
                type="button"
                className="rounded-sm border border-border bg-muted px-2 py-0.5 text-xs hover:border-danger"
                onClick={() => onChange(values.filter((x) => x !== v))}
                aria-label={`Remover ${v}`}
              >
                {v} ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Botão de busca via SearXNG, desabilitado quando qualquer query usa operadores do Google
 * (o SearXNG não os respeita). Mesma regra em todas as abas: Query Builder e Convites.
 */
export function SearxngSearchButton({
  queries,
  disabled,
  pending,
  onClick,
  label = "Buscar via SearXNG",
  permitirOperadores = false,
}: {
  queries: string[];
  disabled?: boolean;
  pending?: boolean;
  onClick: () => void;
  label?: string;
  /** Convites: as consultas são geradas pelo backend só com `site:` simples e aspas, que Bing/DDG honram. */
  permitirOperadores?: boolean;
}) {
  const opsGoogle = React.useMemo(() => [...new Set(queries.flatMap((q) => detectGoogleOperators(q)))], [queries]);
  const opsX = React.useMemo(() => [...new Set(queries.flatMap((q) => detectXOperators(q)))], [queries]);
  const bloqueado = !permitirOperadores && (opsGoogle.length > 0 || opsX.length > 0);
  // Google tem prioridade na mensagem (é a regra original); X aparece quando só há operadores do X.
  const motivo = opsGoogle.length > 0 ? MOTIVO_SEM_SEARXNG : MOTIVO_SEM_SEARXNG_X;
  const id = React.useId();
  return (
    <div className="space-y-1">
      {/* span com title: navegadores não exibem tooltip de <button disabled> de forma consistente */}
      <span className="inline-block" title={bloqueado ? motivo : undefined}>
        <Button disabled={disabled || pending || bloqueado} aria-describedby={bloqueado ? id : undefined} onClick={onClick}>
          {pending ? "Consultando SearXNG…" : label}
        </Button>
      </span>
      {bloqueado && (
        <p id={id} className="text-sm text-warning">
          {motivo} <span className="text-muted-foreground">(encontrados: {[...opsGoogle, ...opsX].join(" ")})</span>
        </p>
      )}
    </div>
  );
}
