import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { api, type AuthEstado, EVENTO_NAO_AUTENTICADO, type Usuario } from "@/lib/api";
import { useSettingsStore } from "@/theme/ThemeProvider";

interface AuthCtx {
  carregando: boolean;
  /** Autenticação ligada no servidor (O51NT_ADMIN_EMAIL). Local, sem login, é `false`. */
  ativo: boolean;
  autenticado: boolean;
  usuario: Usuario | null;
  canal: AuthEstado["canal"];
  validadeMin: number;
  admin: boolean;
  recarregar: () => Promise<void>;
  sair: () => Promise<void>;
}

const SEM_AUTH: AuthEstado = { ativo: false, autenticado: true, usuario: null, canal: "nenhum", validade_min: 10 };
const Ctx = React.createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [estado, setEstado] = React.useState<AuthEstado | null>(null);
  const [carregando, setCarregando] = React.useState(true);
  const qc = useQueryClient();

  const recarregar = React.useCallback(async () => {
    try {
      const e = await api.get<AuthEstado>("/api/auth/estado");
      setEstado(e);
      if (e.autenticado) {
        void useSettingsStore.getState().load();
        void qc.invalidateQueries();
      }
    } catch {
      setEstado(SEM_AUTH); // backend fora do ar ou sem a rota: não bloqueia a interface
    } finally {
      setCarregando(false);
    }
  }, [qc]);

  React.useEffect(() => {
    void recarregar();
  }, [recarregar]);

  React.useEffect(() => {
    const h = () => setEstado((e) => (e && e.ativo ? { ...e, autenticado: false, usuario: null } : e));
    window.addEventListener(EVENTO_NAO_AUTENTICADO, h);
    return () => window.removeEventListener(EVENTO_NAO_AUTENTICADO, h);
  }, []);

  const sair = React.useCallback(async () => {
    try {
      await api.post("/api/auth/sair");
    } finally {
      qc.clear();
      setEstado((e) => (e ? { ...e, autenticado: false, usuario: null } : e));
    }
  }, [qc]);

  const e = estado ?? SEM_AUTH;
  const value: AuthCtx = {
    carregando,
    ativo: e.ativo,
    autenticado: e.autenticado,
    usuario: e.usuario,
    canal: e.canal,
    validadeMin: e.validade_min,
    admin: !e.ativo || e.usuario?.papel === "admin",
    recarregar,
    sair,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = React.useContext(Ctx);
  if (!v) throw new Error("useAuth fora de <AuthProvider>");
  return v;
}
