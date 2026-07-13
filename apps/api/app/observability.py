import time
from collections import Counter, defaultdict
from threading import Lock

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

_started_at = time.time()
_lock = Lock()
_requests: Counter[tuple[str, str, int]] = Counter()
_latency_seconds: defaultdict[tuple[str, str], float] = defaultdict(float)


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        elapsed = time.perf_counter() - started
        with _lock:
            _requests[(request.method, path, response.status_code)] += 1
            _latency_seconds[(request.method, path)] += elapsed
        return response


def render_metrics() -> str:
    lines = [
        "# HELP opengraphrag_process_uptime_seconds API process uptime.",
        "# TYPE opengraphrag_process_uptime_seconds gauge",
        f"opengraphrag_process_uptime_seconds {time.time() - _started_at:.3f}",
        "# HELP opengraphrag_http_requests_total HTTP requests by method, route, and status.",
        "# TYPE opengraphrag_http_requests_total counter",
    ]
    with _lock:
        for (method, path, status), value in sorted(_requests.items()):
            labels = f'method="{method}",path="{path}",status="{status}"'
            lines.append(f"opengraphrag_http_requests_total{{{labels}}} {value}")
        lines.extend(
            [
                "# HELP opengraphrag_http_request_duration_seconds_sum HTTP request latency sum.",
                "# TYPE opengraphrag_http_request_duration_seconds_sum counter",
            ]
        )
        for (method, path), latency in sorted(_latency_seconds.items()):
            labels = f'method="{method}",path="{path}"'
            lines.append(
                f"opengraphrag_http_request_duration_seconds_sum{{{labels}}} {latency:.6f}"
            )
    return "\n".join(lines) + "\n"
