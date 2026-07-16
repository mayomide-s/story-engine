from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGED_COMPOSE = REPO_ROOT / "docker-compose.managed.prod.yml"
LOCAL_COMPOSE = REPO_ROOT / "docker-compose.yml"
PRODUCTION_ENV = REPO_ROOT / ".env.production.example"
NGINX_TEMPLATE = REPO_ROOT / "deploy" / "nginx" / "managed-prod.conf.template"
CLIENT_FILE = REPO_ROOT / "frontend" / "src" / "api" / "client.ts"


def _service_names(compose_text: str) -> list[str]:
    lines = compose_text.splitlines()
    service_names: list[str] = []
    in_services = False
    for line in lines:
        if line.startswith("services:"):
            in_services = True
            continue
        if in_services and line and not line.startswith(" "):
            break
        if in_services and line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":"):
            service_names.append(line.strip().rstrip(":"))
    return service_names


def test_managed_production_compose_excludes_local_data_services():
    compose_text = MANAGED_COMPOSE.read_text(encoding="utf-8")
    services = _service_names(compose_text)

    assert "reverse_proxy" in services
    assert "frontend" in services
    assert "backend" in services
    assert "celery_worker" in services
    assert "migrate" in services
    assert "revision" in services
    assert "config_check" in services
    assert "postgres" not in services
    assert "redis" not in services
    assert "valkey" not in services
    assert "celery_beat" not in services


def test_managed_production_compose_only_publishes_ports_from_reverse_proxy():
    compose_text = MANAGED_COMPOSE.read_text(encoding="utf-8")

    assert 'reverse_proxy:' in compose_text
    assert '- "80:80"' in compose_text
    assert '- "443:443"' in compose_text
    assert 'frontend:\n' in compose_text
    assert 'backend:\n' in compose_text
    assert 'expose:\n      - "80"' in compose_text
    assert 'expose:\n      - "8000"' in compose_text
    assert 'ports:\n      - "127.0.0.1:8001:8000"' not in compose_text
    assert 'ports:\n      - "127.0.0.1:5174:80"' not in compose_text


def test_managed_production_compose_uses_explicit_migration_and_api_commands():
    compose_text = MANAGED_COMPOSE.read_text(encoding="utf-8")

    assert 'command: ["sh", "/app/start-api.sh"]' in compose_text
    assert 'command: ["sh", "/app/migrate.sh"]' in compose_text
    assert 'RUN_MIGRATIONS_ON_STARTUP: ${RUN_MIGRATIONS_ON_STARTUP:-false}' in compose_text
    assert 'DATABASE_URL: ${DATABASE_URL:?set DATABASE_URL in .env.production}' in compose_text
    assert 'REDIS_URL: ${REDIS_URL:?set REDIS_URL in .env.production}' in compose_text


def test_production_env_template_contains_managed_service_placeholders_and_domains():
    env_text = PRODUCTION_ENV.read_text(encoding="utf-8")

    assert "DATABASE_URL=postgresql+psycopg://" in env_text
    assert "REDIS_URL=rediss://" in env_text
    assert "R2_BUCKET_NAME=story-engine-prod-assets" in env_text
    assert "R2_PUBLIC_BASE_URL=https://assets.storyengine.soremekun.org" in env_text
    assert "VITE_API_BASE_URL=https://api.storyengine.soremekun.org/api" in env_text
    assert "CORS_ALLOWED_ORIGINS=https://storyengine.soremekun.org" in env_text
    assert "ALLOWED_HOSTS=storyengine.soremekun.org,api.storyengine.soremekun.org" in env_text
    assert "SESSION_COOKIE_SECURE=true" in env_text
    assert "RUN_MIGRATIONS_ON_STARTUP=false" in env_text
    assert "GOOGLE_OAUTH_REDIRECT_URI=https://api.storyengine.soremekun.org/api/social-connections/youtube/callback" in env_text
    assert "POSTGRES_PASSWORD=" not in env_text
    assert "postgres@postgres:5432" not in env_text
    assert "redis://redis:6379/0" not in env_text


def test_reverse_proxy_template_routes_frontend_and_api_hosts_with_spa_support_upstream():
    template_text = NGINX_TEMPLATE.read_text(encoding="utf-8")

    assert "server_name ${FRONTEND_HOST};" in template_text
    assert "server_name ${API_HOST};" in template_text
    assert "location / {" in template_text
    assert "proxy_pass http://${FRONTEND_UPSTREAM};" in template_text
    assert "location /api/" in template_text
    assert "proxy_pass http://${BACKEND_UPSTREAM};" in template_text
    assert "location = /health" in template_text
    assert "location = /health/details" in template_text
    assert "return 301 https://$host$request_uri;" in template_text
    assert "X-Request-ID" in template_text


def test_local_compose_still_defines_local_postgres_and_redis_for_development():
    compose_text = LOCAL_COMPOSE.read_text(encoding="utf-8")
    services = _service_names(compose_text)

    assert "postgres" in services
    assert "redis" in services


def test_frontend_api_base_remains_full_api_prefix():
    client_text = CLIENT_FILE.read_text(encoding="utf-8")
    env_text = PRODUCTION_ENV.read_text(encoding="utf-8")

    assert 'const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";' in client_text
    assert "VITE_API_BASE_URL=https://api.storyengine.soremekun.org/api" in env_text
