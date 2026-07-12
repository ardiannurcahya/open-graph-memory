# Dataset and document upload

Milestone 1 adds project-isolated dataset CRUD and streamed uploads to S3-compatible storage.

## API

All requests require `X-Project-ID` with the UUID of an existing project.

- `POST /v1/datasets`, `GET /v1/datasets`
- `GET`, `PATCH`, or `DELETE /v1/datasets/{dataset_id}`
- `POST /v1/datasets/{dataset_id}/documents` using multipart field `file`
- `GET /v1/datasets/{dataset_id}/documents`
- `GET /v1/datasets/{dataset_id}/documents/{document_id}`

Uploads accept PDF, Markdown, HTML, and plain text up to 25 MiB. The service streams into a bounded spool, verifies extension, declared MIME and basic content signature, computes SHA-256, then uploads to a stable object key. Re-uploading identical content to the same dataset returns the existing document with `duplicate: true`; content may be uploaded independently to another dataset.

Object keys never contain the supplied filename. If object storage succeeds but metadata persistence loses an idempotency race, the losing object is removed. Operators can reconcile an unexpected database outage by listing objects under `projects/{project_id}/datasets/{dataset_id}/documents/` and comparing their document IDs with PostgreSQL.

## Example

```bash
curl -H "X-Project-ID: $PROJECT_ID" -H 'Content-Type: application/json' \
  -d '{"name":"Company Docs"}' http://localhost:3000/api/v1/datasets

curl -H "X-Project-ID: $PROJECT_ID" \
  -F 'file=@policy.pdf;type=application/pdf' \
  http://localhost:3000/api/v1/datasets/$DATASET_ID/documents
```

Run the real PostgreSQL/RustFS integration gate with `./scripts/m1-runtime-gate.sh`. It creates and removes its Compose volumes and must not be run against persistent production data.
