from __future__ import annotations

from conftest import VALID_MAIN_TF, b64, build_zip_bytes


def _zip_payload(entries: list[tuple[str, bytes]], filename: str = "repo.zip") -> dict:
    return {
        "source_type": "zip",
        "filename": filename,
        "zip_base64": b64(build_zip_bytes(entries)),
    }


def test_ingest_valid_zip_detects_tf_files_and_providers(env):
    client = env.client()
    payload = _zip_payload([("main.tf", VALID_MAIN_TF.encode()), ("outputs.tf", b"output \"id\" {\n  value = 1\n}\n")])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert len(body["task_id"]) == 32
    paths = [item["path"] for item in body["tf_files"]]
    assert paths == ["main.tf", "outputs.tf"]
    assert body["tf_files"][0]["size_bytes"] > 0
    provider = next(p for p in body["providers"] if p["name"] == "aws")
    assert provider["source"] == "hashicorp/aws"
    assert provider["version"] == "~> 5.0"
    assert body["required_version"] == ">= 1.5.0"
    assert body["source_type"] == "zip"
    assert (env.data_dir / body["task_id"] / "repo" / "main.tf").is_file()


def test_ingest_upload_endpoint_accepts_multipart(env):
    client = env.client()
    zip_bytes = build_zip_bytes([("main.tf", VALID_MAIN_TF.encode())])
    response = client.post(
        "/ingest/upload",
        files={"file": ("repo.zip", zip_bytes, "application/zip")},
    )
    assert response.status_code == 200
    assert response.json()["task_id"]


def test_ingest_missing_source_type_rejected(env):
    client = env.client()
    response = client.post("/ingest", json={"git_url": "https://example.com/x.git"})
    assert response.status_code == 422


def test_ingest_unknown_source_type_rejected(env):
    client = env.client()
    response = client.post("/ingest", json={"source_type": "http", "url": "http://x"})
    assert response.status_code == 422


def test_ingest_invalid_base64_rejected(env):
    client = env.client()
    response = client.post(
        "/ingest",
        json={"source_type": "zip", "zip_base64": "not-valid-base64!!!"},
    )
    assert response.status_code == 422


def test_ingest_non_zip_payload_rejected(env):
    client = env.client()
    response = client.post(
        "/ingest",
        json={"source_type": "zip", "zip_base64": b64(b"this is not a zip archive")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_ZIP"
    assert env.task_dirs() == []


def test_ingest_rejects_parent_traversal_entry(env):
    client = env.client()
    payload = _zip_payload(
        [
            ("main.tf", VALID_MAIN_TF.encode()),
            ("../evil.tf", b"resource \"evil\" {}"),
        ]
    )
    response = client.post("/ingest", json=payload)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "UNSAFE_ARCHIVE"
    assert ".." in detail["message"]
    assert env.task_dirs() == []
    assert not list(env.tmp_path.glob("**/evil.tf"))


def test_ingest_rejects_nested_traversal_entry(env):
    client = env.client()
    payload = _zip_payload([("nested/../../evil.tf", b"evil")])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSAFE_ARCHIVE"
    assert env.task_dirs() == []


def test_ingest_rejects_absolute_path_entry(env):
    client = env.client()
    absolute_target = env.tmp_path / "abs-evil.tf"
    payload = _zip_payload([(str(absolute_target), b"evil")])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSAFE_ARCHIVE"
    assert not absolute_target.exists()
    assert env.task_dirs() == []


def test_ingest_rejects_backslash_entry(env):
    client = env.client()
    payload = _zip_payload([("..\\evil.tf", b"evil")])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSAFE_ARCHIVE"


def test_ingest_rejects_symlink_entry(env):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("main.tf", VALID_MAIN_TF)
        info = zipfile.ZipInfo("link.tf")
        info.external_attr = 0o120777 << 16
        archive.writestr(info, "/etc/passwd")
    client = env.client()
    response = client.post(
        "/ingest",
        json={"source_type": "zip", "zip_base64": b64(buffer.getvalue())},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "UNSAFE_ARCHIVE"
    assert "symlink" in detail["message"]
    assert env.task_dirs() == []


def test_ingest_rejects_uncompressed_size_over_limit(env):
    client = env.client(max_uncompressed_bytes=1024)
    payload = _zip_payload([("big.tf", b"0" * 4096)])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "UNSAFE_ARCHIVE"
    assert "uncompressed size" in detail["message"]
    assert env.task_dirs() == []


def test_ingest_rejects_too_many_entries(env):
    client = env.client(max_zip_entries=2)
    payload = _zip_payload(
        [("a.tf", b"a"), ("b.tf", b"b"), ("c.tf", b"c")]
    )
    response = client.post("/ingest", json=payload)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSAFE_ARCHIVE"


def test_ingest_rejects_zip_bomb_ratio(env):
    client = env.client(max_compression_ratio=2)
    payload = _zip_payload([("zeros.tf", b"0" * 200000)])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "UNSAFE_ARCHIVE"
    assert "ratio" in detail["message"]


def test_ingest_payload_too_large(env):
    client = env.client(max_zip_bytes=64)
    payload = _zip_payload([("main.tf", VALID_MAIN_TF.encode())])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"


def test_ingest_repo_without_tf_files_returns_warning(env):
    client = env.client()
    payload = _zip_payload([("README.md", b"# hello")])
    response = client.post("/ingest", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["tf_files"] == []
    assert any("no Terraform" in warning for warning in body["warnings"])
