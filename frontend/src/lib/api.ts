export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, msg);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T>(p: string, b: unknown) => request<T>("PUT", p, b),
  patch: <T>(p: string, b: unknown) => request<T>("PATCH", p, b),
  del: <T = void>(p: string) => request<T>("DELETE", p),
  blob: async (method: string, p: string, b?: unknown): Promise<Blob> => {
    const res = await fetch(p, {
      method,
      headers: b ? { "Content-Type": "application/json" } : {},
      body: b ? JSON.stringify(b) : undefined,
    });
    if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`);
    return res.blob();
  },
};

export const qs = (params: Record<string, string | number | undefined | null>): string => {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && u.set(k, String(v)));
  const s = u.toString();
  return s ? `?${s}` : "";
};

// ------------------------------------------------------------------ tipos
export interface Problema {
  codigo: string;
  mensagem: string;
  posicao: number | null;
}

export interface ComposeResponse {
  query: string;
  valida: boolean;
  erros: Problema[];
  avisos: Problema[];
  deeplinks: Record<string, string>;
  compatibilidade: Record<string, string[]>;
  /** X, TikTok, YouTube e Google Notícias (campo adicional; `deeplinks` original preservado). */
  deeplinks_extra?: Record<string, string>;
  compatibilidade_extra?: Record<string, string[]>;
  operadores_x?: string[];
}

export interface ValidateResponse extends ComposeResponse {
  operadores: Record<string, string[]>;
}

export interface Template {
  id: number;
  nome: string;
  categoria: string;
  descricao: string;
  query: string;
  placeholders: string[];
  origem_pdf: boolean;
  criado_em: string;
}

export interface HistoryItem {
  id: number;
  query: string;
  motor: string;
  origem: string;
  criado_em: string;
}

export interface Monitor {
  id: number;
  nome: string;
  query: string;
  cron: string;
  canal_alerta: "jsonl" | "webhook" | "nenhum";
  webhook_url: string | null;
  tipo: "query" | "hashtag";
  ativo: boolean;
  ultima_execucao: string | null;
  proxima_execucao: string | null;
  criado_em: string;
  radar_modo: "termos" | "estrito";
  hits_total: number;
  hits_novos: number;
}

export interface Fonte {
  id: number;
  nome: string;
  url: string;
  categoria: string;
  ativa: boolean;
  respeitar_robots: boolean;
  ultima_coleta: string | null;
  ultimo_status: number;
  ultimo_erro: string;
  itens_total: number;
  novos_ultima: number;
  criado_em: string;
}

export interface FonteCatalogo {
  nome: string;
  url: string;
  categoria: string;
  tipo: "feed" | "modelo";
  descricao: string;
  cadastrada: boolean;
}

export interface FonteTeste {
  ok: boolean;
  status: number;
  erro: string | null;
  robots_permite: boolean;
  itens: number;
  amostra: { titulo: string; url: string; publicado_em: string | null }[];
}

export interface Hit {
  id: number;
  monitor_id: number;
  monitor_nome: string;
  fonte_id: number | null;
  fonte_nome: string;
  url: string;
  titulo: string;
  resumo: string;
  publicado_em: string | null;
  encontrado_em: string;
  termos: string;
  origem: string;
  lido: boolean;
  boletim_item_id: number | null;
}

export interface RadarStatus {
  ativo: boolean;
  intervalo_min: number;
  agendado: boolean;
  proximo_ciclo: string | null;
  ultimo_ciclo: { executado_em: string; duracao_s: number; itens_novos: number; hits_novos: number; alertas: number; fontes: { nome: string; status: number; novos: number; erro: string | null }[] } | null;
  fontes_ativas: number;
  fontes_total: number;
  monitores_ativos: number;
  itens_total: number;
  hits_total: number;
  hits_novos: number;
}

export interface MonitorRun {
  id: number;
  monitor_id: number;
  executado_em: string;
  status: string;
  deeplinks: Record<string, string>;
  resultado: Record<string, unknown>;
  log: string;
}

export interface Invite {
  id: number;
  plataforma: "whatsapp" | "telegram";
  url: string;
  termo: string;
  origem: string;
  first_seen: string;
  last_seen: string;
  hash_conteudo: string;
}

export interface Ferramenta {
  id: string;
  nome: string;
  url: string;
  categoria: string;
  tags: string[];
  descricao: string;
  deeplink: string | null;
  tipo_parametro: "texto" | "url_imagem" | "hashtag" | null;
}

export interface Evidence {
  id: number;
  tipo: string;
  origem_url: string | null;
  arquivo: string;
  nome_original: string;
  tamanho: number;
  mime: string;
  sha256: string;
  criado_em: string;
  notas: string;
}

export interface Hashtag {
  id: number;
  tag: string;
  chave_normalizada: string;
  rede: string;
  contagem: number;
  primeira_vez: string;
  ultima_vez: string;
  fonte: string;
  monitor_id: number | null;
}

export interface Snapshot {
  id: number;
  coletado_em: string;
  contagem: number;
  fonte: string;
  origem_url: string;
  sha256: string;
}

export interface AppSettings {
  tema: { primary: string; secondary: string; background: string; foreground: string; accent: string; radius: number };
  tipografia: { fontFamily: string; fontSizeBase: number };
  preferencias: { navegadorPadrao: string; historicoRetencaoDias: number; historicoMaxEntradas: number; radarAtivo: boolean; radarIntervaloMin: number };
}

export interface AgendaEvento {
  id: number;
  candidato: string;
  partido: string;
  cargo: string;
  titulo: string;
  tipo: string;
  data: string;
  dia_semana: string;
  hora_inicio: string | null;
  hora_fim: string | null;
  cidade: string;
  uf: string;
  local: string;
  rodovias: string[];
  impacto_rodovia: boolean;
  descricao: string;
  fonte_url: string | null;
  status: string;
  monitor_id: number | null;
  criado_em: string;
  atualizado_em: string;
}

export interface AgendaDia {
  data: string;
  dia_semana: string;
  total: number;
  com_impacto_rodovia: number;
  por_candidato: Record<string, AgendaEvento[]>;
  eventos: AgendaEvento[];
}

export interface AgendaQueries {
  evento_id: number;
  query: string;
  query_x: string;
  deeplinks: Record<string, string>;
  deeplinks_x: Record<string, string>;
  termos_rodovia: string[];
}

export interface Perfil {
  id: number;
  rede: string;
  handle: string;
  url: string;
  rotulo: string;
  categoria: string;
  notas: string;
  ativo: boolean;
  monitor_id: number | null;
  criado_em: string;
}

export interface PerfilDeeplinks {
  perfil: string;
  query_mencoes: string;
  query_mencoes_x: string;
  deeplinks: Record<string, string>;
  deeplinks_x: Record<string, string>;
}

export interface BoletimItem {
  id: number;
  data: string;
  secao: string;
  titulo: string;
  url: string;
  fonte: string;
  resumo: string;
  evidence_id: number | null;
  criado_em: string;
}

export interface Boletim {
  data: string;
  titulo: string;
  dia_semana: string;
  secoes: Record<string, BoletimItem[]>;
  agenda: { total: number; com_impacto_rodovia: number; por_candidato: Record<string, AgendaEvento[]> };
  perfis: Perfil[];
  hashtags: { tag: string; contagem: number; fonte: string }[];
  convites: { plataforma: string; url: string; termo: string; last_seen: string }[];
  markdown: string;
}

export interface ScrapeExecucao {
  fonte: string;
  url: string;
  status: number;
  erro: string | null;
  sha256: string;
  coletado_em: string;
  resultados?: { titulo: string; url: string }[];
  plataforma?: string;
  encontrados?: number;
  resultados_busca?: number;
  engines_sem_resposta?: unknown[];
}
