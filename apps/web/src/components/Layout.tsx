import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import { ThemeControl } from "./ThemeControl";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/datasets", label: "Datasets" },
  { to: "/graph", label: "Graph Playground" },
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
    <div className="flex min-h-screen flex-col bg-ui-canvas sm:flex-row">
      <aside className="flex w-full flex-col border-b border-ui-border bg-ui-surface sm:w-56 sm:border-b-0 sm:border-r">
        <div className="border-b border-ui-border px-4 py-4">
          <h1 className="text-lg font-semibold text-ui-text">OpenGraphMemory</h1>
          <p className="mt-1 truncate text-xs text-ui-subdued" title={projectId}>
            {projectId.slice(0, 13)}…
          </p>
        </div>
        <nav className="flex flex-1 gap-1 overflow-x-auto px-2 py-3 sm:flex-col">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium ${
                  isActive
                    ? "bg-stone-900 text-ui-inverse"
                    : "text-ui-subdued hover:bg-ui-muted"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex items-center gap-2 border-t border-ui-border p-2 sm:block">
          <div className="p-1"><ThemeControl /></div>
          <button
            type="button"
            onClick={handleLogout}
            className="w-full rounded-md px-3 py-2 text-left text-sm font-medium text-ui-subdued hover:bg-ui-muted"
          >
            Logout
          </button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
