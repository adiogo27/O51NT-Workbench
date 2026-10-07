import { Bell, CalendarDays, Clock, FileSearch, Hash, Image, Link2, Megaphone, Newspaper, Palette, Search, Wrench } from "lucide-react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { AlertasBadge } from "@/components/AlertasBadge";
import { cn } from "@/lib/utils";
import AgendaPage from "@/pages/Agenda";
import AlertasPage from "@/pages/Alertas";
import BoletimPage from "@/pages/Boletim";
import ConvocacoesPage from "@/pages/Convocacoes";
import EvidencePage from "@/pages/Evidence";
import HashtagsPage from "@/pages/Hashtags";
import ImagesPage from "@/pages/Images";
import InvitesPage from "@/pages/Invites";
import MonitorsPage from "@/pages/Monitors";
import QueryBuilderPage from "@/pages/QueryBuilder";
import SettingsPage from "@/pages/Settings";
import ToolsPage from "@/pages/Tools";

const NAV = [
  { to: "/query", label: "Query Builder", icon: Search },
  { to: "/monitors", label: "Monitores", icon: Clock },
  { to: "/convocacoes", label: "Convocações", icon: Megaphone },
  { to: "/alertas", label: "Alertas", icon: Bell, badge: true },
  { to: "/agenda", label: "Agenda", icon: CalendarDays },
  { to: "/boletim", label: "Boletim", icon: Newspaper },
  { to: "/invites", label: "Convites", icon: Link2 },
  { to: "/hashtags", label: "Hashtags", icon: Hash },
  { to: "/images", label: "Imagens", icon: Image },
  { to: "/tools", label: "Ferramentas", icon: Wrench },
  { to: "/evidence", label: "Evidências", icon: FileSearch },
  { to: "/settings", label: "Tema", icon: Palette },
];

export default function App() {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <a href="#conteudo" className="sr-only-focusable absolute left-2 top-2 z-50 rounded bg-accent px-3 py-1 text-accent-foreground">
        Pular para o conteúdo
      </a>
      <aside className="border-b border-border bg-secondary text-secondary-foreground md:w-56 md:border-b-0 md:border-r">
        <div className="px-4 py-4">
          <p className="text-xl font-extrabold tracking-tight text-primary">O51NT</p>
          <p className="text-xs opacity-75">Workbench local</p>
        </div>
        <nav aria-label="Módulos" className="flex gap-1 overflow-x-auto px-2 pb-3 md:flex-col md:overflow-visible">
          {NAV.map(({ to, label, icon: Icon, badge }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 whitespace-nowrap rounded-md px-3 py-2 text-sm",
                  isActive ? "bg-primary text-primary-foreground" : "hover:bg-black/20",
                )
              }
            >
              <Icon size={16} aria-hidden /> {label}
              {badge && <AlertasBadge />}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main id="conteudo" className="mx-auto w-full max-w-6xl flex-1 p-4 md:p-8">
        <Routes>
          <Route path="/" element={<Navigate to="/query" replace />} />
          <Route path="/query" element={<QueryBuilderPage />} />
          <Route path="/monitors" element={<MonitorsPage />} />
          <Route path="/convocacoes" element={<ConvocacoesPage />} />
          <Route path="/alertas" element={<AlertasPage />} />
          <Route path="/agenda" element={<AgendaPage />} />
          <Route path="/boletim" element={<BoletimPage />} />
          <Route path="/invites" element={<InvitesPage />} />
          <Route path="/hashtags" element={<HashtagsPage />} />
          <Route path="/images" element={<ImagesPage />} />
          <Route path="/tools" element={<ToolsPage />} />
          <Route path="/evidence" element={<EvidencePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/query" replace />} />
        </Routes>
      </main>
    </div>
  );
}
