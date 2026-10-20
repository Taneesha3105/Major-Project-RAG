import {
  Briefcase,
  ChevronRight,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Search,
  Settings,
  Sun,
  UsersRound,
} from "lucide-react";
import { Suspense, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { dashboardApi, dealsApi } from "../api/services";
import { Avatar, Badge, PageLoader } from "../components/ui/primitives";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useAsync } from "../hooks/useAsync";
import { P, ROLES, STAGE_LABELS } from "../lib/constants";
import { classNames } from "../lib/format";

export function Logo({ compact }) {
  return (
    <div className="logo">
      <span className="logo-mark">
        <svg viewBox="0 0 64 64" width="20" height="20" aria-hidden>
          <circle cx="28" cy="28" r="12" fill="none" stroke="currentColor" strokeWidth="6" />
          <path d="M37 37l10 10" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
        </svg>
      </span>
      {!compact && (
        <span className="logo-text">
          Deal<b>Lens</b>
        </span>
      )}
    </div>
  );
}

function SystemPill() {
  const { data } = useAsync(() => dashboardApi.status(), []);
  if (!data) return null;
  const healthy = data.database && data.llm_configured;
  return (
    <span className={classNames("system-pill", healthy ? "ok" : "warn")} title={`LLM: ${data.llm_model} · Embeddings: ${data.embedding_model}`}>
      <span className="pulse-dot" />
      {healthy ? `AI online · ${data.llm_model}` : data.llm_configured ? "Database issue" : "LLM not configured"}
    </span>
  );
}

export default function AppLayout() {
  const { user, logout, can } = useAuth();
  const { theme, toggle } = useTheme();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [query, setQuery] = useState("");
  const navigate = useNavigate();
  const location = useLocation();
  const { data: deals } = useAsync(() => dealsApi.list(), [location.pathname === "/deals"]);

  useEffect(() => setMobileOpen(false), [location.pathname]);

  const nav = [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/deals", label: "Deals", icon: Briefcase },
    ...(can(P.USER_MANAGE) ? [{ to: "/admin/users", label: "Users & roles", icon: UsersRound }] : []),
    { to: "/settings", label: "Settings", icon: Settings },
  ];

  const submitSearch = (event) => {
    event.preventDefault();
    navigate(`/deals?search=${encodeURIComponent(query.trim())}`);
  };

  return (
    <div className={classNames("app-shell", mobileOpen && "nav-open")}>
      <aside className="sidebar">
        <div className="sidebar-top">
          <Logo />
        </div>
        <nav className="sidebar-nav">
          <span className="nav-section">Workspace</span>
          {nav.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => classNames("nav-link", isActive && "active")}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
          {deals?.length > 0 && (
            <>
              <span className="nav-section">Recent deals</span>
              {deals.slice(0, 5).map((deal) => (
                <NavLink
                  key={deal.id}
                  to={`/deals/${deal.id}`}
                  className={({ isActive }) => classNames("nav-link nav-deal", isActive && "active")}
                >
                  <span className="deal-dot" data-stage={deal.stage} />
                  <span className="truncate">{deal.code_name || deal.name}</span>
                  <small>{STAGE_LABELS[deal.stage]}</small>
                </NavLink>
              ))}
            </>
          )}
        </nav>
        <div className="sidebar-user">
          <Avatar name={user.full_name} size={36} />
          <div className="sidebar-user-info">
            <strong className="truncate">{user.full_name}</strong>
            <span>{ROLES[user.role]?.label}</span>
          </div>
          <button className="icon-btn ghost" onClick={logout} title="Sign out" aria-label="Sign out">
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} />

      <div className="main">
        <header className="topbar">
          <button className="icon-btn ghost mobile-only" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu size={20} />
          </button>
          <form className="topbar-search" onSubmit={submitSearch}>
            <Search size={16} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search deals, targets, acquirers…"
              aria-label="Search deals"
            />
            <kbd>↵</kbd>
          </form>
          <div className="topbar-right">
            <SystemPill />
            <button className="icon-btn ghost" onClick={toggle} aria-label="Toggle theme" title="Toggle theme">
              {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <NavLink to="/settings" className="topbar-user">
              <Avatar name={user.full_name} size={30} />
              <span className="desktop-only">{user.full_name.split(" ")[0]}</span>
              <Badge tone={ROLES[user.role]?.tone}>{ROLES[user.role]?.label}</Badge>
              <ChevronRight size={14} className="desktop-only" />
            </NavLink>
          </div>
        </header>
        <main className="content">
          <Suspense fallback={<PageLoader />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
