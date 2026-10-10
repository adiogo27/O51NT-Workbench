import { KeyRound, Mail, ShieldCheck, UserCog, UserRound } from "lucide-react";
import * as React from "react";
import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api, ApiError, type Usuario } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const CANAL_MSG: Record<string, string> = {
  email: "Enviamos um código de 6 dígitos para o seu e-mail (confira também a pasta de spam).",
  telegram: "Este servidor está sem e-mail (SMTP) configurado: o código foi enviado pelo bot do Telegram.",
  journal: "Este servidor está sem e-mail (SMTP) configurado: o código ficou registrado no journal do serviço e só o operador da VM consegue lê-lo (journalctl -u o51nt | grep CODIGO). Configure o SMTP com deploy/vps/segredos.sh.",
  nenhum: "",
};

/** Login por e-mail autorizado + código de uso único. Nunca revela se um e-mail está cadastrado. */
export default function LoginPage() {
  const auth = useAuth();
  const [etapa, setEtapa] = React.useState<"email" | "codigo">("email");
  // Perfil escolhido na tela: o fluxo é o mesmo (e-mail cadastrado + código); "Administrador" só confere o papel ao entrar.
  const [perfil, setPerfil] = React.useState<"usuario" | "admin">("usuario");
  const [email, setEmail] = React.useState("");
  const [codigo, setCodigo] = React.useState("");
  const [canal, setCanal] = React.useState<string>(auth.canal);
  const [erro, setErro] = React.useState<string | null>(null);
  const [ocupado, setOcupado] = React.useState(false);
  const [espera, setEspera] = React.useState(0);
  const refCodigo = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    if (espera <= 0) return;
    const t = window.setTimeout(() => setEspera((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [espera]);

  const solicitar = async (ev?: React.FormEvent) => {
    ev?.preventDefault();
    setErro(null);
    setOcupado(true);
    try {
      const r = await api.post<{ ok: boolean; canal: string; validade_min: number }>("/api/auth/solicitar", { email: email.trim() });
      setCanal(r.canal);
      setEtapa("codigo");
      setCodigo("");
      setEspera(60);
      window.setTimeout(() => refCodigo.current?.focus(), 50);
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "falha ao pedir o código");
    } finally {
      setOcupado(false);
    }
  };

  const verificar = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setErro(null);
    setOcupado(true);
    try {
      await api.post("/api/auth/verificar", { email: email.trim(), codigo: codigo.replace(/\D/g, "") });
      if (perfil === "admin") {
        const eu = await api.get<Usuario>("/api/auth/eu");
        if (eu.papel !== "admin") {
          await api.post("/api/auth/sair").catch(() => undefined);
          setErro("Esta conta não tem perfil de administrador. Entre como Usuário.");
          return;
        }
      }
      await auth.recarregar();
    } catch (e) {
      setErro(e instanceof ApiError ? e.message : "falha ao verificar o código");
    } finally {
      setOcupado(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-4 text-foreground">
      <Card className="w-full max-w-md space-y-4">
        <div>
          <p className="text-2xl font-extrabold tracking-tight text-primary">O51NT</p>
          <p className="text-sm text-muted-foreground">Acesso restrito a usuários autorizados.</p>
        </div>

        {etapa === "email" ? (
          <form onSubmit={solicitar} className="space-y-3" aria-label="Identificação">
            <fieldset className="grid grid-cols-2 gap-2" aria-label="Perfil de acesso">
              <legend className="mb-1 text-xs text-muted-foreground">Entrar como</legend>
              <button type="button" aria-pressed={perfil === "usuario"} onClick={() => setPerfil("usuario")} className={`flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm ${perfil === "usuario" ? "border-primary bg-primary/10 font-medium" : "border-border"}`}>
                <UserRound size={16} aria-hidden /> Usuário
              </button>
              <button type="button" aria-pressed={perfil === "admin"} onClick={() => setPerfil("admin")} className={`flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-sm ${perfil === "admin" ? "border-primary bg-primary/10 font-medium" : "border-border"}`}>
                <UserCog size={16} aria-hidden /> Administrador
              </button>
            </fieldset>
            <p className="text-xs text-muted-foreground">{perfil === "admin" ? "Administradores cadastram usuários e veem a auditoria. O código de acesso chega pelo e-mail do administrador." : "Somente e-mails cadastrados por um administrador recebem o código de acesso de uso único."}</p>
            <Field label="E-mail autorizado" htmlFor="login-email">
              <Input id="login-email" type="email" autoComplete="username" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="voce@exemplo.gov.br" />
            </Field>
            <Button type="submit" className="w-full" disabled={ocupado || !email.includes("@")}>
              <Mail size={16} aria-hidden /> {ocupado ? "Enviando…" : perfil === "admin" ? "Receber código de administrador" : "Receber código de acesso"}
            </Button>
          </form>
        ) : (
          <form onSubmit={verificar} className="space-y-3" aria-label="Código de acesso">
            {CANAL_MSG[canal] && <Alert variant={canal === "email" ? "info" : "warning"}>{CANAL_MSG[canal]}</Alert>}
            <Field label={`Código enviado para ${email}`} htmlFor="login-codigo" hint={`Vale por ${auth.validadeMin} minutos e só uma vez.`}>
              <Input
                id="login-codigo"
                ref={refCodigo}
                inputMode="numeric"
                pattern="[0-9 ]*"
                autoComplete="one-time-code"
                maxLength={7}
                required
                value={codigo}
                onChange={(e) => setCodigo(e.target.value)}
                placeholder="000000"
                className="text-center text-2xl tracking-[0.5em]"
              />
            </Field>
            <Button type="submit" className="w-full" disabled={ocupado || codigo.replace(/\D/g, "").length !== 6}>
              <KeyRound size={16} aria-hidden /> {ocupado ? "Verificando…" : "Entrar"}
            </Button>
            <div className="flex justify-between text-xs">
              <button type="button" className="underline" onClick={() => { setEtapa("email"); setErro(null); }}>
                Trocar e-mail
              </button>
              <button type="button" className="underline disabled:opacity-50" disabled={espera > 0 || ocupado} onClick={() => void solicitar()}>
                {espera > 0 ? `Reenviar em ${espera}s` : "Reenviar código"}
              </button>
            </div>
          </form>
        )}

        {erro && <Alert variant="error">{erro}</Alert>}
        <p className="flex items-start gap-2 text-xs text-muted-foreground">
          <ShieldCheck size={14} aria-hidden className="mt-0.5 shrink-0" />
          <span>Somente administradores cadastram usuários. Tentativas são registradas com IP e horário; após falhas repetidas o acesso é bloqueado temporariamente.</span>
        </p>
      </Card>
    </main>
  );
}
