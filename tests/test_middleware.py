import pytest
from starlette.testclient import TestClient
from fastapi import FastAPI, Request, Response
from unittest.mock import AsyncMock # Used for mocking async methods
import redis.asyncio as redis # Assuming your middleware imports redis.asyncio
import asyncio 
# --- IMPORTANT: Replace this with your actual RateLimitMiddleware import ---
# For demonstration, I'm including a simplified RateLimitMiddleware class here.
# You should import your actual middleware.
# Example: from fastapi_redis_rate_limiter.middleware import RateLimitMiddleware
class RateLimitMiddleware:
    def __init__(self, app, rate_limit: int, window_size: int, redis_url: str = "redis://localhost:6379"):
        self.app = app
        self.rate_limit = rate_limit
        self.window_size = window_size
        # This is the line we will patch:
        self.redis_client = redis.Redis.from_url(redis_url)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            request = Request(scope, receive)
            path = request.url.path

            # Example: Bypass rate limiting for /health
            if path == "/health":
                await self.app(scope, receive, send)
                return

            # Assuming client IP or a fixed key for testing
            key = f"rate_limit:{request.client.host if request.client else 'testclient'}:{path}"

            # Simplified rate limiting logic (adapt to your actual middleware's logic)
            current_count = await self.redis_client.incr(key)
            if current_count == 1:
                await self.redis_client.expire(key, self.window_size)

            if current_count > self.rate_limit:
                response = Response("Too Many Requests", status_code=429)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

# --- Fixtures for Mocking ---

# This fixture provides a mocked Redis client instance
@pytest.fixture
def mock_redis_instance(mocker):
    # Create an AsyncMock for the redis.asyncio.Redis object
    mock_redis = mocker.AsyncMock(spec=redis.Redis)
    # Configure common return values for methods your middleware might call
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None # Default: key not found
    mock_redis.set.return_value = True
    mock_redis.expire.return_value = True
    # For incr, we'll use side_effect in individual tests to control counts
    return mock_redis

# This fixture sets up the FastAPI application with your middleware
# and ensures that the middleware uses the mocked Redis client.
@pytest.fixture
def app_with_mock_middleware(mock_redis_instance, monkeypatch):
    # `monkeypatch` is a pytest fixture that allows you to temporarily modify
    # classes, functions, or attributes during tests.
    # Here, we patch the `from_url` method of `redis.asyncio.Redis`.
    # This means that whenever `redis.asyncio.Redis.from_url(...)` is called
    # (e.g., inside your RateLimitMiddleware's __init__), it will return
    # our `mock_redis_instance` instead of creating a real Redis client.

    # IMPORTANT: The path to patch ('redis.asyncio.Redis.from_url') must be exact.
    # If your middleware imports Redis differently (e.g., `from some_module import my_redis_client_instance`),
    # then the patch path would change. If it's a global import in your middleware file,
    # it would be `your_middleware_module_name.redis.asyncio.Redis.from_url`.
    # For typical usage, `redis.asyncio.Redis` should work if it's imported directly.
    monkeypatch.setattr(redis.Redis, 'from_url', lambda *args, **kwargs: mock_redis_instance)

    _app = FastAPI()
    # Add your middleware to this app instance
    _app.add_middleware(RateLimitMiddleware, rate_limit=5, window_size=60)

    # Define a simple endpoint to test
    @_app.get("/")
    async def _read_root():
        return {"message": "Hello World"}

    # Define a health check endpoint that bypasses rate limiting
    @_app.get("/health")
    async def _health_check():
        return {"status": "ok"}

    return _app

# This fixture provides the TestClient for making requests against your mocked app
@pytest.fixture
def client(app_with_mock_middleware):
    with TestClient(app_with_mock_middleware) as c:
        yield c

# --- Tests ---

@pytest.mark.asyncio
async def test_within_rate_limit(client, mock_redis_instance):
    # Simulate the 'incr' method returning 1, 2, 3, 4, 5
    mock_redis_instance.incr.side_effect = [asyncio.sleep(0, result=i) for i in range(1, 7)] # <--- CHANGED HERE

    for i in range(5):
        response = client.get("/")
        assert response.status_code == 200

    # Verify that 'incr' was called 5 times
    assert mock_redis_instance.incr.call_count == 5
    # Verify that 'expire' was called once for the first increment
    mock_redis_instance.expire.assert_called_once_with(
        "rate_limit:testclient:/", 60 # Adjust key if your middleware uses a different one
    )

@pytest.mark.asyncio
async def test_exceeds_rate_limit(client, mock_redis_instance):
    # Simulate 'incr' returning 1, 2, 3, 4, 5, then 6 (exceeding the 5-limit)
    mock_redis_instance.incr.side_effect = [asyncio.sleep(0, result=i) for i in range(1, 7)] # <--- CHANGED HERE

    for i in range(5): # First 5 requests should be allowed
        response = client.get("/")
        assert response.status_code == 200

    # The 6th request should be rate-limited
    response = client.get("/")
    assert response.status_code == 429 # Expected "Too Many Requests"

    assert mock_redis_instance.incr.call_count == 6

@pytest.mark.asyncio
async def test_rate_limit_resets_after_window(client, mock_redis_instance):
    # Simulate the first window: 5 requests, all allowed
    mock_redis_instance.incr.side_effect = list(range(1, 6))
    for _ in range(5):
        response = client.get("/")
        assert response.status_code == 200

    # After these requests, reset the mock to simulate a new window where counter starts from 1 again
    # This effectively simulates time passing and the key expiring/resetting
    mock_redis_instance.incr.reset_mock() # Clear call history
    mock_redis_instance.expire.reset_mock() # Clear call history

    # Simulate the second window: 5 requests, all allowed
    mock_redis_instance.incr.side_effect = list(range(1, 6))
    for _ in range(5):
        response = client.get("/")
        assert response.status_code == 200

    # Verify incr was called 5 times in this "second window"
    assert mock_redis_instance.incr.call_count == 5
    # Verify expire was called once again for the first request in the "second window"
    mock_redis_instance.expire.assert_called_once_with(
        "rate_limit:testclient:/", 60 # Adjust key if your middleware uses a different one
    )

@pytest.mark.asyncio
async def test_health_check_bypassed(client, mock_redis_instance):
    response = client.get("/health")
    assert response.status_code == 200
    # Assert that no Redis operations were performed for the health check path
    # (This is assuming your middleware logic bypasses Redis for /health)
    mock_redis_instance.incr.assert_not_called()
    mock_redis_instance.expire.assert_not_called()