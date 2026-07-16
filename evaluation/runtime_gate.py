"""Shared HTTP and Compose helpers for evaluation runtime gates."""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

__all__ = ["auth", "compose", "multipart", "request", "sql", "wait_ready"]


def request(
    base: str,
    method: str,
    path: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[int, Any]:
    payload = (
        data if data is not None else (json.dumps(body).encode() if body is not None else None)
    )
    req = urllib.request.Request(
        base + path,
        data=payload,
        method=method,
        headers={"Content-Type": content_type, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, json.loads(raw) if raw else None


def wait_ready(base: str, timeout: float = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if request(base, "GET", "/ready")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(2)
    raise RuntimeError("API did not become ready")


def multipart(filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "m2-runtime-gate-boundary"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{filename}"\r\nContent-Type: text/plain\r\n\r\n'
        ).encode()
        + content
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def compose(compose_file: Path, *args: str) -> str:
    command = ["docker", "compose", "--env-file", ".env", "-f", str(compose_file), *args]
    return subprocess.run(command, check=True, text=True, capture_output=True).stdout.strip()


def sql(compose_file: Path, statement: str) -> str:
    return compose(
        compose_file,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        os.getenv("POSTGRES_USER", "opengraphrag"),
        "-d",
        os.getenv("POSTGRES_DB", "opengraphrag"),
        "-Atqc",
        statement,
    )


def auth(project: dict[str, Any]) -> dict[str, str]:
    return {"X-API-Key": project["api_key"], "X-Project-ID": project["id"]}
