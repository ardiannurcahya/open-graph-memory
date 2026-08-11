import httpx
import json
import sys
import time
from pathlib import Path
from uuid import uuid4

BASE_URL = "http://localhost:8000"
ADMIN_KEY = "ogm-admin-secret-key-local"

client = httpx.Client(base_url=BASE_URL, timeout=120.0)

print("=" * 60)
print("  OPENGRAPH-MEMORY CODEBASE INDEXING BENCHMARK")
print("=" * 60)

project_name = f"Benchmark Project-{uuid4().hex[:6]}"

print(f"\n1. Creating fresh project '{project_name}'...")
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

headers = {
    "X-Project-Id": project_id,
    "X-Api-Key": api_key,
    "Content-Type": "application/json"
}

resp = client.post(
    "/v1/datasets",
    headers=headers,
    json={"name": "OGM Benchmark Codebase", "description": "Benchmark AST Knowledge Graph"}
)
if resp.status_code != 201:
    print(f"Dataset creation failed: {resp.status_code} {resp.text}")
    sys.exit(1)

dataset_data = resp.json()
dataset_id = dataset_data["id"]
print(f"   [+] Project ID: {project_id}")
print(f"   [+] Dataset ID: {dataset_id}")

print("\n2. Scanning Python source files...")
scan_start = time.perf_counter()
files_to_ingest = []

for py_file in Path("packages/core/src/open_graph_core").glob("*.py"):
    code_text = py_file.read_text(encoding="utf-8")
    if not code_text.strip():
        continue
    files_to_ingest.append({
        "file_path": str(py_file.as_posix()),
        "code": code_text,
        "language": "python"
    })

for py_file in Path("apps/api/app").glob("*.py"):
    code_text = py_file.read_text(encoding="utf-8")
    if not code_text.strip():
        continue
    files_to_ingest.append({
        "file_path": str(py_file.as_posix()),
        "code": code_text,
        "language": "python"
    })

scan_duration = time.perf_counter() - scan_start
total_bytes = sum(len(f["code"].encode("utf-8")) for f in files_to_ingest)
total_lines = sum(len(f["code"].splitlines()) for f in files_to_ingest)

print(f"   [+] Scanned {len(files_to_ingest)} files ({total_lines:,} lines, {total_bytes/1024:.1f} KB) in {scan_duration*1000:.2f} ms")

print("\n3. Ingesting & Extracting AST Knowledge Graph (POST /v1/codebase/ingest)...")
ingest_payload = {
    "dataset_id": dataset_id,
    "files": files_to_ingest
}

ingest_start = time.perf_counter()
resp = client.post("/v1/codebase/ingest", headers=headers, json=ingest_payload, timeout=120.0)
ingest_duration = time.perf_counter() - ingest_start

if resp.status_code != 200:
    print(f"Ingestion failed ({resp.status_code}): {resp.text}")
    sys.exit(1)

ingest_result = resp.json()
files_proc = ingest_result["files_processed"]
entities_count = ingest_result["entities_inserted"]
relations_count = ingest_result["relations_inserted"]

print(f"   [+] Ingestion completed in {ingest_duration:.3f} seconds ({ingest_duration*1000:.1f} ms)!")

print("\n4. Calculating Hierarchical Louvain GraphRAG Analytics...")
analytics_start = time.perf_counter()
resp_analytics = client.post(f"/v1/datasets/{dataset_id}/analytics/refresh", headers=headers, timeout=120.0)
analytics_duration = time.perf_counter() - analytics_start

total_duration = scan_duration + ingest_duration + analytics_duration

print("\n" + "=" * 60)
print("           BENCHMARK PERFORMANCE RESULTS")
print("=" * 60)
print(f"  * Total Files Processed  : {files_proc} files")
print(f"  * Total Lines of Code   : {total_lines:,} LOC ({total_bytes/1024:.1f} KB)")
print(f"  * Code Entities Extracted: {entities_count:,} entities")
print(f"  * Code Relations Parsed : {relations_count:,} relations")
print("-" * 60)
print(f"  * AST Ingestion Time    : {ingest_duration:.3f} sec ({ingest_duration*1000:.1f} ms)")
print(f"  * GraphRAG Analytics   : {analytics_duration:.3f} sec")
print(f"  * TOTAL END-TO-END TIME : {total_duration:.3f} sec")
print("-" * 60)
print(f"  * Throughput Speed      : {files_proc / ingest_duration:.1f} files/sec")
print(f"  * Ingestion Throughput : {(entities_count + relations_count) / ingest_duration:.1f} graph-elements/sec")
print("=" * 60)

# Save credentials to local_credentials.json
config_output = {
    "project_id": project_id,
    "api_key": api_key,
    "dataset_id": dataset_id
}
Path("scratch/local_credentials.json").write_text(json.dumps(config_output, indent=2))

# Update global mcp_config.json
mcp_config_path = Path(r"C:\Users\ardia\.gemini\config\mcp_config.json")
if mcp_config_path.exists():
    try:
        mcp_data = json.loads(mcp_config_path.read_text("utf-8"))
        mcp_data["mcpServers"]["ogm"]["env"]["OGM_API_KEY"] = api_key
        mcp_data["mcpServers"]["ogm"]["env"]["OGM_PROJECT_ID"] = project_id
        mcp_config_path.write_text(json.dumps(mcp_data, indent=2), "utf-8")
        print("\n[+] Updated global mcp_config.json with new benchmark credentials!")
    except Exception as e:
        print(f"\nFailed to update mcp_config.json: {e}")
