from __future__ import annotations

import json


def test_ingest_git_success(env):
    env.install_git()
    client = env.client()
    response = client.post(
        "/ingest",
        json={"source_type": "git_url", "git_url": "https://example.com/demo.git"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_type"] == "git_url"
    assert [item["path"] for item in body["tf_files"]] == ["main.tf"]
    provider = next(p for p in body["providers"] if p["name"] == "aws")
    assert provider["version"] == "~> 5.0"
    calls_file = env.data_dir / body["task_id"] / "git.calls.json"
    args = json.loads(calls_file.read_text())
    assert args[0] == "clone"
    assert "--" in args
    assert args.index("--") == len(args) - 3
    assert args[-2] == "https://example.com/demo.git"


def test_ingest_git_rejects_non_https_schemes(env):
    env.install_git()
    client = env.client()
    bad_urls = [
        "file:///etc/passwd",
        "ext::sh -c id",
        "git://example.com/demo.git",
        "ssh://git@example.com/demo.git",
        "ftp://example.com/demo.git",
        "http://example.com/demo.git",
        "-uhttps://example.com",
        "https://example.com/demo file.git",
    ]
    for url in bad_urls:
        response = client.post("/ingest", json={"source_type": "git_url", "git_url": url})
        assert response.status_code == 400, url
        assert response.json()["detail"]["code"] == "UNSAFE_GIT_URL", url
    assert env.task_dirs() == []


def test_ingest_git_missing_binary_returns_unavailable(env):
    client = env.client()
    response = client.post(
        "/ingest",
        json={"source_type": "git_url", "git_url": "https://example.com/demo.git"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "GIT_UNAVAILABLE"
    assert env.task_dirs() == []


def test_ingest_git_disabled_returns_unavailable(env):
    env.install_git()
    client = env.client(git_enabled=False)
    response = client.post(
        "/ingest",
        json={"source_type": "git_url", "git_url": "https://example.com/demo.git"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "GIT_UNAVAILABLE"
    assert env.task_dirs() == []


def test_ingest_git_clone_failure_returns_502_and_cleans_task(env):
    env.install_git()
    client = env.client()
    response = client.post(
        "/ingest",
        json={"source_type": "git_url", "git_url": "https://example.com/fail-clone.git"},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "CLONE_FAILED"
    assert "repository not found" in detail["message"]
    assert env.task_dirs() == []
