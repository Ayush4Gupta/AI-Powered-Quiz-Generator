from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, status
import time, redis, structlog
from app.core.settings import get_settings
from app.core.errors import QuizError

settings = get_settings()
rds = redis.from_url(settings.celery_broker_url)
log = structlog.get_logger()

class RateLimitMiddleware(BaseHTTPMiddleware):
    WINDOW = 60         # seconds
    MAX_REQ = 30        # per window

    async def dispatch(self, request: Request, call_next):
        key = f"ratelimit:{request.client.host}"
        txn = rds.pipeline()
        txn.incr(key, 1)
        txn.expire(key, self.WINDOW)
        current = txn.execute()[0]

        if current > self.MAX_REQ:
            log.warning("ratelimit.exceeded", ip=request.client.host)
            raise QuizError("Rate limit exceeded, try later", status.HTTP_429_TOO_MANY_REQUESTS)

        return await call_next(request)
