import { statusColor } from "../lib/documentStatus";

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusColor(status)}`}
    >
      {status}
    </span>
  );
}
