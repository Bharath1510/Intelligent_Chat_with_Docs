import uuid
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging import correlation_id_ctx, logger


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Assigns a unique correlation ID to every request for structured log tracing."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        token = correlation_id_ctx.set(correlation_id)

        start_time = time.time()
        response: Response = await call_next(request)
        process_time = (time.time() - start_time) * 1000

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = f"{process_time:.2f}"

        logger.info(f"{request.method} {request.url.path} - Status: {response.status_code} - {process_time:.2f}ms")
        correlation_id_ctx.reset(token)
        return response
