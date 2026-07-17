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
      return "bg-ui-success-bg text-ui-success";
    case "failed":
    case "storage_failed":
    case "delete_failed":
      return "bg-ui-danger-bg text-ui-danger";
    case "queued":
    case "parsing":
    case "chunking":
    case "persisting":
    case "uploaded":
    case "pending_upload":
      return "bg-ui-warning-bg text-ui-warning";
    case "deleting":
      return "bg-ui-raised text-ui-subdued";
    case "cancelled":
    case "stale":
      return "bg-ui-muted text-ui-subdued";
    default:
      return "bg-ui-muted text-ui-subdued";
  }
}
