import httpx
import json
import sys
from pathlib import Path
from uuid import uuid4

BASE_URL = "http://localhost:8000"
ADMIN_KEY = "ogm-admin-secret-key-local"

client = httpx.Client(base_url=BASE_URL, timeout=60.0)

project_name = f"Codebase Graph Test-{uuid4().hex[:6]}"

print(f"1. Creating Project '{project_name}'...")
resp = client.post(
    "/v1/projects",
    headers={"X-Api-Key": ADMIN_KEY},
    json={"name": project_name}
)
if resp.status_code != 201:
    print(f"Project creation failed: {resp.status_code} {resp.text}")
    sys.exit(1)

project_data = resp.json()
project_id = project_data["id"]
api_key = project_data["api_key"]
print(f"Project ID: {project_id}")
print(f"API Key: {api_key}")

headers = {
    "X-Project-Id": project_id,
    "X-Api-Key": api_key,
    "Content-Type": "application/json"
}

print("\n2. Creating Dataset...")
resp = client.post(
    "/v1/datasets",
    headers=headers,
    json={"name": "OGM Core Codebase", "description": "Codebase AST Knowledge Graph"}
)
if resp.status_code != 201:
    print(f"Dataset creation failed: {resp.status_code} {resp.text}")
    sys.exit(1)

dataset_data = resp.json()
dataset_id = dataset_data["id"]
print(f"Dataset ID: {dataset_id}")

print("\n3. Scanning Python files for codebase indexing...")
code_dir = Path("packages/core/src/open_graph_core")
files_to_ingest = []

for py_file in code_dir.glob("*.py"):
    code_text = py_file.read_text(encoding="utf-8")
    if not code_text.strip():
        continue
    rel_path = str(py_file.as_posix())
    files_to_ingest.append({
        "file_path": rel_path,
        "code": code_text,
        "language": "python"
    })

api_dir = Path("apps/api/app")
for py_file in api_dir.glob("*.py"):
    code_text = py_file.read_text(encoding="utf-8")
    if not code_text.strip():
        continue
    rel_path = str(py_file.as_posix())
    files_to_ingest.append({
        "file_path": rel_path,
        "code": code_text,
        "language": "python"
    })

print(f"Total non-empty files to ingest: {len(files_to_ingest)}")

print("\n4. Ingesting codebase files into Knowledge Graph (POST /v1/codebase/ingest)...")
ingest_payload = {
    "dataset_id": dataset_id,
    "files": files_to_ingest
}

resp = client.post("/v1/codebase/ingest", headers=headers, json=ingest_payload)
print(f"Ingestion status: {resp.status_code}")
ingest_result = resp.json()
print("\n=== INGESTION SUCCESS ===")
print(json.dumps(ingest_result, indent=2))

# Save credentials and updating global mcp_config.json
config_output = {
    "project_id": project_id,
    "api_key": api_key,
    "dataset_id": dataset_id
}
Path("scratch/local_credentials.json").write_text(json.dumps(config_output, indent=2))
print("\nSaved credentials to scratch/local_credentials.json")
