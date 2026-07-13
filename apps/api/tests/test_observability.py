from app.observability import render_metrics


def test_metrics_expose_uptime_and_request_counters() -> None:
    payload = render_metrics()
    assert "opengraphrag_process_uptime_seconds" in payload
    assert "opengraphrag_http_requests_total" in payload
    assert "opengraphrag_http_request_duration_seconds_sum" in payload
