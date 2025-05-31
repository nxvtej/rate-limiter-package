from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.types import ASGIApp
import redis.asyncio as redis
import time
import logging

# logging configuration and indian time format and must print the filename and line number
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

logger.info("processing fastapi_redis_rate_limiter middleware")

class RedisRateLimitMiddleware(BaseHTTPMiddleware):
    """
    A FastAPI middleware for distributed rate limiting using Redis.
    """
    def __init__(
        self,
        app: ASGIApp,
        redis_client: redis.Redis,
        rate_limit: int = 5,
        time_window: int = 60,
        exceeded_response: dict = None,
        ip_extractor: callable = None,
    ):
        super().__init__(app)
        self.redis_client = redis_client
        self.rate_limit = rate_limit
        self.time_window = time_window
        self.exceeded_response = exceeded_response or {"detail": "Rate limit exceeded"}
        self.ip_extractor = ip_extractor if ip_extractor else self._default_ip_extractor
        logger.info(
            f"RedisRateLimitMiddleware initialized: "
            f"Limit={self.rate_limit} requests per {self.time_window} seconds."
        )

    async def _default_ip_extractor(self, request: Request) -> str:
        """
        Default method to extract client IP from request.
        Considers X-Forwarded-For if present, otherwise uses request.client.host.
        """
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def is_rate_limited(self, client_identifier: str) -> bool:
        """
        Checks if the client is rate-limited using a fixed-window counter in Redis.
        """
        key = f"rate_limit:{client_identifier}"

        try:
            pipe = self.redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, self.time_window)

            count, _ = await pipe.execute()

            if count > self.rate_limit:
                return True
            return False
        except Exception as e:
            logger.error(f"Error interacting with Redis for rate limiting (key: {key}): {e}")
            raise Exception("Rate limiting service unavailable.")


    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        The main middleware dispatch method.
        """
        if request.url.path == "/health": # Optionally bypass rate limiting for health checks
            return await call_next(request)

        client_identifier = await self.ip_extractor(request)

        try:
            if await self.is_rate_limited(client_identifier):
                retry_after = await self.redis_client.ttl(f"rate_limit:{client_identifier}")
                if retry_after == -1: # No TTL set (shouldn't happen with expire)
                    retry_after = self.time_window # Fallback

                response = JSONResponse(
                    status_code=429,
                    content=self.exceeded_response
                )
                response.headers["Retry-After"] = str(retry_after)
                logger.warning(f"Rate limit exceeded for {client_identifier}. Retrying after {retry_after}s.")
                return response
        except Exception as e:
            # Catch any exception from is_rate_limited (e.g., Redis down)
            logger.error(f"Rate limiting middleware error: {e}")
            return JSONResponse(
                status_code=503,
                content={"detail": "Rate limiting service error or unavailable."}
            )

        response = await call_next(request)
        return response