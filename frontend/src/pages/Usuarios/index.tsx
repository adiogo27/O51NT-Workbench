import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, Trash2, UserPlus } from "lucide-react";
import * as React from "react";
import { ErrorText } from "@/components/shared";
import { Alert, Badge, Button, Card, CardTitle, Empty, Field, Input, PageHeader, Select } from "@/components/ui";
import { api, type EventoAcesso, type SessaoInfo, type Usuario } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString("pt-BR") : "—");

const EVENTO_LABEL: Record<string, string> = {
  codigo_solicitado: "código enviado",
  codigo_recusado: "e-mail não autorizado",
  codigo_limite: "limite de pedidos",
  login_ok: "login",
  login_falha: "falha de login",
  bloqueado: "bloqueado",
  logout: "saída",
  sessoes_revogadas: "sessões encerradas",
  usuario_criado: "usuário criado",
  usuario_alterado: "usuário alterado",
  usuario_removido: "usuário removido",
};

/** Administração de acesso: só administradores veem esta página (o backend também exige o papel). */
export default function UsuariosPage() {
  const auth = useAuth();
  const qc = useQueryClient();
  const usuarios = useQuery({ queryKey: ["auth-usuarios"], queryFn: () => api.get<Usuario[]>("/api/auth/usuarios") });
  const eventos = useQuery({ queryKey: ["auth-eventos"], queryFn: () => api.get<EventoAcesso[]>("/api/auth/eventos?limit=60") });
  const sessoes = useQuery({ queryKey: ["auth-sessoes"], queryFn: () => api.get<SessaoInfo[]>("/api/auth/sessoes"), enabled: auth.ativo });
  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: ["auth-usuarios"] });
    void qc.invalidateQueries({ queryKey: ["auth-eventos"] });
  };

  const [novo, setNovo] = React.useState({ email: "", nome: "", papel: "analista", telegram_chat_id: "" });
  const criar = useMutation({
    mutationFn: () => api.post<Usuario>("/api/auth/usuarios", { ...novo, telegram_chat_id: novo.telegram_chat_id || null }),
    onSuccess: () => {
      setNovo({ email: "", nome: "", papel: "analista", telegram_chat_id: "" });
      invalidar();
    },
  });
  const alterar = useMutation({ mutationFn: (p: { id: number; dados: Partial<Usuario> }) => api.patch<Usuario>(`/api/auth/usuarios/${p.id}`, p.dados), onSuccess: invalidar });
  const remover = useMutation({ mutationFn: (id: number) => api.del(`/api/auth/usuarios/${id}`), onSuccess: invalidar });
  const revogar = useMutation({ mutationFn: () => api.post<{ revogadas: number }>("/api/auth/sessoes/revogar-outras"), onSuccess: () => void qc.invalidateQueries({ queryKey: ["auth-sessoes"] }) });

  if (!auth.admin) {
    return (
      <Alert variant="error">
        <ShieldAlert size={16} aria-hidden className="mr-1 inline" /> Apenas administradores podem gerenciar usuários.
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Usuários e acesso" description="Quem pode entrar no painel. O login exige e-mail autorizado + código de uso único; só administradores cadastram pessoas." />

      {!auth.ativo && <Alert variant="warning">Autenticação desligada neste ambiente (defina O51NT_ADMIN_EMAIL no .env do servidor). Os cadastros abaixo valem quando ela estiver ativa.</Alert>}

      <Card>
        <CardTitle>Adicionar usuário</CardTitle>
        <form
          className="grid gap-3 md:grid-cols-5"
          onSubmit={(e) => {
            e.preventDefault();
            criar.mutate();
          }}
        >
          <Field label="E-mail" htmlFor="u-email">
            <Input id="u-email" type="email" required value={novo.email} onChange={(e) => setNovo({ ...novo, email: e.target.value })} />
          </Field>
          <Field label="Nome" htmlFor="u-nome">
            <Input id="u-nome" value={novo.nome} onChange={(e) => setNovo({ ...novo, nome: e.target.value })} />
          </Field>
          <Field label="Papel" htmlFor="u-papel">
            <Select id="u-papel" value={novo.papel} onChange={(e) => setNovo({ ...novo, papel: e.target.value })}>
              <option value="analista">analista</option>
              <option value="admin">admin</option>
            </Select>
          </Field>
          <Field label="Chat ID Telegram (opcional)" htmlFor="u-tg" hint="código vai pelo bot se o servidor estiver sem SMTP">
            <Input id="u-tg" inputMode="numeric" value={novo.telegram_chat_id} onChange={(e) => setNovo({ ...novo, telegram_chat_id: e.target.value })} />
          </Field>
          <div className="flex items-end">
            <Button type="submit" disabled={criar.isPending || !novo.email.includes("@")}>
              <UserPlus size={16} aria-hidden /> Adicionar
            </Button>
          </div>
        </form>
        <ErrorText error={criar.error} />
      </Card>

      <Card>
        <CardTitle>Autorizados ({usuarios.data?.length ?? 0})</CardTitle>
        <ErrorText error={usuarios.error ?? alterar.error ?? remover.error} />
        {usuarios.data && usuarios.data.length === 0 && <Empty>Nenhum usuário.</Empty>}
        {usuarios.data && usuarios.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr>
                  <th className="py-1 pr-3">E-mail</th>
                  <th className="py-1 pr-3">Nome</th>
                  <th className="py-1 pr-3">Papel</th>
                  <th className="py-1 pr-3">Estado</th>
                  <th className="py-1 pr-3">Último login</th>
                  <th className="py-1 pr-3">Cadastro</th>
                  <th className="py-1" />
                </tr>
              </thead>
              <tbody>
                {usuarios.data.map((u) => {
                  const eu = auth.usuario?.id === u.id;
                  return (
                    <tr key={u.id} className="border-t border-border">
                      <td className="py-2 pr-3 font-medium">
                        {u.email} {eu && <Badge variant="muted">você</Badge>}
                      </td>
                      <td className="py-2 pr-3">{u.nome || "—"}</td>
                      <td className="py-2 pr-3">
                        <Badge variant={u.papel === "admin" ? "success" : "muted"}>{u.papel}</Badge>
                      </td>
                      <td className="py-2 pr-3">
                        <Badge variant={u.ativo ? "success" : "muted"}>{u.ativo ? "ativo" : "inativo"}</Badge>
                      </td>
                      <td className="py-2 pr-3 text-xs">{fmt(u.ultimo_login)}</td>
                      <td className="py-2 pr-3 text-xs">
                        {fmt(u.criado_em)} <span className="text-muted-foreground">por {u.criado_por}</span>
                      </td>
                      <td className="py-2">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="outline" disabled={eu || alterar.isPending} onClick={() => alterar.mutate({ id: u.id, dados: { papel: u.papel === "admin" ? "analista" : "admin" } })}>
                            {u.papel === "admin" ? "tornar analista" : "tornar admin"}
                          </Button>
                          <Button size="sm" variant="outline" disabled={eu || alterar.isPending} onClick={() => alterar.mutate({ id: u.id, dados: { ativo: !u.ativo } })}>
                            {u.ativo ? "desativar" : "reativar"}
                          </Button>
                          <Button size="sm" variant="danger" disabled={eu || remover.isPending} aria-label={`remover ${u.email}`} onClick={() => window.confirm(`Remover ${u.email}?`) && remover.mutate(u.id)}>
                            <Trash2 size={14} aria-hidden />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {auth.ativo && (
        <Card>
          <CardTitle>Minhas sessões</CardTitle>
          <ul className="space-y-1 text-sm">
            {(sessoes.data ?? []).map((s) => (
              <li key={s.id} className="flex flex-wrap gap-2">
                {s.atual && <Badge variant="success">esta</Badge>}
                <span className="code text-xs">{s.ip || "?"}</span>
                <span className="text-xs text-muted-foreground">{s.user_agent.slice(0, 60)}</span>
                <span className="text-xs">último uso {fmt(s.ultimo_uso)} · expira {fmt(s.expira_em)}</span>
              </li>
            ))}
          </ul>
          <div className="mt-2 flex items-center gap-2">
            <Button size="sm" variant="outline" disabled={revogar.isPending} onClick={() => revogar.mutate()}>
              Encerrar as outras sessões
            </Button>
            {revogar.data && <span className="text-xs text-muted-foreground">{revogar.data.revogadas} encerrada(s)</span>}
          </div>
        </Card>
      )}

      <Card>
        <CardTitle>Auditoria de acesso (últimos 60 eventos)</CardTitle>
        <ErrorText error={eventos.error} />
        <ul className="divide-y divide-border text-xs">
          {(eventos.data ?? []).map((e) => (
            <li key={e.id} className="flex flex-wrap gap-2 py-1">
              <span className="w-36 shrink-0 text-muted-foreground">{fmt(e.em)}</span>
              <Badge variant={e.ok ? "muted" : "danger"}>{EVENTO_LABEL[e.evento] ?? e.evento}</Badge>
              <span className="font-medium">{e.email || "—"}</span>
              <span className="code">{e.ip || "—"}</span>
              <span className="text-muted-foreground">{e.detalhe}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
