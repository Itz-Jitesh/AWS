import re

_AWS_ACCESS_KEY = re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")
_AWS_SECRET_ASSIGN = re.compile(
    r"(?i)\b((?:aws_)?secret_access_key|aws_secret_key)\b(\s*[:=]\s*)(\S+)"
)
_GENERIC_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|token|api_key|apikey|access_key|credential|authorization)\b"
    r"(\s*[:=]\s*)(\S+)"
)
_PRIVATE_KEY_BLOCK = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)
_BEARER = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._\-]+")

REDACTED = "***REDACTED***"


def redact(text: str | None) -> str:
    if not text:
        return ""
    out = _PRIVATE_KEY_BLOCK.sub(REDACTED, text)
    out = _AWS_ACCESS_KEY.sub(REDACTED, out)
    out = _AWS_SECRET_ASSIGN.sub(lambda m: m.group(1) + m.group(2) + REDACTED, out)
    out = _BEARER.sub(lambda m: m.group(1) + " " + REDACTED, out)
    out = _GENERIC_ASSIGN.sub(lambda m: m.group(1) + m.group(2) + REDACTED, out)
    return out
