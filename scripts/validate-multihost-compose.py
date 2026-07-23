from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "deployments" / "multihost"
FILES = (
    "postgres.yml",
    "redis.yml",
    "dispatcher.yml",
    "neo4j.yml",
    "app.yml",
    "worker.yml",
    "graph-worker.yml",
    "edge.yml",
)


def render(name: str) -> dict[str, Any]:
    env = os.environ | {
        "GHCR_NAMESPACE": "example",
        "IMAGE_TAG": "sha-0123456",
        "POSTGRES_DB": "db",
        "POSTGRES_USER": "user",
        "POSTGRES_PASSWORD": "test-password",
        "POSTGRES_BIND_IP": "10.77.0.3",
        "REDIS_PASSWORD": "test-password",
        "REDIS_BIND_IP": "10.77.0.7",
        "NEO4J_AUTH": "neo4j/test-password",
        "NEO4J_BIND_IP": "10.77.0.5",
        "WORKER_NODE": "test-worker",
        "WEB_BIND_IP": "10.77.0.9",
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(DEPLOYMENT / name),
            "config",
            "--format",
            "json",
        ],
        cwd=DEPLOYMENT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return cast(dict[str, Any], json.loads(result.stdout))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    rendered = {name: render(name) for name in FILES}
    for name, config in rendered.items():
        for service_name, service in config["services"].items():
            for port in service.get("ports", []):
                published = int(port["published"])
                require(
                    name == "edge.yml" or published not in {22, 80, 443},
                    f"{name}:{service_name} must not publish protected port {published}",
                )

    app_ports = rendered["app.yml"]["services"]["web"]["ports"]
    require(app_ports[0]["published"] == "3000", "web must publish port 3000")
    require(app_ports[0]["host_ip"] == "10.77.0.9", "web must bind to WireGuard")
    require(
        rendered["postgres.yml"]["services"]["postgres"]["ports"][0]["host_ip"]
        == "10.77.0.3",
        "PostgreSQL must bind to WireGuard",
    )
    require(
        rendered["redis.yml"]["services"]["redis"]["ports"][0]["host_ip"]
        == "10.77.0.7",
        "Redis must bind to WireGuard",
    )
    neo4j_ports = rendered["neo4j.yml"]["services"]["neo4j"]["ports"]
    require(
        all(port["host_ip"] == "10.77.0.5" for port in neo4j_ports),
        "Neo4j must bind to WireGuard",
    )
    edge_ports = rendered["edge.yml"]["services"]["edge"]["ports"]
    require(
        {(int(port["published"]), port["protocol"]) for port in edge_ports}
        == {(80, "tcp"), (443, "tcp"), (443, "udp")},
        "edge must publish only TCP 80/443 and UDP 443",
    )
    require(
        all(
            "build" not in service
            for config in rendered.values()
            for service in config["services"].values()
        ),
        "production services must use prebuilt images",
    )
    print("multi-host compose validation passed")


if __name__ == "__main__":
    main()
