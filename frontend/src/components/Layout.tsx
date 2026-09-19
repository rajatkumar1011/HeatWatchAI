import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { formatTime } from "../utils/format";
import {
  BellIcon,
  ChartIcon,
  ChevronDownIcon,
  CloudIcon,
  CollapseIcon,
  DocIcon,
  FaceIcon,
  FlameIcon,
  HomeIcon,
  LogoutIcon,
  MenuIcon,
  ShieldIcon,
  UserIcon,
  CloseIcon,
} from "./icons";

const navItems = [
  { to: "/dashboard", label: "Dashboard", Icon: HomeIcon },
  { to: "/weather", label: "Weather Monitoring", Icon: CloudIcon },
  { to: "/sentiment", label: "Public Sentiment", Icon: FaceIcon },
  { to: "/predictions", label: "Heatwave Predictions", Icon: ChartIcon },
  { to: "/alerts", label: "Alerts", Icon: BellIcon },
  { to: "/reports", label: "Historical Reports", Icon: DocIcon },
];

const pageTitles: Record<string, { title: string; context: string }> = {
  "/dashboard": { title: "Operations Dashboard", context: "Live monitoring overview" },
  "/weather": { title: "Weather Monitoring", context: "Stored observations & freshness" },
  "/sentiment": { title: "Public Sentiment", context: "NLP analysis of public posts" },
  "/predictions": { title: "Heatwave Predictions", context: "Severity assessments & history" },
  "/alerts": { title: "Alerts", context: "Application-generated early warnings" },
  "/reports": { title: "Historical Reports", context: "PDF & CSV exports" },
  "/admin": { title: "Administration", context: "Users, configuration & system health" },
  "/profile": { title: "User Profile", context: "Account details" },
};

function BrandMark({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand text-white shadow-sm">
        <FlameIcon className="h-4.5 w-4.5" style={{ width: 18, height: 18 }} />
      </div>
      {!compact && (
        <div className="min-w-0">
          <p className="truncate text-[13px] font-bold tracking-tight text-white">HeatWatch AI</p>
          <p className="truncate text-[9.5px] font-medium uppercase tracking-[0.14em] text-slate-400">
            Climate Intelligence
          </p>
        </div>
      )}
    </div>
  );
}

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [now, setNow] = useState(new Date());
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    setMobileOpen(false);
    setMenuOpen(false);
  }, [location.pathname]);

  const isAdmin = user?.role === "admin";
  const meta = pageTitles[location.pathname] ?? { title: "HeatWatch AI", context: "" };

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `group relative flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors duration-150 ${
      isActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"
    }`;

  const sidebarInner = (compact: boolean) => (
    <>
      <div className={`flex items-center px-4 pt-5 pb-4 ${compact ? "justify-center px-2" : ""}`}>
        <BrandMark compact={compact} />
      </div>
      <nav className="flex-1 space-y-0.5 px-2.5" aria-label="Primary">
        {navItems.map(({ to, label, Icon }) => (
          <NavLink key={to} to={to} className={navLinkClass} title={compact ? label : undefined}>
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-brand" aria-hidden />}
                <Icon className="h-[18px] w-[18px] shrink-0" />
                {!compact && <span className="truncate">{label}</span>}
              </>
            )}
          </NavLink>
        ))}
        {isAdmin && (
          <NavLink to="/admin" className={navLinkClass} title={compact ? "Administration" : undefined}>
            {({ isActive }) => (
              <>
                {isActive && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-brand" aria-hidden />}
                <ShieldIcon className="h-[18px] w-[18px] shrink-0" />
                {!compact && <span className="truncate">Administration</span>}
              </>
            )}
          </NavLink>
        )}
      </nav>
      <div className={`border-t border-white/10 p-2.5 ${compact ? "px-1.5" : ""}`}>
        {compact ? (
          <NavLink to="/profile" className="flex justify-center py-2" title="Profile">
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/10 text-[11px] font-bold text-white">
              {user?.username?.slice(0, 2).toUpperCase()}
            </span>
          </NavLink>
        ) : (
          <NavLink
            to="/profile"
            className="flex items-center gap-2.5 rounded-lg px-2 py-2 transition-colors hover:bg-white/5"
          >
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-[11px] font-bold text-white">
              {user?.username?.slice(0, 2).toUpperCase()}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[13px] font-semibold text-white">{user?.username}</span>
              <span className="block truncate text-[11px] text-slate-400">{user?.role_label}</span>
            </span>
          </NavLink>
        )}
      </div>
    </>
  );

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside
        className={`sticky top-0 hidden h-screen shrink-0 flex-col bg-navy transition-[width] duration-200 md:flex ${
          collapsed ? "w-[68px]" : "w-[228px]"
        }`}
      >
        {sidebarInner(collapsed)}
        <button
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="mx-auto mb-3 flex h-7 w-7 items-center justify-center rounded-md text-slate-500 transition-colors hover:bg-white/10 hover:text-white"
        >
          <CollapseIcon className={`h-4 w-4 transition-transform duration-200 ${collapsed ? "rotate-180" : ""}`} />
        </button>
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-slate-950/50" onClick={() => setMobileOpen(false)} aria-hidden />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-navy shadow-pop">
            <button
              aria-label="Close navigation"
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-4 text-slate-400 hover:text-white"
            >
              <CloseIcon className="h-5 w-5" />
            </button>
            {sidebarInner(false)}
          </aside>
        </div>
      )}

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-4 border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur md:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 md:hidden"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <MenuIcon className="h-5 w-5" />
            </button>
            <div className="min-w-0">
              <h2 className="truncate text-[15px] font-semibold leading-5 tracking-tight text-slate-900">{meta.title}</h2>
              <p className="hidden truncate text-xs text-slate-400 sm:block">{meta.context}</p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden text-right lg:block">
              <p className="tnum text-xs font-semibold text-slate-600">{formatTime(now.toISOString(), true)}</p>
              <p className="text-[10px] text-slate-400">IST · Asia/Kolkata</p>
            </div>
            <div className="relative">
              <button
                onClick={() => setMenuOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white py-1.5 pl-1.5 pr-2.5 text-sm shadow-sm transition-colors hover:bg-slate-50"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-900 text-[10px] font-bold text-white">
                  {user?.username?.slice(0, 2).toUpperCase()}
                </span>
                <span className="hidden font-semibold text-slate-700 sm:inline">{user?.username}</span>
                <ChevronDownIcon className="h-3.5 w-3.5 text-slate-400" />
              </button>
              {menuOpen && (
                <div role="menu" className="absolute right-0 top-full z-40 mt-1.5 w-52 rounded-xl border border-slate-200 bg-white p-1.5 shadow-pop">
                  <div className="border-b border-slate-100 px-2.5 pb-2 pt-1.5">
                    <p className="text-xs font-semibold text-slate-700">{user?.email}</p>
                    <p className="mt-0.5 text-[11px] text-slate-400">{user?.role_label}</p>
                  </div>
                  <button
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      navigate("/profile");
                    }}
                    className="mt-1 flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  >
                    <UserIcon className="h-4 w-4 text-slate-400" /> Profile settings
                  </button>
                  <button
                    role="menuitem"
                    onClick={() => {
                      logout();
                      navigate("/login");
                    }}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-red-600 hover:bg-red-50"
                  >
                    <LogoutIcon className="h-4 w-4" /> Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="min-w-0 flex-1">
          <div className="mx-auto w-full max-w-[1440px] px-4 py-5 md:px-6 md:py-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
