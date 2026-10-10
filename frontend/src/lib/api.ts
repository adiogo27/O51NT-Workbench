export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Cabeçalho exigido pelo backend em requisições que alteram estado (anti-CSRF, junto do cookie SameSite=Strict). */
export const CSRF_HEADER: Record<string, string> = { "X-Requested-With": "O51NT" };
export const EVENTO_NAO_AUTENTICADO = "o51nt:nao-autenticado";

function avisarNaoAutenticado(path: string): void {
  if (!path.startsWith("/api/auth/")) window.dispatchEvent(new Event(EVENTO_NAO_AUTENTICADO));
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { ...CSRF_HEADER }, credentials: "same-origin" };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  if (res.status === 401) avisarNaoAutenticado(path);
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
      headers: b ? { "Content-Type": "application/json", ...CSRF_HEADER } : { ...CSRF_HEADER },
      body: b ? JSON.stringify(b) : undefined,
      credentials: "same-origin",
    });
    if (res.status === 401) avisarNaoAutenticado(p);
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
export interface Usuario {
  id: number;
  email: string;
  nome: string;
  papel: "admin" | "analista";
  ativo: boolean;
  telegram_chat_id: string | null;
  criado_em: string;
  criado_por: string;
  ultimo_login: string | null;
}

export interface AuthEstado {
  ativo: boolean;
  autenticado: boolean;
  usuario: Usuario | null;
  canal: "email" | "telegram" | "journal" | "nenhum";
  validade_min: number;
}

export interface SessaoInfo {
  id: number;
  criado_em: string;
  ultimo_uso: string;
  expira_em: string;
  ip: string;
  user_agent: string;
  atual: boolean;
}

export interface EventoAcesso {
  id: number;
  em: string;
  evento: string;
  email: string;
  ip: string;
  ok: boolean;
  detalhe: string;
}

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
  canal_alerta: "jsonl" | "webhook" | "telegram" | "nenhum";
  webhook_url: string | null;
  tipo: "query" | "hashtag";
  ativo: boolean;
  ultima_execucao: string | null;
  proxima_execucao: string | null;
  criado_em: string;
  radar_modo: "termos" | "estrito";
  hits_total: number;
  hits_novos: number;
  ia: boolean;
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
  tipo: "feed" | "pagina";
  intervalo_min: number | null;
  ultima_mudanca: string | null;
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
  tipo_detectado?: "feed" | "pagina" | null;
  feed_descoberto?: string | null;
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
  plataforma: "whatsapp" | "whatsapp_canal" | "telegram" | "telegram_publico";
  url: string;
  termo: string;
  origem: string;
  first_seen: string;
  last_seen: string;
  hash_conteudo: string;
  // v2 — contexto e verificação da página pública do convite
  fonte_url: string;
  status: "ativo" | "revogado" | "desconhecido";
  nome_grupo: string | null;
  membros: number | null;
  descricao: string | null;
  verificado_em: string | null;
  evidencia_id: number | null;
  score_relevancia: number;
  http_status: number;
  erro_verificacao: string;
}

export interface InviteVerificacao {
  status: "ativo" | "revogado" | "desconhecido";
  nome_grupo: string | null;
  membros: number | null;
  descricao: string | null;
  foto_url: string | null;
  http_status: number;
  erro: string | null;
  robots_permite: boolean;
  verificado_em: string;
  tipo: string;
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
  preferencias: Preferencias;
}

export interface Preferencias {
  navegadorPadrao: string;
  historicoRetencaoDias: number;
  historicoMaxEntradas: number;
  radarAtivo: boolean;
  radarIntervaloMin: number;
  // Convocações
  convocacoesAtivo: boolean;
  convocacoesIntervaloMin: number;
  convocacoesPerfilML: "leve" | "completo";
  convocacoesLimiarAlerta: number;
  convocacoesLimiarCritico: number;
  convocacoesPesoLexico: number;
  convocacoesPesoVisual: number;
  convocacoesPesoReferencia: number;
  convocacoesPesoMonitor: number;
  convocacoesBonusDistribuicao: number;
  convocacoesTermosExtra: string[];
  convocacoesTermosExcluir: string[];
  convocacoesMaxImagensCiclo: number;
  convocacoesDescarregarMin: number;
  convocacoesAnalisarFeeds: boolean;
  convocacoesCanalAlerta: "jsonl" | "webhook" | "telegram" | "nenhum";
  convocacoesWebhookUrl: string | null;
  convocacoesRetencaoDias: number;
  // Convites
  convitesRespeitarRobots: boolean;
  convitesVerificarAuto: boolean;
  convitesVerificarIntervaloHoras: number;
  // Assistente de IA (OpenClaw)
  iaAtivo: boolean;
  iaIntervaloMin: number;
  iaMaxItensCiclo: number;
  iaCustoDiarioUsd: number;
  iaModeloTriagem: string;
  iaModeloPadrao: string | null;
  iaModeloLeve: string | null;
  iaPesquisarSeveridadeMin: "baixa" | "media" | "alta" | "critica" | "nunca";
  iaBoletim: "auto" | "aprovar" | "nunca";
  iaAgenda: "auto" | "aprovar" | "nunca";
  iaTelegramRelevante: boolean;
  iaResumoHoras: number;
  iaSuprimirAlertasBrutos: boolean;
  iaMarcarLidos: boolean;
  iaTextoMaxChars: number;
  iaAterramento: boolean;
  ferramentasSensiveisAtivas: boolean;
}

// ------------------------------------------------------------------ Assistente de IA
export type Veredito = "RELEVANTE" | "OBSERVAR" | "DESCARTAR";
export type EtiquetaConfianca = "alta" | "media" | "baixa" | "nao_verificada" | "refutada";

export interface IaTarefa {
  id: number;
  origem: "hit" | "deteccao" | "manual";
  hit_id: number | null;
  deteccao_id: number | null;
  monitor_id: number | null;
  monitor_nome: string;
  url: string;
  titulo: string;
  resumo: string;
  fonte_nome: string;
  termos: string;
  publicado_em: string | null;
  texto_chars: number;
  status: "pendente" | "em_processo" | "concluida" | "erro";
  etapa: string;
  tentativas: number;
  erro: string;
  veredito: Veredito | null;
  severidade: Severidade | null;
  justificativa: string;
  secao_sugerida: string | null;
  eh_evento: boolean;
  triagem: Record<string, unknown>;
  evento: { tipo?: string | null; titulo?: string | null; data?: string | null; hora?: string | null; cidade?: string | null; uf?: string | null; local?: string | null; rodovias?: string[]; organizador?: string | null; pauta?: string | null; confianca?: number };
  pesquisa: { resposta?: string; verificacao?: string | null; fontes?: { url: string; titulo?: string; trecho?: string }[]; confianca?: number; lacunas?: string };
  cartao: { titulo?: string; resumo?: string; impacto_rodovia?: string; acao?: string; fontes?: string[] };
  /** Checagem de aterramento (OOVS): afirmações do cartão × trechos citados. Vazio quando a etapa não rodou. */
  aterramento?: { sustentadas?: number; parciais?: number; total?: number; afirmacoes?: { texto: string; sustentada: "sim" | "parcial" | "nao"; fonte?: number | null }[]; observacao?: string };
  /** Camada OOVS: origens distintas, corroborações e etiqueta de confiança derivada mecanicamente. */
  verificacao?: { norma?: string; etiqueta?: EtiquetaConfianca; origens_distintas?: number; corroboracoes?: number; duplicadas?: number; verificacao?: string | null; aterramento?: { sustentadas: number; total: number } | null; motivos?: string[] };
  aprovacao: "nao_se_aplica" | "pendente" | "aprovada" | "rejeitada";
  aprovado_por: string;
  aprovado_em: string | null;
  alerta_id: number | null;
  boletim_item_id: number | null;
  agenda_evento_id: number | null;
  telegram_enviado: boolean;
  resumo_enviado: boolean;
  tokens_entrada: number;
  tokens_saida: number;
  custo_usd: number;
  modelos: string;
  criado_em: string;
  iniciado_em: string | null;
  concluido_em: string | null;
}

export interface IaStatus {
  ativo: boolean;
  intervalo_min: number;
  openclaw_configurado: boolean;
  openclaw_url: string;
  fila: { pendente: number; em_processo: number; concluida: number; erro: number };
  vereditos: Record<string, number>;
  aprovacoes_pendentes: number;
  alertas_ia_nao_lidos: number;
  custo_hoje: { data: string; chamadas: number; tokens_entrada: number; tokens_saida: number; custo_usd: number; teto_usd: number; bloqueado: boolean };
  politica: { boletim: string; agenda: string; pesquisar_min: string; telegram_relevante: boolean; resumo_horas: number };
  ultimo_ciclo: { executado_em: string; processadas: number; concluidas: number; erros: number; custo_usd: number; motivo_parada: string | null; duracao_s?: number } | null;
  agendado: boolean;
  proximo_ciclo: string | null;
  proximo_resumo: string | null;
}

export interface IaCustoDia {
  data: string;
  chamadas: number;
  tokens_entrada: number;
  tokens_saida: number;
  custo_usd: number;
}

export interface FerramentaServidor {
  id: string;
  nome: string;
  descricao: string;
  tipo_alvo: string;
  grupo: "infra" | "perfis" | "midia" | "sensivel";
  sensivel: boolean;
  timeout_s: number;
  exemplo: string;
  instalada: boolean;
  habilitada: boolean;
}

export interface FerramentaResultado {
  id: number | null;
  ferramenta: string;
  alvo: string;
  comando: string[];
  ok: boolean;
  codigo: number | null;
  saida: string;
  truncada: boolean;
  duracao_ms: number;
  erro: string | null;
}

export interface FerramentaExecucao {
  id: number;
  ferramenta: string;
  alvo: string;
  solicitante: string;
  ok: boolean;
  duracao_ms: number;
  resumo: string;
  criado_em: string;
}

// ------------------------------------------------------------------ Convocações / Alertas
export type Severidade = "baixa" | "media" | "alta" | "critica";

export interface Deteccao {
  id: number;
  origem: string;
  plataforma: string;
  post_url: string;
  imagem_url: string;
  autor: string;
  publicado_em: string | null;
  evidencia_id: number | null;
  sha256: string;
  phash: string;
  texto_post: string;
  texto_ocr: string;
  ocr_confianca: number;
  ocr_modelo: string;
  qr: string[];
  convites: { plataforma: string; url: string }[];
  termos_lexico: Record<string, string[]>;
  termos_monitor: string;
  monitor_ids: string;
  tempo: "futuro" | "passado" | "indefinido";
  data_evento: string | null;
  hora_evento: string | null;
  local_evento: string;
  noticiando: boolean;
  nao_pacifico: boolean;
  score: number;
  score_detalhe: Record<string, unknown>;
  severidade: Severidade;
  estado: "nova" | "confirmada" | "descartada";
  referencia_id: number | null;
  alerta_id: number | null;
  boletim_item_id: number | null;
  agenda_evento_id: number | null;
  ocorrencias: number;
  notas: string;
  criado_em: string;
}

export interface AnaliseResultado {
  score: number;
  severidade: Severidade;
  decomposicao: { componentes: Record<string, { valor: number; peso: number; parcela: number }>; bonus_distribuicao: number; score: number };
  lexico: {
    pontos: number;
    cobertura: number;
    termos: Record<string, string[]>;
    tempo: string;
    data_evento: string | null;
    hora_evento: string | null;
    local: string | null;
    noticiando: boolean;
    pistas_noticiando: string[];
    pistas_convocando: string[];
    nao_pacifico: boolean;
    score: number;
  };
  ocr: { texto: string; linhas: string[]; confianca: number; variante: number; ms: number; modelo: string } | null;
  qr: string[];
  convites: { plataforma: string; url: string }[];
  visual: Record<string, number> | null;
  referencia: { id: number | null; score: number; motivo: string } | null;
  monitores: { id: number; nome: string; termos: string[] }[];
  imagem: { largura: number; altura: number; sha256: string; phash: string; mime: string } | null;
  ms: number;
  capacidades: { ocr: boolean; clip: boolean; ocr_modelo: string | null };
  passos?: string[];
}

export interface AnaliseOut {
  deteccao: Deteccao | null;
  nova: boolean;
  duplicada: boolean;
  salva: boolean;
  score: number;
  severidade: Severidade;
  alerta_id: number | null;
  ocorrencia_id: number | null;
  resultado: AnaliseResultado;
}

export interface Ocorrencia {
  id: number;
  deteccao_id: number;
  post_url: string;
  imagem_url: string;
  plataforma: string;
  autor: string;
  publicado_em: string | null;
  visto_em: string;
  variante: boolean;
  fonte_id: number | null;
}

export interface ReferenciaCartaz {
  id: number;
  deteccao_id: number | null;
  evidencia_id: number | null;
  phash: string;
  tem_embedding: boolean;
  modelo_embedding: string;
  rotulo: string;
  notas: string;
  criado_em: string;
}

export type TipoFonteConvocacao = "bluesky_busca" | "telegram_canal" | "searxng_imagens" | "feed_midia";

export interface FonteConvocacao {
  id: number;
  nome: string;
  tipo: TipoFonteConvocacao;
  parametro: string;
  rede_alvo: string;
  ativa: boolean;
  respeitar_robots: boolean;
  ultima_coleta: string | null;
  ultimo_status: number;
  ultimo_erro: string;
  itens_total: number;
  novos_ultima: number;
  criado_em: string;
}

export interface FonteConvocacaoTeste {
  ok: boolean;
  status: number;
  erro: string | null;
  robots_permite: boolean;
  candidatos: number;
  com_imagem: number;
  amostra: { post_url: string; autor: string; texto: string; imagens: string[]; publicado_em: string | null }[];
}

export interface Capacidades {
  perfil: "leve" | "completo";
  ocr_instalado: boolean;
  clip_instalado: boolean;
  qr: boolean;
  lexico: boolean;
  carregados: string[];
  ocr_modelo: string | null;
  clip_modelo: string | null;
  ultimo_uso: string | null;
  analises: number;
  rss_mb: number;
  threads: number;
  dir_modelos: string;
}

export interface ConvocacoesStatus {
  ativo: boolean;
  intervalo_min: number;
  agendado: boolean;
  proximo_ciclo: string | null;
  ultimo_ciclo: { executado_em: string; duracao_s: number; analisados: number; novos: number; ocorrencias: number; alertas: number; fontes: Record<string, unknown>[] } | null;
  fontes_ativas: number;
  fontes_total: number;
  deteccoes_total: number;
  novas: number;
  por_severidade: Record<Severidade, number>;
  referencias: number;
  capacidades: Capacidades;
}

export interface Alerta {
  id: number;
  tipo: "convocacao" | "convite" | "radar" | "ia";
  severidade: Severidade;
  titulo: string;
  resumo: string;
  url: string;
  deteccao_id: number | null;
  invite_id: number | null;
  monitor_id: number | null;
  lido: boolean;
  criado_em: string;
  canal_log: string;
}

export interface AlertasContagem {
  total: number;
  criticos: number;
  convocacao: number;
  convite: number;
  radar: number;
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
  query?: string;
  encontrados?: number;
  resultados_busca?: number;
  engines_sem_resposta?: unknown[];
}
