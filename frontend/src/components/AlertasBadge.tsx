import { useQuery } from "@tanstack/react-query";
import { api, type AlertasContagem } from "@/lib/api";

/** Contador de alertas não lidos no menu lateral (poll 20 s). Vermelho quando há críticos. */
export function AlertasBadge() {
  const { data } = useQuery({ queryKey: ["alertas-contagem"], queryFn: () => api.get<AlertasContagem>("/api/alertas/contagem"), refetchInterval: 20000 });
  if (!data || data.total === 0) return null;
  return (
    <span
      className={`ml-auto inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold ${data.criticos ? "bg-danger text-white" : "bg-warning text-black"}`}
      aria-label={`${data.total} alerta(s) não lido(s)${data.criticos ? `, ${data.criticos} crítico(s)` : ""}`}
    >
      {data.total > 99 ? "99+" : data.total}
    </span>
  );
}
