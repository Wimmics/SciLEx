"""WebSocket connection manager."""
import json
from typing import Dict, Set
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""

    def __init__(self):
        # job_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, job_id: str):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        if job_id not in self.active_connections:
            self.active_connections[job_id] = set()

        self.active_connections[job_id].add(websocket)
        print(f"WebSocket connected for job {job_id}")

    def disconnect(self, websocket: WebSocket, job_id: str):
        """Remove a WebSocket connection."""
        if job_id in self.active_connections:
            self.active_connections[job_id].discard(websocket)

            # Clean up empty sets
            if not self.active_connections[job_id]:
                del self.active_connections[job_id]

        print(f"WebSocket disconnected for job {job_id}")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send a message to a specific WebSocket."""
        await websocket.send_text(json.dumps(message))

    async def broadcast_to_job(self, job_id: str, event_type: str, data: dict):
        """Broadcast a message to all connections for a specific job."""
        if job_id not in self.active_connections:
            return

        message = {
            "job_id": job_id,
            "type": event_type,
            "data": data,
            "timestamp": data.get("timestamp", "")
        }

        # Send to all connections for this job
        disconnected = set()
        for connection in self.active_connections[job_id]:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                print(f"Error sending to WebSocket: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection, job_id)


# Global instance
manager = ConnectionManager()
