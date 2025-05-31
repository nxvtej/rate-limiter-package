from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import redis.asyncio as redis
from dotenv import load_dotenv
import os
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.from_url(REDIS_URL)

from fastapi_redis_rate_limiter.middleware import RedisRateLimitMiddleware


app = FastAPI(
    title="Example App with Rate Limiter",
    description="A simple FastAPI app demonstrating the rate limiting middleware."
)

app.add_middleware(
    RedisRateLimitMiddleware,
    redis_client=redis_client,
    rate_limit=int(os.getenv("RATE_LIMIT", "5")),       # 5 requests
    time_window=int(os.getenv("TIME_WINDOW", "60")),    # per 60 seconds
    exceeded_response={"message": "You are making too many requests. Please try again later."}
)

# --- Example Routes ---
@app.get("/")
async def read_root():
    return {"message": "Welcome to the rate-limited API!"}

@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id, "data": f"Some data for item {item_id}"}

@app.get("/users/{user_id}")
async def read_user(user_id: int):
    return {"user_id": user_id, "name": f"User {user_id}"}

@app.get("/status")
async def get_status():
    """A simple endpoint that is protected by the rate limiter."""
    return {"status": "Service is operational."}

# Health check (excluded from rate limiting in middleware)
@app.get("/health")
async def health_check_app():
    """Health check for the example application itself."""
    try:
        await redis_client.ping()
        redis_status = "Connected"
    except Exception:
        redis_status = "Disconnected"

    return JSONResponse(content={"status": "OK", "redis_status": redis_status})