from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from api.rate_limit import RateLimitMiddleware, TokenBucket


def test_token_bucket_allows_up_to_capacity_then_blocks():
    bucket = TokenBucket(capacity=3, refill_per_second=0)  # no refill -- deterministic
    assert bucket.try_consume() is True
    assert bucket.try_consume() is True
    assert bucket.try_consume() is True
    assert bucket.try_consume() is False


def _build_test_app(requests_per_minute: int = 2) -> Starlette:
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/ping", ok)])
    app.add_middleware(RateLimitMiddleware, requests_per_minute=requests_per_minute)
    return app


def test_rate_limit_middleware_returns_429_after_limit_exceeded():
    with TestClient(_build_test_app(requests_per_minute=2)) as client:
        r1 = client.get("/ping", headers={"X-API-Key": "some-key"})
        r2 = client.get("/ping", headers={"X-API-Key": "some-key"})
        r3 = client.get("/ping", headers={"X-API-Key": "some-key"})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers


def test_rate_limit_buckets_are_isolated_per_key():
    with TestClient(_build_test_app(requests_per_minute=1)) as client:
        r_key_a_1 = client.get("/ping", headers={"X-API-Key": "key-a"})
        r_key_a_2 = client.get("/ping", headers={"X-API-Key": "key-a"})
        r_key_b_1 = client.get("/ping", headers={"X-API-Key": "key-b"})

        assert r_key_a_1.status_code == 200
        assert r_key_a_2.status_code == 429  # key-a exhausted its own bucket
        assert r_key_b_1.status_code == 200  # key-b has its own, untouched bucket


def test_rate_limit_disabled_never_blocks():
    async def ok(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/ping", ok)])
    app.add_middleware(RateLimitMiddleware, requests_per_minute=1, enabled=False)

    with TestClient(app) as client:
        for _ in range(5):
            assert client.get("/ping", headers={"X-API-Key": "k"}).status_code == 200
