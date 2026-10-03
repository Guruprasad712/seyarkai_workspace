import pytest


@pytest.mark.asyncio
async def test_health_returns_200(async_client):
    r = await async_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
