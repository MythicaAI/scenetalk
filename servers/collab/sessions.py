# Session data models
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Awaitable, Callable, Coroutine, Dict, Optional, Set
from uuid import uuid4
from pycrdt import Doc

from pydantic import BaseModel


log = logging.getLogger(__name__)


def timestamp() -> datetime:
    return datetime.now(timezone.utc)

class Client:
    def __init__(self, id, send_to_client):
        self.id = id
        self.send = send_to_client
        self.last_active: datetime = timestamp()

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.id == other.id

class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    last_active: datetime
    data: Dict[str, Any] = {}

class Session:
    def __init__(self, id: str):
        self.id = id
        self.created_at = timestamp()
        self.last_active = timestamp()
        self.data: Dict[str, any] = {}
        self.clients: Set[Client] = set()
        self.doc: Doc = Doc()

    def response(self):
        return SessionResponse(
            id=self.id,
            created_at=self.created_at,
            last_active=self.last_active,
            data=self.data)

class SessionManager:
    def __init__(self, session_timeout: timedelta = None):
        self.sessions: Dict[str, Session] = {}
        self.client_to_session: Dict[str, str] = {}
        self.session_timeout = session_timeout or timedelta(minutes=5)
        self.cleanup_task: Optional[asyncio.Task] = None

    def start_cleanup_task(self):
        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(self.cleanup_expired_sessions())

    async def cleanup_expired_sessions(self):
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            current_time = timestamp()
            expired_sessions = [
                session_id for session_id, session in self.sessions.items()
                if current_time - session.last_active > self.session_timeout
            ]

            for session_id in expired_sessions:
                log.info(f"Removing expired session", extra={"session_id": session_id})
                session = self.sessions.pop(session_id, None)
                if session:
                    # Remove client mappings
                    for client_id in session.clients:
                        self.client_to_session.pop(client_id, None)

    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new session or return existing one if session_id is provided"""
        ts = timestamp()
        if session_id and session_id in self.sessions:
            self.sessions[session_id].last_active = ts
            return session_id

        # Create new session
        new_session_id = session_id or str(uuid4())
        self.sessions[new_session_id] = Session(
            id=new_session_id,
        )
        log.info(f"Created new session", extra={"session_id": new_session_id})
        return new_session_id

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        session = self.sessions.get(session_id)
        if session:
            session.last_active = timestamp()
        return session

    def register_client(self, client_id: str, session_id: str, send_to_client: Callable[[object], Awaitable[None]]) -> bool:
        """Associate a client with a session"""
        if session_id not in self.sessions:
            return False
        client = Client(client_id, send_to_client)

        # Remove client from any previous session
        prev_session_id = self.client_to_session.get(client_id)
        if prev_session_id and prev_session_id in self.sessions:
            self.sessions[prev_session_id].clients.discard(client)

        # Add to new session
        self.sessions[session_id].clients.add(client)
        self.client_to_session[client_id] = session_id
        self.sessions[session_id].last_active = timestamp()
        log.info(f"Client: %s joined session %s", client_id, session_id)
        return True

    def unregister_client(self, client_id: str) -> Optional[str]:
        """Remove a client from its session"""
        session_id = self.client_to_session.pop(client_id, None)
        if session_id and session_id in self.sessions:
            self.sessions[session_id].clients.discard(Client(client_id, None))
            self.sessions[session_id].last_active = timestamp()
            log.info(f"Client left session", extra={"session_id": session_id})
            return session_id
        return None

    def get_session_by_client(self, client_id: str) -> Optional[Session]:
        """Get a client's session"""
        session_id = self.client_to_session.get(client_id)
        if session_id:
            return self.get_session(session_id)
        return None

    def get_session_data(self, session_id: str) -> Dict[str, Any]:
        """Get session data"""
        session = self.get_session(session_id)
        return session.data if session else {}

    def update_session_data(self, session_id: str, key: str, value: Any) -> bool:
        """Update session data"""
        session = self.get_session(session_id)
        if not session:
            return False
        session.data[key] = value
        return True

    async def broadcast_to_session(self, session_id: str, message: Any, exclude_client: Optional[str] = None):
        """Queue a message to be broadcast to all clients in a session"""
        session = self.get_session(session_id)
        if not session:
            return
        exclude = Client(exclude_client, None)
        clients = session.clients - {exclude}
        await asyncio.gather(*[c.send(message) for c in clients])

