from __future__ import annotations

from app.redact import REDACTED, redact_obj, redact_text


def test_redacts_aws_access_key_ids():
    text = "key=AKIAIOSFODNN7EXAMPLE and ASIAABCDEFGHJKLMNPQR"
    out = redact_text(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "ASIAABCDEFGHJKLMNPQR" not in out
    assert REDACTED in out


def test_redacts_named_secret_fields_in_json_text():
    text = '{"secret_access_key": "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY", "region": "us-east-1"}'
    out = redact_text(text)
    assert "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY" not in out
    assert '"region": "us-east-1"' in out


def test_redacts_password_assignment():
    out = redact_text("password=sup3rS3cretValue and user hunter2")
    assert "sup3rS3cretValue" not in out
    assert "password=***REDACTED***" in out
    assert "hunter2" in out


def test_redacts_pem_private_key_blocks():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----"
    out = redact_text(text)
    assert "MIIEpAIBAAKCAQEA" not in out
    assert REDACTED in out


def test_redacts_bearer_tokens():
    out = redact_text("Authorization: Bearer abcdef1234567890")
    assert "abcdef1234567890" not in out


def test_leaves_ordinary_text_alone():
    text = "aws_s3_bucket.demo acl public-read region us-east-1"
    assert redact_text(text) == text


def test_redact_obj_redacts_sensitive_keys_recursively():
    obj = {
        "planned_values": {
            "credentials": {"token": "abcdef123456", "note": "keep"},
            "acl": "public-read",
        },
        "password": "hunter22",
        "count": 3,
    }
    out = redact_obj(obj)
    assert out["planned_values"]["acl"] == "public-read"
    assert out["planned_values"]["credentials"]["note"] == "keep"
    assert out["password"] == REDACTED
    assert out["count"] == 3
    assert out["planned_values"]["credentials"]["token"] == REDACTED


def test_redact_obj_does_not_mutate_input():
    obj = {"password": "hunter22"}
    redact_obj(obj)
    assert obj["password"] == "hunter22"
