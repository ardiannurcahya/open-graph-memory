import { Link } from "react-router-dom";
import { useAuthStore } from "../store/auth";

export default function DashboardPage() {
  const projectId = useAuthStore((s) => s.projectId);
  return (
    <div className="px-8 py-6">
      <h2 className="text-xl font-semibold text-stone-900">Dashboard</h2>
      <p className="mt-2 text-sm text-stone-600">
        Connected to project <code className="rounded bg-stone-100 px-1">{projectId}</code>.
      </p>
      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card title="Datasets" to="/datasets" desc="Manage datasets and documents" />
        <Card title="Graph Playground" to="/graph" desc="Search entities and inspect graph structure" />
      </div>
    </div>
  );
}

function Card({ title, desc, to }: { title: string; desc: string; to: string }) {
  return (
    <Link
      to={to}
      className="block rounded-lg border border-stone-200 bg-white p-4 transition hover:border-stone-400 hover:shadow-sm"
    >
      <h3 className="font-semibold text-stone-900">{title}</h3>
      <p className="mt-1 text-sm text-stone-500">{desc}</p>
    </Link>
  );
}
