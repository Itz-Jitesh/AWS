"""Redaction tests: credentials must never survive into evidence strings."""

from __future__ import annotations

from audit.redact import redact_text


def test_aws_access_key_id_redacted() -> None:
    out = redact_text("using key AKIAIOSFODNN7EXAMPLE today")
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "[REDACTED]" in out


def test_labeled_secret_value_redacted() -> None:
    out = redact_text('secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"')
    assert "wJalrXUtnFEMI" not in out
    assert "secret_access_key" in out
    assert "[REDACTED]" in out


def test_labeled_password_with_spaces_redacted() -> None:
    out = redact_text('password = "correct horse battery"')
    assert "correct horse battery" not in out
    assert "[REDACTED]" in out


def test_json_style_secret_redacted() -> None:
    out = redact_text('{"SecretAccessKey": "abc123", "Region": "us-east-1"}')
    assert "abc123" not in out
    assert "us-east-1" in out


def test_pem_private_key_block_redacted() -> None:
    text = "header\n-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\nfooter"
    out = redact_text(text)
    assert "MIIEpAIBAAKCAQEA" not in out
    assert "[REDACTED PRIVATE KEY]" in out


def test_bearer_token_redacted() -> None:
    out = redact_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.payload")
    assert "eyJhbGciOiJIUzI1NiJ9" not in out
    assert "Bearer [REDACTED]" in out


def test_plain_evidence_is_unchanged() -> None:
    text = "resource aws_s3_bucket.public_data has no public access block; file main.tf:12"
    assert redact_text(text) == text


def test_non_string_passthrough() -> None:
    assert redact_text(None) is None  # type: ignore[arg-type]
    assert redact_text("") == ""


def test_large_scanner_output_redacts_quickly() -> None:
    import time

    payload = ("x" * 1000 + "token = abc123\n") * 200
    start = time.monotonic()
    out = redact_text(payload)
    assert time.monotonic() - start < 2.0
    assert "abc123" not in out
    assert len(out) > 1000
