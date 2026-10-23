from __future__ import annotations


def test_health_returns_ok(env):
    client = env.client()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "worker"


def test_capabilities_without_tools(env):
    client = env.client()
    response = client.get("/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["apply_enabled"] is False
    assert body["tools"]["terraform"]["available"] is False
    assert body["tools"]["terraform"]["version"] is None
    assert "not found" in body["tools"]["terraform"]["detail"]
    assert body["tools"]["git"]["available"] is False
    for capability in body["checks"].values():
        assert capability["available"] is False
        assert capability["argv_preview"][0] == "terraform"
    assert body["sandbox"]["containerized"] is False
    assert body["sandbox"]["limitations"]


def test_capabilities_with_tools(env):
    env.install_terraform()
    env.install_git()
    client = env.client()
    response = client.get("/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["tools"]["terraform"]["available"] is True
    assert body["tools"]["terraform"]["version"] == "Terraform 1.9.5 (fake)"
    assert body["tools"]["git"]["available"] is True
    assert "git version" in body["tools"]["git"]["version"]
    for capability in body["checks"].values():
        assert capability["available"] is True
    assert body["limits"]["check_timeout_s"] == 30
    assert body["apply_enabled"] is False
