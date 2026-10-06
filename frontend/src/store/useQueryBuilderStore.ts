import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface BlocoX {
  since: string;
  until: string;
  from: string[];
  to: string[];
  mencoes: string[];
  excluir_retweets: boolean;
  apenas_respostas: boolean;
  apenas_verificados: boolean;
  has: string[];
  lang: string;
  min_faves: string;
  min_retweets: string;
  min_replies: string;
}

export interface Blocos {
  precisao: { termos: string[]; frases_exatas: string[]; grupos_or: string[][]; excluir: string[]; curingas: string[][] };
  temporal: { after: string; before: string };
  escopo: { sites: string[]; excluir_sites: string[]; filetype: string; inurl: string[]; intitle: string[]; intext: string[] };
  x: BlocoX;
  extra: string;
  template_id: number | null;
  valores_template: Record<string, string>;
}

export const BLOCOS_VAZIOS: Blocos = {
  precisao: { termos: [], frases_exatas: [], grupos_or: [], excluir: [], curingas: [] },
  temporal: { after: "", before: "" },
  escopo: { sites: [], excluir_sites: [], filetype: "", inurl: [], intitle: [], intext: [] },
  x: {
    since: "",
    until: "",
    from: [],
    to: [],
    mencoes: [],
    excluir_retweets: false,
    apenas_respostas: false,
    apenas_verificados: false,
    has: [],
    lang: "",
    min_faves: "",
    min_retweets: "",
    min_replies: "",
  },
  extra: "",
  template_id: null,
  valores_template: {},
};

/** Completa rascunhos antigos (sem o bloco X, por exemplo) com os valores padrão. */
export function normalizarBlocos(b: Partial<Blocos> | undefined): Blocos {
  return {
    ...BLOCOS_VAZIOS,
    ...(b ?? {}),
    precisao: { ...BLOCOS_VAZIOS.precisao, ...(b?.precisao ?? {}) },
    temporal: { ...BLOCOS_VAZIOS.temporal, ...(b?.temporal ?? {}) },
    escopo: { ...BLOCOS_VAZIOS.escopo, ...(b?.escopo ?? {}) },
    x: { ...BLOCOS_VAZIOS.x, ...(b?.x ?? {}) },
  };
}

interface QueryBuilderState {
  blocos: Blocos;
  set: (fn: (b: Blocos) => Blocos) => void;
  reset: () => void;
}

// Persistência do rascunho no navegador (conveniência; histórico/templates ficam no SQLite).
export const useQueryBuilderStore = create<QueryBuilderState>()(
  persist(
    (set) => ({
      blocos: BLOCOS_VAZIOS,
      set: (fn) => set((s) => ({ blocos: fn(s.blocos) })),
      reset: () => set({ blocos: BLOCOS_VAZIOS }),
    }),
    {
      name: "o51nt-query-builder",
      version: 2,
      migrate: (persisted) => {
        const p = persisted as Partial<QueryBuilderState> | undefined;
        return { ...(p ?? {}), blocos: normalizarBlocos(p?.blocos) } as QueryBuilderState;
      },
      merge: (persisted, current) => {
        const p = persisted as Partial<QueryBuilderState> | undefined;
        return { ...current, blocos: normalizarBlocos(p?.blocos) };
      },
    },
  ),
);

const numOuNull = (v: string): number | null => (v.trim() === "" ? null : Number(v));

export function toPayload(b: Blocos) {
  return {
    ...b,
    temporal: { after: b.temporal.after || null, before: b.temporal.before || null },
    escopo: { ...b.escopo, filetype: b.escopo.filetype || null },
    x: {
      ...b.x,
      since: b.x.since || null,
      until: b.x.until || null,
      lang: b.x.lang.trim() || null,
      min_faves: numOuNull(b.x.min_faves),
      min_retweets: numOuNull(b.x.min_retweets),
      min_replies: numOuNull(b.x.min_replies),
    },
  };
}
