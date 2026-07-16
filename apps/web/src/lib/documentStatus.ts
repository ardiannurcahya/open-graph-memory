import type { DocumentStatus } from "../api/types";

const TERMINAL_STATUSES: DocumentStatus[] = [
  "indexed",
  "failed",
  "cancelled",
  "stale",
  "delete_failed",
  "storage_failed",
];

export const isTerminal = (status: DocumentStatus): boolean =>
  TERMINAL_STATUSES.includes(status);

export const hasActiveDocuments = (statuses: DocumentStatus[]): boolean =>
  statuses.some((s) => !isTerminal(s));

export const ACCEPTED_EXTENSIONS = [".txt", ".md", ".html", ".json", ".pdf", ".csv"];

export function statusColor(status: string): string {
  switch (status) {
    case "indexed":
      return "bg-green-100 text-green-800";
    case "failed":
    case "storage_failed":
    case "delete_failed":
      return "bg-red-100 text-red-800";
    case "queued":
    case "parsing":
    case "chunking":
    case "persisting":
    case "uploaded":
    case "pending_upload":
      return "bg-amber-100 text-amber-800";
    case "deleting":
      return "bg-stone-200 text-stone-700";
    case "cancelled":
    case "stale":
      return "bg-stone-100 text-stone-500";
    default:
      return "bg-stone-100 text-stone-700";
  }
}
