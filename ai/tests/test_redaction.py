from planproof_ai.redaction import REDACTED, redact


def test_aws_access_key_redacted():
    out = redact("using key AKIA1234567890ABCDEF here")
    assert "AKIA1234567890ABCDEF" not in out
    assert REDACTED in out


def test_password_assignment_redacted():
    out = redact("password=hunter2")
    assert "hunter2" not in out
    assert "password=" in out


def test_aws_secret_assignment_redacted():
    out = redact('aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG"')
    assert "wJalrXUtnFEMI" not in out


def test_private_key_block_redacted():
    text = "-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----"
    out = redact(text)
    assert "abc" not in out
    assert REDACTED in out


def test_bearer_token_redacted():
    out = redact("Authorization: Bearer abc.def.ghi")
    assert "abc.def.ghi" not in out


def test_plain_text_unchanged():
    assert redact("resource \"aws_s3_bucket\" \"b\" {}") == 'resource "aws_s3_bucket" "b" {}'
    assert redact(None) == ""
