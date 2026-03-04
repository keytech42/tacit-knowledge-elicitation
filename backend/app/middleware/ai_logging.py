import json
import time
import uuid
from collections.abc import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.database import async_session
from app.models.ai_log import AIInteractionLog
from app.models.user import User, UserType
from app.services.auth import validate_api_key, verify_jwt_token


class AILoggingMiddleware(BaseHTTPMiddleware):
    """Automatically log all write requests from service accounts."""

    WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Only intercept write methods
        if request.method not in self.WRITE_METHODS:
            return await call_next(request)

        # Try to identify service account
        service_user = await self._get_service_user(request)
        if not service_user:
            return await call_next(request)

        # Read request body
        body_bytes = await request.body()
        try:
            request_body = json.loads(body_bytes) if body_bytes else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            request_body = None

        start_time = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start_time) * 1000)

        # Log asynchronously
        endpoint = f"{request.method} {request.url.path}"
        try:
            async with async_session() as session:
                log_entry = AIInteractionLog(
                    service_user_id=service_user.id,
                    model_id=service_user.model_id,
                    endpoint=endpoint,
                    request_body=request_body,
                    response_status=response.status_code,
                    latency_ms=latency_ms,
                )
                session.add(log_entry)
                await session.commit()
        except Exception:
            pass  # Don't fail the request if logging fails

        return response

    async def _get_service_user(self, request: Request) -> User | None:
        """Try to identify if the request is from a service account."""
        # Check API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            async with async_session() as session:
                user = await validate_api_key(session, api_key)
                if user and (user.user_type == UserType.SERVICE.value or user.user_type == UserType.SERVICE):
                    return user
            return None

        # Check JWT
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = verify_jwt_token(token)
                if payload.get("user_type") == "service":
                    from sqlalchemy import select
                    async with async_session() as session:
                        result = await session.execute(
                            select(User).where(User.id == uuid.UUID(payload["sub"]))
                        )
                        return result.scalar_one_or_none()
            except Exception:
                pass

        return None
