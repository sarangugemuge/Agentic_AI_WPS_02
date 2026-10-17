"""
Events API Route — Server-Sent Events (SSE) streaming endpoint for live frontend updates.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.services.event_broadcaster import EventBroadcaster, get_broadcaster

router = APIRouter()


@router.get(
    "/events",
    summary="Real-Time Event Stream (SSE)",
    description=(
        "Streams Server-Sent Events to the client for real-time synchronization, "
        "push reassessments, and score recalculations without page reload."
    ),
    response_class=StreamingResponse,
)
async def event_stream(
    broadcaster: EventBroadcaster = Depends(get_broadcaster),
):
    """
    HTTP GET endpoint for Server-Sent Events.
    Keeps a persistent HTTP connection open, streaming JSON messages when events occur.
    """
    return StreamingResponse(
        broadcaster.subscribe(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
