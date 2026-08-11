"""Secret auto-redaction for input sanitization."""

import re
from typing import Any, cast

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "assignment",
        re.compile(
            r"(?i)(\b(?:authorization|credential|cookie|private[_-]?key|ssh[_-]?key|"
            r"access[_-]?key|api[_-]?key|access[_-]?token|auth[_-]?token|password|"
            r"passwd|pwd|secret)\b\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
    ),
    (
        "header",
        re.compile(
            r"(?i)(\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)"
            r"\s*:\s*)[^\r\n]+"
        ),
    ),
    ("auth", re.compile(r"(?i)(\b(?:Basic|Bearer)\s+)[A-Za-z0-9._~+/=-]+")),
    ("credential", re.compile(r"\b(?:ogm|rfr)_[A-Za-z0-9_-]+\b")),
    (
        "pem",
        re.compile(
            r"(?s)-----BEGIN [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----.*?"
            r"-----END [A-Z0-9 ]*(?:PRIVATE KEY|CERTIFICATE)-----"
        ),
    ),
    (
        "dsn",
        re.compile(
            r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp(?:s)?)://[^\s\"']+"
        ),
    ),
    ("url_userinfo", re.compile(r"(?i)\bhttps?://[^\s/@:]+:[^\s/@]+@[^\s\"']+")),
]

REDACTED = "[REDACTED]"

SENSITIVE_KEYS = {
    "authorization",
    "credential",
    "cookie",
    "password",
    "passwd",
    "secret",
    "privatekey",
    "sshkey",
    "accesskey",
    "accesstoken",
    "authtoken",
    "apikey",
    "token",
}


def _normalize_key(key: str) -> str:
    return key.lower().replace("_", "").replace("-", "").replace(" ", "")


def is_sensitive_key(key: str) -> bool:
    normalized = _normalize_key(key)
    return any(sensitive in normalized for sensitive in SENSITIVE_KEYS)


def redact_string(value: str) -> str:
    result = value
    for _, pattern in PATTERNS:
        if pattern.pattern.startswith("(?i)(\\b(?:Basic|Bearer)"):
            result = pattern.sub(r"\1" + REDACTED, result)
        elif pattern.pattern.startswith("(?i)(\\b(?:authorization"):
            result = pattern.sub(r"\1" + REDACTED, result)
        else:
            result = pattern.sub(REDACTED, result)
    return result


def redact_value(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            k: REDACTED if is_sensitive_key(k) else redact_value(v, k) for k, v in value.items()
        }
    elif isinstance(value, list):
        return [redact_value(item, parent_key) for item in value]
    elif isinstance(value, str):
        if parent_key == "pattern":
            return value
        return redact_string(value)
    return value


def contains_secret(value: Any, parent_key: str = "") -> bool:
    if isinstance(value, dict):
        for k, v in value.items():
            if is_sensitive_key(k):
                return True
            if contains_secret(v, k):
                return True
    elif isinstance(value, list):
        for item in value:
            if contains_secret(item, parent_key):
                return True
    elif isinstance(value, str):
        if parent_key == "pattern":
            return False
        for _, pattern in PATTERNS:
            if pattern.search(value):
                return True
    return False


def sanitize_input(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], redact_value(data))


def validate_no_secrets(data: dict[str, Any]) -> None:
    if contains_secret(data):
        raise ValueError("input contains secrets that must be redacted")
