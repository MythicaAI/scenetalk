import asyncio
import logging
from base64 import b64decode, b64encode
from typing import Any, Dict, Optional, Set

from pycrdt import Array, Doc, Map
from pydantic import BaseModel

from .client import Client
from .models import SessionInfo
from .timestamp import timestamp

log = logging.getLogger(__name__)


def log_doc_state(d: Doc):
    def log_doc_internal(indent, k, o):
        log.info(f"{indent * ' '}{k}: {o}")
        if isinstance(o, Map):
            for sub_k, sub_o in o.items():
                log_doc_internal(indent + 2, sub_k, sub_o)
        if isinstance(o, Array):
            for i, v in enumerate(o):
                log_doc_internal(indent + 2, str(i), v)

    for k, o in d.items():
        log_doc_internal(0, k, o)

class Session:
    def __init__(self, id: str):
        self.id = id
        self.created_at = timestamp()
        self.last_active = timestamp()
        self.props: Dict[str, any] = {}
        self.clients: Set[Client] = set()
        self.doc: Doc = Doc()
        self.checkpoint: bytes | None = None
        self.mesh_cache: Dict[str, Any] = {}

    async def broadcast(self, msg: BaseModel, exclude: Optional[Client] = None):
        """Queue a message to be broadcast to all clients in a session"""
        clients = self.clients - {exclude}
        await asyncio.gather(*[c.send(msg.op, msg.data) for c in clients])

    def build_info(self, client_id: str) -> SessionInfo:
        self.checkpoint = self.doc.get_state()
        if self.checkpoint is None:
            state = bytes()
        else:
            state = b64encode(self.checkpoint).decode('utf-8')
        return SessionInfo(
            session_id=self.id,
            client_id=client_id,
            created_at=self.created_at,
            last_active=self.last_active,
            props=self.props,
            state=state)

    def cache_mesh(self, data):
        name = data.get('name')
        if not name:
            log.info("name not provided to mesh cache")
            return False
        self.mesh_cache[name] = data
        return True

    def apply_update(self, client_id: str, encoded_data: str):
        if not encoded_data:
            log.warning("apply_update with missing encoded_data")
            return
        bdata = b64decode(encoded_data, validate=True)
        self.doc.apply_update(bdata)
        self.last_active = timestamp()
        log.info("Document state:")
        log_doc_state(self.doc)

        log.info(f"Updated session", extra={"session_id": self.id})

    def checkpoint(self):
        self.checkpoint = self.doc.get_state()

    def get_update(self) -> bytes:
        return self.doc.get_update(self.checkpoint)