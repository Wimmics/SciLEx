"""WebSocket endpoint handlers."""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .manager import manager

router = APIRouter()


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job updates."""
    await manager.connect(websocket, job_id)

    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()

            # Echo back for now (could handle control commands later)
            await manager.send_personal_message(
                {"type": "ack", "message": f"Received: {data}"},
                websocket
            )

    except WebSocketDisconnect:
        manager.disconnect(websocket, job_id)
