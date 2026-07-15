# Dataset and document upload

Milestone 1 adds project-isolated dataset CRUD and streamed uploads to S3-compatible storage.

## API

All requests require `X-Project-ID` with the UUID of an existing project.

- `POST /v1/datasets`, `GET /v1/datasets`
- `GET`, `PATCH`, or `DELETE /v1/datasets/{dataset_id}`
- `POST /v1/datasets/{dataset_id}/documents` using multipart field `file`
- `GET /v1/datasets/{dataset_id}/documents`
- `GET /v1/datasets/{dataset_id}/documents/{document_id}`

Uploads accept `.txt`, `.md`, `.html`, `.json`, `.pdf`, and `.csv` files up to configured `UPLOAD_MAX_BYTES` limit (50,000,000 bytes by default). JSON uploads accept `application/json`, `text/json`, or browser fallback `text/plain` and must contain valid UTF-8 JSON. Top-level arrays become source-aware records with `record_number` and `json_path`; top-level objects and scalars remain one source document. Duplicate detection hashes raw uploaded bytes, so whitespace or key-order changes produce different content hashes. Web UI file picker lists `.json` alongside other supported formats. Service streams into bounded spool, verifies extension, declared MIME, and full content structure, computes SHA-256, then uploads to stable object key. Re-uploading identical content to same dataset returns existing document with `duplicate: true`; content may be uploaded independently to another dataset.

Object keys never contain the supplied filename. If object storage succeeds but metadata persistence loses an idempotency race, the losing object is removed. Operators can reconcile an unexpected database outage by listing objects under `projects/{project_id}/datasets/{dataset_id}/documents/` and comparing their document IDs with PostgreSQL.

## Example

```bash
curl -H "X-Project-ID: $PROJECT_ID" -H 'Content-Type: application/json' \
  -d '{"name":"Company Docs"}' http://localhost:3000/api/v1/datasets

curl -H "X-Project-ID: $PROJECT_ID" \
  -F 'file=@policy.pdf;type=application/pdf' \
  http://localhost:3000/api/v1/datasets/$DATASET_ID/documents

curl -H "X-Project-ID: $PROJECT_ID" \
  -F 'file=@config.json;type=application/json' \
  http://localhost:3000/api/v1/datasets/$DATASET_ID/documents
```

Run the real PostgreSQL/RustFS integration gate with `./scripts/m1-runtime-gate.sh`. It creates and removes its Compose volumes and must not be run against persistent production data.
