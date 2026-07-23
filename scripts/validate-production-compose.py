import json
import subprocess
import sys

command = [
    "docker",
    "compose",
    "-f",
    "deployments/docker-compose.yml",
    "-f",
    "deployments/docker-compose.prod.yml",
    "config",
    "--format",
    "json",
]
result = subprocess.run(command, check=True, capture_output=True, text=True)
services = json.loads(result.stdout)["services"]
application_services = {"api", "worker", "migrate", "web"}
errors: list[str] = []
for name in sorted(application_services):
    service = services[name]
    if service.get("build"):
        errors.append(f"{name}: production service must not contain build configuration")
    if not service.get("image"):
        errors.append(f"{name}: production service must use a published image")
if errors:
    print("\n".join(errors), file=sys.stderr)
    raise SystemExit(1)
print("production compose: application images set; host builds disabled")
