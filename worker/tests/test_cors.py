from __future__ import annotations

from conftest import VALID_MAIN_TF, b64, build_zip_bytes

FRONTEND = "http://localhost:3000"
EVIL = "http://evil.example"


def _preflight(client, path: str, origin: str, method: str = "POST", headers: str = "content-type"):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


def test_preflight_on_existing_route_succeeds(env):
    client = env.client()
    response = _preflight(client, "/ingest", FRONTEND)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND
    allow_methods = response.headers["access-control-allow-methods"]
    for method in ("GET", "POST", "OPTIONS"):
        assert method in allow_methods
    allow_headers = response.headers["access-control-allow-headers"].lower()
    assert "content-type" in allow_headers
    assert "authorization" in allow_headers


def test_preflight_on_missing_route_does_not_404_or_405(env):
    client = env.client()
    response = _preflight(client, "/tasks", FRONTEND)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert "access-control-allow-methods" in response.headers


def test_preflight_with_authorization_header_allowed(env):
    client = env.client()
    response = _preflight(client, "/tasks", FRONTEND, headers="content-type,authorization")
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_actual_get_carries_cors_headers(env):
    client = env.client()
    response = client.get("/health", headers={"Origin": FRONTEND})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_error_response_carries_cors_headers(env):
    client = env.client()
    response = client.post("/check", json={"task_id": "a" * 32, "checks": ["fmt"]}, headers={"Origin": FRONTEND})
    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == FRONTEND

    response = client.post("/ingest", json={"source_type": "zip", "zip_base64": "@@@"}, headers={"Origin": FRONTEND})
    assert response.status_code == 422
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_5xx_response_carries_cors_headers(env):
    env.install_git()
    client = env.client()
    response = client.post(
        "/ingest",
        json={"source_type": "git_url", "git_url": "https://example.com/fail-clone.git"},
        headers={"Origin": FRONTEND},
    )
    assert response.status_code == 502
    assert response.headers["access-control-allow-origin"] == FRONTEND


def test_unapproved_origin_gets_no_cors_headers(env):
    client = env.client()
    response = client.get("/health", headers={"Origin": EVIL})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

    preflight = _preflight(client, "/ingest", EVIL)
    assert preflight.status_code >= 400
    assert "access-control-allow-origin" not in preflight.headers


def test_no_origin_request_untouched(env):
    client = env.client()
    response = client.get("/health")
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_no_wildcard_origin_and_no_credentials(env):
    client = env.client()
    response = client.get("/health", headers={"Origin": FRONTEND})
    assert response.headers["access-control-allow-origin"] == FRONTEND
    assert response.headers["access-control-allow-origin"] != "*"
    assert "access-control-allow-credentials" not in response.headers


def test_origins_configurable_by_environment(env):
    custom = "http://frontend.internal:4000"
    client = env.client(cors_allow_origins=(custom,))
    allowed = client.get("/health", headers={"Origin": custom})
    assert allowed.headers["access-control-allow-origin"] == custom
    denied = client.get("/health", headers={"Origin": FRONTEND})
    assert "access-control-allow-origin" not in denied.headers


def test_default_origins_from_settings():
    from app.config import Settings

    settings = Settings(data_dir=__import__("pathlib").Path("/tmp/x"))
    assert "http://localhost:3000" in settings.cors_allow_origins
    assert "http://127.0.0.1:3000" in settings.cors_allow_origins
    assert "*" not in settings.cors_allow_origins


def test_wildcard_env_value_is_dropped():
    from app.config import _env_origins

    import os

    os.environ["WORKER_CORS_TEST"] = "*, http://localhost:3000"
    try:
        origins = _env_origins("WORKER_CORS_TEST", ("http://default",))
    finally:
        del os.environ["WORKER_CORS_TEST"]
    assert origins == ("http://localhost:3000",)
