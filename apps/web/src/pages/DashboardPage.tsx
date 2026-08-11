import { Link } from "react-router-dom";
import { 
  Database, 
  Network, 
  Brain, 
  ArrowRight, 
  Cpu, 
  Server, 
  Activity, 
  FileCode2, 
  GitFork
} from "lucide-react";
import { useAuthStore } from "../store/auth";

export default function DashboardPage() {
  const projectId = useAuthStore((s) => s.projectId);

  return (
    <div className="px-6 py-8 sm:px-10 max-w-6xl mx-auto space-y-8">
      {/* macOS Clean Header */}
      <div className="border-b border-mac pb-6 space-y-2">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-muted text-main px-3 py-1 text-xs font-semibold border border-mac">
          <span>AST Codebase Knowledge Graph</span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-main">
          Dashboard
        </h1>
        <p className="text-sm text-subdued">
          Connected to project <code className="font-mono rounded bg-muted px-1.5 py-0.5 text-xs text-mac-accent font-bold">{projectId || "Local Engine"}</code>.
        </p>
      </div>

      {/* macOS Engine Metrics */}
      <div>
        <h2 className="text-xs font-bold uppercase tracking-wider text-subdued mb-3 flex items-center gap-2">
          <Activity className="h-4 w-4 text-mac-accent" /> Engine Metrics
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            title="Indexed Code Entities"
            value="2,408"
            subtitle="AST Symbols, Classes & Functions"
            icon={FileCode2}
          />
          <MetricCard
            title="Knowledge Graph Relations"
            value="3,521"
            subtitle="Calls, Inherits, Imports, Contains"
            icon={GitFork}
          />
          <MetricCard
            title="Hierarchical Louvain Graph"
            value="3 Levels"
            subtitle="46 Code Communities"
            icon={Network}
          />
          <MetricCard
            title="Database Engine"
            value="Active"
            subtitle="PostgreSQL 16 + Redis 7.4"
            icon={Server}
          />
        </div>
      </div>

      {/* macOS Workspaces */}
      <div>
        <h2 className="text-xs font-bold uppercase tracking-wider text-subdued mb-3 flex items-center gap-2">
          <Cpu className="h-4 w-4 text-mac-accent" /> Workspaces
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <FeatureCard
            title="Graph Playground"
            desc="Search symbols, inspect call paths, subgraphs, and relation evidence in 2D/3D graph."
            to="/graph"
            icon={Network}
            badge="Explorer"
          />
          <FeatureCard
            title="Datasets & Ingestion"
            desc="Manage datasets, code files, and documents. Trigger AST indexing and refresh analytics."
            to="/datasets"
            icon={Database}
            badge="Datasets"
          />
          <FeatureCard
            title="Agent Memory"
            desc="Persistent operational memory for AI agents. Track fix patterns and outcome feedback."
            to="/memory"
            icon={Brain}
            badge="Memory"
          />
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
  icon: Icon,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ElementType;
}) {
  return (
    <div className="rounded-xl border border-mac bg-surface p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-subdued">{title}</span>
        <Icon className="h-4 w-4 text-mac-accent" />
      </div>
      <div className="mt-2">
        <p className="text-xl font-bold text-main">{value}</p>
        <p className="mt-0.5 text-xs text-subdued">{subtitle}</p>
      </div>
    </div>
  );
}

function FeatureCard({
  title,
  desc,
  to,
  icon: Icon,
  badge,
}: {
  title: string;
  desc: string;
  to: string;
  icon: React.ElementType;
  badge: string;
}) {
  return (
    <Link
      to={to}
      className="group flex flex-col justify-between rounded-xl border border-mac bg-surface p-5 hover:border-mac-accent transition-all duration-150 shadow-sm hover:shadow-md"
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted text-mac-accent">
            <Icon className="h-4 w-4" />
          </div>
          <span className="rounded-full bg-muted border border-mac px-2.5 py-0.5 text-[10px] font-bold text-subdued">
            {badge}
          </span>
        </div>
        <div>
          <h3 className="text-base font-bold text-main group-hover:text-mac-accent transition-colors">
            {title}
          </h3>
          <p className="mt-1 text-xs text-subdued leading-normal">{desc}</p>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-1 text-xs font-bold text-mac-accent">
        <span>Open</span>
        <ArrowRight className="h-3 w-3" />
      </div>
    </Link>
  );
}
