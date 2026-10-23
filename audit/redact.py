"""Redaction of secret-like values from text destined for evidence, logs, or reports.

Redaction is intentionally aggressive: a label such as ``max_tokens`` may be
over-redacted. Over-redaction is preferred over leaking a credential into an
evidence string that ends up in a downloadable report.

The labeled-secret pass is a linear keyword scan rather than one big regular
expression; a backtracking regex over multi-hundred-kilobyte scanner output
is quadratically slow and effectively hangs.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_PEM_BLOCK = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_AWS_KEY_ID = re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA|AROA|AIDA)[0-9A-Z]{16}\b")
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+={0,2}")
_KEYWORD = re.compile(
    r"(?i)(?:password|passwd|secret|credential|token|apikey|api_key|access_key|private_key)"
)
_LABEL_CHAR = re.compile(r"[A-Za-z0-9_.\-]")
_SEPARATOR = re.compile(r"\s*[=:]\s*")
_BARE_VALUE = re.compile(r"[^\s,;}\]]+")


def _redact_labeled(text: str) -> str:
    matches = list(_KEYWORD.finditer(text))
    if not matches:
        return text
    pieces: list[str] = []
    cursor = 0
    consumed_to = 0
    for match in matches:
        if match.start() < consumed_to:
            continue
        start = match.start()
        while start > 0 and _LABEL_CHAR.fullmatch(text[start - 1]):
            start -= 1
        end = match.end()
        while end < len(text) and _LABEL_CHAR.fullmatch(text[end]):
            end += 1
        if end < len(text) and text[end] in "\"'":
            end += 1
        separator = _SEPARATOR.match(text, end)
        if separator is None:
            continue
        value_start = separator.end()
        if value_start >= len(text):
            continue
        if text[value_start] in "\"'":
            quote = text[value_start]
            value_end = text.find(quote, value_start + 1)
            if value_end == -1:
                continue
            value_end += 1
        else:
            bare = _BARE_VALUE.match(text, value_start)
            if bare is None:
                continue
            value_end = bare.end()
        if start < cursor:
            continue
        pieces.append(text[cursor:start])
        pieces.append(text[start:value_start])
        pieces.append(REDACTED)
        cursor = value_end
        consumed_to = value_end
    pieces.append(text[cursor:])
    return "".join(pieces)


def redact_text(text: str) -> str:
    """Return ``text`` with secret-looking values replaced by placeholders."""
    if not isinstance(text, str) or not text:
        return text
    out = _PEM_BLOCK.sub("[REDACTED PRIVATE KEY]", text)
    out = _redact_labeled(out)
    out = _AWS_KEY_ID.sub(REDACTED, out)
    out = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", out)
    return out
