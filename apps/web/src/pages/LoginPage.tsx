import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { projectsApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import { useAuthStore } from "../store/auth";

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
    <div className="flex min-h-screen items-center justify-center bg-stone-100 px-4">
      <div className="w-full max-w-md rounded-xl border border-stone-200 bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-semibold text-stone-900">OpenGraphMemory</h1>
        <p className="mt-1 text-sm text-stone-500">
          Enter project credentials to access the dashboard.
        </p>

        <div className="mt-6 flex gap-2 rounded-lg bg-stone-100 p-1">
          <button
            type="button"
            onClick={() => setMode("connect")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium ${
              mode === "connect" ? "bg-white text-stone-900 shadow-sm" : "text-stone-600"
            }`}
          >
            Connect
          </button>
          <button
            type="button"
            onClick={() => setMode("create")}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium ${
              mode === "create" ? "bg-white text-stone-900 shadow-sm" : "text-stone-600"
            }`}
          >
            Create New
          </button>
        </div>

        {error && (
          <div className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {mode === "connect" ? (
          <form onSubmit={handleConnect} className="mt-6 space-y-4">
            <Field label="Project ID" value={projectId} onChange={setProjectId} />
            <Field label="API Key" value={apiKey} onChange={setApiKey} type="password" />
            <Field
              label="Admin Key (optional)"
              value={adminKey}
              onChange={setAdminKeyState}
              type="password"
            />
            <button
              type="submit"
              className="w-full rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700"
            >
              Sign In
            </button>
          </form>
        ) : (
          <form onSubmit={handleCreate} className="mt-6 space-y-4">
            <Field label="Admin Key" value={adminKey} onChange={setAdminKeyState} type="password" />
            <Field label="Project Name" value={projectName} onChange={setProjectName} />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-stone-900 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700 disabled:opacity-50"
            >
              {busy ? "Creating…" : "Create Project"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}

interface FieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}

function Field({ label, value, onChange, type = "text" }: FieldProps) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-stone-700">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 block w-full rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-stone-900 focus:outline-none focus:ring-1 focus:ring-stone-900"
      />
    </label>
  );
}
