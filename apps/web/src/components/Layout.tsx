import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { 
  LayoutDashboard, 
  Database, 
  Network, 
  Brain, 
  LogOut, 
  Layers
} from "lucide-react";
import { useAuthStore } from "../store/auth";
import { ThemeControl } from "./ThemeControl";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/datasets", label: "Datasets", icon: Database },
  { to: "/graph", label: "Graph Playground", icon: Network },
  { to: "/memory", label: "Agent Memory", icon: Brain },
];

export default function Layout() {
  const navigate = useNavigate();
  const clear = useAuthStore((s) => s.clear);
  const projectId = useAuthStore((s) => s.projectId);

  const handleLogout = () => {
    clear();
    navigate("/login");
  };

  return (
    <div className="flex min-h-screen flex-col bg-canvas sm:flex-row text-main antialiased selection:bg-mac-accent selection:text-white">
      {/* Sidebar Navigation */}
      <aside className="flex w-full flex-col border-b border-mac bg-sidebar sm:w-60 sm:border-b-0 sm:border-r">
        {/* Window Titlebar Header */}
        <div className="border-b border-mac px-4 py-3.5 space-y-3">
          {/* Status Indicators */}
          <div className="flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-full bg-[#ff5f56] border border-[#e0443e]/50 inline-block"></span>
            <span className="h-3 w-3 rounded-full bg-[#ffbd2e] border border-[#dea123]/50 inline-block"></span>
            <span className="h-3 w-3 rounded-full bg-[#27c93f] border border-[#1aab29]/50 inline-block"></span>
          </div>

          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-mac-accent text-white font-bold text-xs shadow-sm">
              OGM
            </div>
            <div>
              <h1 className="text-sm font-bold text-main tracking-tight">
                OpenGraphMemory
              </h1>
              <p className="text-[10px] font-semibold text-subdued">
                Knowledge Graph Engine
              </p>
            </div>
          </div>

          {/* Active Project Box */}
          <div className="rounded-lg border border-mac bg-surface p-2">
            <div className="flex items-center gap-1.5 text-[10px] font-medium text-subdued">
              <Layers className="h-3 w-3 text-mac-accent" />
              <span>Project ID</span>
            </div>
            <p className="mt-0.5 truncate font-mono text-[11px] font-semibold text-main" title={projectId}>
              {projectId ? projectId.slice(0, 16) + "…" : "Local Context"}
            </p>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex flex-1 gap-1 overflow-x-auto px-2.5 py-3 sm:flex-col">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-150 ${
                    isActive
                      ? "bg-mac-accent !text-white font-bold shadow-sm"
                      : "text-main hover:bg-muted"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    <Icon className={`h-4 w-4 ${isActive ? "!text-white" : "text-subdued"}`} />
                    <span className={isActive ? "!text-white" : ""}>{item.label}</span>
                  </>
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* Footer Actions */}
        <div className="border-t border-mac p-3 space-y-2">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-xs text-subdued font-medium">Appearance</span>
            <ThemeControl />
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs font-semibold text-main hover:bg-muted hover:text-rose-600 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            <span>Logout</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="min-w-0 flex-1 overflow-auto bg-canvas">
        <Outlet />
      </main>
    </div>
  );
}
