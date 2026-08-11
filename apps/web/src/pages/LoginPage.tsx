import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Key, Layers, Shield, ArrowRight } from "lucide-react";
import { projectsApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import { useAuthStore } from "../store/auth";
import { ThemeControl } from "../components/ThemeControl";

export default function LoginPage() {
  const navigate = useNavigate();
  const setCredentials = useAuthStore((s) => s.setCredentials);
  const setAdminKey = useAuthStore((s) => s.setAdminKey);

  const [apiKey, setApiKey] = useState("");
  const [projectId, setProjectId] = useState("");
  const [adminKey, setAdminKeyState] = useState("");
  const [mode, setMode] = useState<"connect" | "create">("connect");
  const [projectName, setProjectName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Quick auto-fill helper for the newly indexed codebase dataset
  const handleAutoFill = () => {
    setProjectId("66ebb1d0-51b0-4aea-aee9-8e386b34e643");
    setApiKey("ogm_HQAEYaqKzPU5chzqroTMc7rDjFupmptkKXQuCPIy-BE");
    setError(null);
  };

  const handleConnect = (event: React.FormEvent) => {
    event.preventDefault();
    if (!apiKey.trim() || !projectId.trim()) {
      setError("API key and project ID are required");
      return;
    }
    setCredentials({ apiKey: apiKey.trim(), projectId: projectId.trim() });
    if (adminKey.trim()) setAdminKey(adminKey.trim());
    navigate("/");
  };

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!adminKey.trim() || !projectName.trim()) {
      setError("Admin key and project name are required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setAdminKey(adminKey.trim());
      const created = await projectsApi.create(projectName.trim());
      setCredentials({ apiKey: created.api_key, projectId: created.id });
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "project creation failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4 py-12 text-main antialiased selection:bg-mac-accent selection:text-white">
      {/* macOS Window Dialog Box */}
      <div className="w-full max-w-md rounded-2xl border border-mac bg-surface p-8 shadow-xl">
        {/* macOS Traffic Dots Header */}
        <div className="flex items-center justify-between border-b border-mac pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex items-center gap-1.5 mr-1">
              <span className="h-3 w-3 rounded-full bg-[#ff5f56] inline-block"></span>
              <span className="h-3 w-3 rounded-full bg-[#ffbd2e] inline-block"></span>
              <span className="h-3 w-3 rounded-full bg-[#27c93f] inline-block"></span>
            </div>
            <span className="text-sm font-bold text-main">OpenGraphMemory</span>
          </div>
          <ThemeControl />
        </div>

        <div className="mt-5 space-y-1">
          <h1 className="text-xl font-bold text-main">Connect Workspace</h1>
          <p className="text-xs text-subdued">
            Enter project credentials to access the Knowledge Graph dashboard.
          </p>
        </div>

        {/* macOS Auto-fill Helper Banner */}
        <div className="mt-4 rounded-xl border border-mac bg-muted p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-main">Indexed Codebase Dataset</span>
            <button
              type="button"
              onClick={handleAutoFill}
              className="rounded-lg bg-mac-accent px-2.5 py-1 text-[11px] font-bold text-white shadow-sm hover:opacity-90 active:scale-95"
            >
              Auto-Fill Credentials
            </button>
          </div>
          <p className="mt-1 text-[11px] text-subdued">
            Dataset: <code className="font-mono text-mac-accent font-bold">ds_019fefae...</code> (2,408 entities, 3,521 relations).
          </p>
        </div>

        {/* macOS Segmented Switcher Tabs */}
        <div className="mt-5 flex rounded-xl border border-mac bg-muted p-1">
          <button
            type="button"
            onClick={() => setMode("connect")}
            className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              mode === "connect"
                ? "bg-mac-accent !text-white shadow-sm"
                : "text-subdued hover:text-main"
            }`}
          >
            Connect Project
          </button>
          <button
            type="button"
            onClick={() => setMode("create")}
            className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
              mode === "create"
                ? "bg-mac-accent !text-white shadow-sm"
                : "text-subdued hover:text-main"
            }`}
          >
            Create New Project
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mt-4 rounded-xl border border-rose-300 bg-rose-50 dark:bg-rose-950/40 p-2.5 text-xs font-medium text-rose-700 dark:text-rose-300">
            {error}
          </div>
        )}

        {/* Connect Form */}
        {mode === "connect" ? (
          <form onSubmit={handleConnect} className="mt-5 space-y-3.5">
            <Field
              label="Project ID"
              value={projectId}
              onChange={setProjectId}
              placeholder="e.g. 66ebb1d0-51b0-4aea-aee9-8e386b34e643"
              icon={Layers}
            />
            <Field
              label="API Key"
              value={apiKey}
              onChange={setApiKey}
              type="password"
              placeholder="ogm_..."
              icon={Key}
            />
            <Field
              label="Admin Key (optional)"
              value={adminKey}
              onChange={setAdminKeyState}
              type="password"
              placeholder="ogm-admin-secret-key-local"
              icon={Shield}
            />

            <button
              type="submit"
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl bg-mac-accent px-4 py-2.5 text-xs font-bold text-white shadow-sm hover:opacity-90 active:scale-95 transition-all"
            >
              <span>Connect Workspace</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </form>
        ) : (
          /* Create Form */
          <form onSubmit={handleCreate} className="mt-5 space-y-3.5">
            <Field
              label="Admin Secret Key"
              value={adminKey}
              onChange={setAdminKeyState}
              type="password"
              placeholder="ogm-admin-secret-key-local"
              icon={Shield}
            />
            <Field
              label="New Project Name"
              value={projectName}
              onChange={setProjectName}
              placeholder="e.g. My Codebase Graph"
              icon={Layers}
            />

            <button
              type="submit"
              disabled={busy}
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-xl bg-mac-accent px-4 py-2.5 text-xs font-bold text-white disabled:opacity-50 active:scale-95 transition-all"
            >
              <span>{busy ? "Creating..." : "Create Project"}</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  icon: Icon,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  icon: React.ElementType;
}) {
  return (
    <label className="block space-y-1 text-xs font-semibold text-main">
      <span className="flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5 text-mac-accent" />
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="block w-full rounded-lg border border-mac bg-canvas px-3 py-2 text-xs text-main placeholder-subdued focus:border-mac-accent focus:outline-none"
      />
    </label>
  );
}
