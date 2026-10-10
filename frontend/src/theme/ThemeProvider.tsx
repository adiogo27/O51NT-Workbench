import * as React from "react";
import { create } from "zustand";
import { api, type AppSettings } from "@/lib/api";
import { contrastText } from "@/lib/utils";

export const DEFAULT_SETTINGS: AppSettings = {
  tema: { primary: "#0091d5", secondary: "#1e293b", background: "#0b1220", foreground: "#e2e8f0", accent: "#f2e08a", radius: 0.5 },
  tipografia: { fontFamily: "Inter", fontSizeBase: 16 },
  preferencias: {
    navegadorPadrao: "auto",
    historicoRetencaoDias: 90,
    historicoMaxEntradas: 10000,
    radarAtivo: true,
    radarIntervaloMin: 10,
    convocacoesAtivo: false,
    convocacoesIntervaloMin: 30,
    convocacoesPerfilML: "leve",
    convocacoesLimiarAlerta: 55,
    convocacoesLimiarCritico: 75,
    convocacoesPesoLexico: 0.45,
    convocacoesPesoVisual: 0.2,
    convocacoesPesoReferencia: 0.2,
    convocacoesPesoMonitor: 0.15,
    convocacoesBonusDistribuicao: 15,
    convocacoesTermosExtra: [],
    convocacoesTermosExcluir: [],
    convocacoesMaxImagensCiclo: 40,
    convocacoesDescarregarMin: 10,
    convocacoesAnalisarFeeds: true,
    convocacoesCanalAlerta: "jsonl",
    convocacoesWebhookUrl: null,
    convocacoesRetencaoDias: 180,
    convitesRespeitarRobots: true,
    convitesVerificarAuto: false,
    convitesVerificarIntervaloHoras: 24,
    iaAtivo: false,
    iaIntervaloMin: 5,
    iaMaxItensCiclo: 25,
    iaCustoDiarioUsd: 1,
    iaModeloTriagem: "anthropic/claude-haiku-5-5",
    iaModeloPadrao: null,
    iaModeloLeve: "anthropic/claude-haiku-5-5",
    iaPesquisarSeveridadeMin: "alta",
    iaBoletim: "aprovar",
    iaAgenda: "aprovar",
    iaTelegramRelevante: true,
    iaResumoHoras: 2,
    iaSuprimirAlertasBrutos: true,
    iaMarcarLidos: true,
    iaTextoMaxChars: 6000,
    iaAterramento: true,
    ferramentasSensiveisAtivas: false,
  },
};

export const FONTES: Record<string, string> = {
  Inter: "Inter, ui-sans-serif, system-ui, sans-serif",
  System: "ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  "JetBrains Mono": "'JetBrains Mono', ui-monospace, monospace",
  "Fira Code": "'Fira Code', ui-monospace, monospace",
  "DejaVu Sans": "'DejaVu Sans', sans-serif",
  Serif: "Georgia, 'Times New Roman', serif",
};

interface SettingsState {
  settings: AppSettings;
  loaded: boolean;
  setSettings: (s: AppSettings) => void;
  load: () => Promise<void>;
  save: (s: AppSettings) => Promise<AppSettings>;
}

export const useSettingsStore = create<SettingsState>((set) => ({
  settings: DEFAULT_SETTINGS,
  loaded: false,
  setSettings: (s) => set({ settings: s }),
  load: async () => {
    try {
      set({ settings: await api.get<AppSettings>("/api/settings"), loaded: true });
    } catch {
      set({ loaded: true });
    }
  },
  save: async (s) => {
    const saved = await api.put<AppSettings>("/api/settings", s);
    set({ settings: saved });
    return saved;
  },
}));

export function applyTheme(s: AppSettings, el: HTMLElement = document.documentElement): void {
  const t = s.tema;
  const vars: Record<string, string> = {
    "--color-primary": t.primary,
    "--color-primary-foreground": contrastText(t.primary),
    "--color-secondary": t.secondary,
    "--color-secondary-foreground": contrastText(t.secondary),
    "--color-background": t.background,
    "--color-foreground": t.foreground,
    "--color-accent": t.accent,
    "--color-accent-foreground": contrastText(t.accent),
    "--radius": `${t.radius}rem`,
    "--font-family": FONTES[s.tipografia.fontFamily] ?? s.tipografia.fontFamily,
    "--font-size-base": `${s.tipografia.fontSizeBase}px`,
  };
  Object.entries(vars).forEach(([k, v]) => el.style.setProperty(k, v));
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { settings, load } = useSettingsStore();
  React.useEffect(() => {
    void load();
  }, [load]);
  React.useEffect(() => applyTheme(settings), [settings]);
  return <>{children}</>;
}
