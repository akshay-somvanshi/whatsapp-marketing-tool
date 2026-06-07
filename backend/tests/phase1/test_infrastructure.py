"""
Phase 1 — Infrastructure connectivity tests.

Requires docker compose services to be running:
    docker compose up -d

Run from repo root:
    cd backend && pytest tests/phase1/ -v

Environment overrides (optional):
    TEST_DB_DSN      default: postgresql://wa:wa@localhost:5432/wa_marketing
    TEST_REDIS_URL   default: redis://localhost:6379/0
    TEST_BACKEND_URL default: http://localhost:8000
"""

import os

import asyncpg
import httpx
import pytest
import redis.asyncio as aioredis

DB_DSN = os.getenv("TEST_DB_DSN", "postgresql://wa:wa@localhost:5432/wa_marketing")
REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("TEST_BACKEND_URL", "http://localhost:8000")

pytestmark = pytest.mark.asyncio


async def test_postgres_reachable():
    conn = await asyncpg.connect(DB_DSN)
    result = await conn.fetchval("SELECT 1")
    await conn.close()
    assert result == 1


async def test_postgres_test_db_exists():
    """Verify init_db.sh created wa_test during container first-start."""
    conn = await asyncpg.connect(DB_DSN)
    exists = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname = 'wa_test'"
    )
    await conn.close()
    assert exists == 1, "wa_test database not found — check init_db.sh ran correctly"


async def test_redis_reachable():
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    pong = await r.ping()
    await r.aclose()
    assert pong is True


async def test_health_endpoint():
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{BACKEND_URL}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
