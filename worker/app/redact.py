from __future__ import annotations

import json
import re
from typing import Any

REDACTED = "***REDACTED***"

_FULL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASCA)[0-9A-Z]{16}\b"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----[\s\S]*?"
        r"-----END (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{8,}={0,2}"),
]

_VALUE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?i)([\"']?(?:secret[_-]?access[_-]?key|aws[_-]?secret[_-]?access[_-]?key|"
        r"aws[_-]?session[_-]?token|session[_-]?token|access[_-]?key[_-]?id|"
        r"password|passwd|pwd|api[_-]?key|apikey|auth[_-]?token|"
        r"private[_-]?key|client[_-]?secret)[\"']?\s*[:=]\s*[\"']?)([^\s\"',;}\]]{6,})"
    ),
    re.compile(r"(?i)([?&](?:password|passwd|token|api[_-]?key|secret)=)([^&\s\"']{6,})"),
]


_SENSITIVE_KEY = re.compile(
    r"(?i)secret|password|passwd|token|api[_-]?key|private[_-]?key|credential|access[_-]?key"
)


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    for pattern in _FULL_PATTERNS:
        out = pattern.sub(REDACTED, out)
    for pattern in _VALUE_PATTERNS:
        out = pattern.sub(lambda match: match.group(1) + REDACTED, out)
    return out


def redact_obj(value: Any, key: str | None = None) -> Any:
    if isinstance(value, str):
        if key is not None and _SENSITIVE_KEY.search(key):
            return REDACTED
        return redact_text(value)
    if isinstance(value, dict):
        return {item_key: redact_obj(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact_obj(item, key) for item in value]
    if key is not None and _SENSITIVE_KEY.search(key):
        return REDACTED
    return value



def redact_json_text(text: str) -> str:
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return redact_text(text)
    return json.dumps(redact_obj(parsed), indent=2, sort_keys=False)
