import { AlertCircle, FileText, Loader2, Trash2, Upload } from "lucide-react";
import { useRef } from "react";

import type { DocumentItem } from "../lib/types";

interface DocumentManagerProps {
  documents: DocumentItem[];
  loading: boolean;
  uploading: boolean;
  onUpload: (files: File[]) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onRefresh: () => void;
}

const ACCEPTED = ".txt,.md,.html,.pdf,.csv";

const STATUS_LABELS: Record<string, string> = {
  pending_upload: "Pending",
  uploaded: "Uploaded",
  storage_failed: "Storage Failed",
  queued: "Queued",
  parsing: "Parsing",
  chunking: "Chunking",
  embedding: "Embedding",
  persisting: "Persisting",
  indexed: "Indexed",
  failed: "Failed",
  cancelled: "Cancelled",
  stale: "Stale",
  deleting: "Deleting",
  delete_failed: "Delete Failed",
};

function statusVariant(status: string): string {
  if (status === "indexed") return "ok";
  if (status === "failed" || status === "storage_failed" || status === "delete_failed")
    return "error";
  if (status === "uploaded" || status === "queued") return "info";
  return "active";
}

function isProcessing(status: string): boolean {
  return ["parsing", "chunking", "embedding", "persisting", "deleting"].includes(status);
}

function formatBytes(value: number): string {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const idx = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** idx).toFixed(idx ? 1 : 0)} ${units[idx]}`;
}

function fileExtension(filename: string): string {
  const parts = filename.split(".");
  return parts.length > 1 ? parts.pop()!.toUpperCase() : "FILE";
}

export function DocumentManager({
  documents,
  loading,
  uploading,
  onUpload,
  onDelete,
  onRefresh,
}: DocumentManagerProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    try {
      if (files.length > 0) await onUpload(files);
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <section className="panel" id="documents" aria-labelledby="documents-heading">
      <div className="panel-header">
        <div>
          <span className="panel-eyebrow">Source Library</span>
          <h2 id="documents-heading" className="panel-title">
            Documents
          </h2>
        </div>
        <div className="panel-actions">
          <button
            className="btn btn-ghost"
            onClick={onRefresh}
            disabled={loading}
            title="Refresh document list"
          >
            {loading ? <Loader2 size={14} strokeWidth={2} className="spin" /> : "Refresh"}
          </button>
          <label className="btn btn-primary upload-label">
            {uploading ? (
              <>
                <Loader2 size={15} strokeWidth={2} className="spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload size={15} strokeWidth={2} />
                Upload
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              aria-label="Upload files"
              accept={ACCEPTED}
              multiple
              onChange={handleFileChange}
              disabled={uploading}
              hidden
            />
          </label>
        </div>
      </div>

      <div className="document-list">
        {documents.length === 0 && !loading ? (
          <div className="empty-state">
            <FileText size={28} strokeWidth={1.5} />
            <p>No documents yet. Upload a .txt, .md, .html, .pdf, or .csv file to begin indexing.</p>
          </div>
        ) : (
          documents.map((doc) => (
            <article key={doc.id} className="document-row">
              <span className="document-ext">{fileExtension(doc.filename)}</span>
              <div className="document-info">
                <strong className="document-name">{doc.filename}</strong>
                <span className="document-meta">
                  {formatBytes(doc.size_bytes)}
                  {doc.duplicate && " · duplicate"}
                </span>
              </div>
              <span className={`status-badge status-${statusVariant(doc.status)}`}>
                {isProcessing(doc.status) && <Loader2 size={10} strokeWidth={2} className="spin" />}
                {doc.status === "failed" && <AlertCircle size={10} strokeWidth={2} />}
                {STATUS_LABELS[doc.status] ?? doc.status}
              </span>
              <button
                className="btn btn-icon btn-danger"
                onClick={() => onDelete(doc.id)}
                aria-label={`Delete ${doc.filename}`}
                title="Delete document"
              >
                <Trash2 size={14} strokeWidth={2} />
              </button>
            </article>
          ))
        )}
      </div>
    </section>
  );
}
