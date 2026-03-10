"""SSE endpoint for real-time question events."""

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, Query
from starlette.requests import Request
from starlette.responses import StreamingResponse

from app.services.auth import verify_jwt_token
from app.services.event_bus import subscribe

router = APIRouter(tags=["events"])


@router.get("/questions/{question_id}/events")
async def question_events(
    question_id: uuid.UUID,
    request: Request,
    token: str = Query(..., description="JWT token (EventSource cannot send headers)"),
):
    """Stream answer status changes for a question via SSE."""
    # Validate JWT from query param (EventSource API cannot set headers)
    try:
        verify_jwt_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    channel = str(question_id)

    async def event_stream():
        async with subscribe(channel) as queue:
            # Send initial keepalive so the client knows the connection is live
            yield ": connected\n\n"
            while True:
                try:
                    # Check for client disconnect between events
                    if await request.is_disconnected():
                        break
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    event_type = event.get("type", "message")
                    data = json.dumps(event)
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive comment to prevent proxy/browser timeout
                    yield ": keepalive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
