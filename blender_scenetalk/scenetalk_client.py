import asyncio
import base64
from datetime import datetime, timezone, timedelta
from enum import Enum
from functools import partial
import json
import logging
from random import random
import secrets
import string
import sys
import contextlib
import os
from typing import Dict, Any, Optional, Tuple, Callable
from asyncio import Queue
from uuid import uuid4

from .scenetalk_state import apply_remote_update
from .event_types import EventType
from .model_db import find_by_name
#from .scenetalk_state import apply_remote_updates

# Add the 'libs' folder to the Python path
libs_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib")
if libs_path not in sys.path:
    sys.path.append(libs_path)

import httpx
from httpx_ws import WebSocketNetworkError, aconnect_ws

# Configure logging
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("scenetalk_client")

ping_interval_seconds = 15

def random_obj_name(model_type) -> str:
    """Generate a random object name."""
    rand_str = ''.join(secrets.choice(string.ascii_lowercase) for i in range(10))
    obj_name = f"{model_type.upper()}_{rand_str}"
    return obj_name


async def process_message(client, response: object) -> bool:
    """Generic SceneTalk response processor"""
    op_type = response['op']
    # logger.info(f"process_response: {op_type}")
    if op_type == "update":
        apply_remote_update(response["data"])
    elif op_type == "error":
        await client.event_queue.put((EventType.ERROR, response["data"]))
    elif op_type == "geometry":
        # TODO - decide on model or schema or job def language
        await client.event_queue.put((EventType.GEOMETRY,
                                    client.current_model_type,
                                    client.current_object_name or random_obj_name(),
                                    client.current_inputs,
                                    response,
                                    client.current_object_schema))
    completed = op_type == "automation" and \
        response["data"] == "end"
    return completed


async def client_task(client):
    """Client task to handle WebSocket events."""
    ws = client.websocket
    shutdown_event = client._shutdown_event
    last_ping = None
    while not shutdown_event.is_set():
        try:
            text_message = await ws.receive_text(timeout=.5)
            print("received event", text_message)
        except asyncio.TimeoutError:
            continue
        
        try: 
            obj = json.loads(text_message)
            await process_message(client, obj)
        except json.JSONDecodeError as e:
            logger.exception(f"invalid JSON message: {text_message}")
            continue
        except Exception as e:
            logger.exception(f"error processing message: {text_message}")
            continue

        # handle ping/pong keepalive
        try:
            now = datetime.now(timezone.utc)
            if not last_ping or now - last_ping > timedelta(seconds=ping_interval_seconds):
                print("sending ping")
                ping_sent_time = asyncio.get_event_loop().time()
                pong_callback = await ws.ping()
                result = await pong_callback.wait()
                if result is None:
                    await client.disconnect("ping timed out")
                elapsed = asyncio.get_event_loop().time() - ping_sent_time
                print("received pong", elapsed)
        except WebSocketNetworkError as e:
            msg = f"WebSocket error: {e}"
            logger.exception()
            await client.disconnect(msg)
            break
        except Exception as e:
            logger.exception(f"Error in client task: {e}")

class CookRequest:
    def __init__(self,
                 model_type: str,
                 obj_name: str,
                 object_inputs: list,
                 params: dict):
        self.model_type = model_type
        self.obj_name = obj_name
        self.object_inputs = object_inputs
        self.params = params
        self.schema = find_by_name(model_type)
        assert self.schema is not None
        self.file_path = self.schema['file_path']
        self.file_id = self.schema['file_id']
        self.file_type = self.schema['file_type']


class ConnState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    ERROR = "error"


class SceneTalkClient:
    """Minimal client for communicating with Houdini via WebSocket."""

    def __init__(self, event_queue: Queue, host: str = "localhost", port: int = 8765):
        self.event_queue = event_queue
        self.ws_url = f"ws://{host}:{port}"
        self.client = None
        self.websocket = None
        self.async_stack = None
        self.connection_state = ConnState.DISCONNECTED
        self.last_error = None
        self._client_task = None
        self._shutdown_event = None
        self._correlations = {}

    async def connect(self, endpoint) -> bool:
        """Connect to the SceneTalk WebSocket server."""
        if self.connection_state ==ConnState.CONNECTED or \
              self.connection_state == ConnState.CONNECTING:
            return
        
        self.last_error = None
        self.state = "connecting"
        logger.info(f"Connecting to {endpoint}")
        try:
            self.client = httpx.AsyncClient(
                base_url=endpoint,
                timeout=5,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                http2=False,
            )

            # create the websocket connection object, it has to be wrapped
            # in an async stack to handle the async generator
            self.async_stack = contextlib.AsyncExitStack()
            self.websocket = await self.async_stack.enter_async_context(
                aconnect_ws(endpoint, self.client))
            self.connection_state = ConnState.CONNECTED
            self.ws_url = endpoint
            if self._client_task:
                self._shutdown_event.set()
                await self._client_task
            
            await self.event_queue.put([EventType.CONNECTED, self.ws_url])
            self._shutdown_event = asyncio.Event()
            self._client_task = asyncio.create_task(client_task(self))
            
            return True
        
        except httpx.ConnectError as e:
            self.last_error = f"Connection error: {e}"
            await self.event_queue.put((EventType.ERROR, self.last_error))
            await self.disconnect()
            return False
        except Exception as e:
            self.last_error = f"Connection failure: {e}"
            await self.event_queue.put((EventType.ERROR, self.last_error))
            await self.disconnect()
            return False

    async def disconnect(self, msg: str):
        """Disconnect from the WebSocket server."""
        self.connection_state = ConnState.DISCONNECTING

        if self._client_task:
            self._shutdown_event.set()
            self._client_task = None
            self._shutdown_event = None

        if self.websocket:
            await self.websocket.close()
            self.websocket = None

        if self.async_stack:
            await self.async_stack.aclose()
            self.async_stack = None

        if self.client:
            await self.client.aclose()
            self.client = None

        self.connection_state = ConnState.DISCONNECTED

        await self.event_queue.put([EventType.DISCONNECTED, self.ws_url, msg or ""])

    async def send_cook(self, req: CookRequest):
        """Send a cook message to the server."""
        cid = str(uuid4())
        # self._correlations[cid] = req
        
        if not self.websocket or self.connection_state != ConnState.CONNECTED:
            logger.error("Cannot send message: not connected")
            return False
        try:
            msg = {   
                "op": "cook",
                "cor": cid,
                "data": {
                    "hda_path": {
                        "file_id": "file_local_hda",
                        "file_path": req.schema['file_path']
                    },
                    "definition_index": 0,
                    "format": "raw",
                    **req.params  # Unpack all parameters
                }
            }
            json_message = json.dumps(msg)
            await self.websocket.send_text(json_message)
            return True
        except httpx.WriteError as e:
            logger.error(f"Error sending message: {e}")
            return False
        
    async def send_update(self, update: bytes) -> bool:
        try:
            msg = {
                "op": "update",
                "data": {
                    "update": base64.b64encode(update).decode('utf-8')
                }
            }
            json_message = json.dumps(msg)
            await self.websocket.send_text(json_message)
            return True
        except httpx.WriteError as e:
            logger.error(f"Error sending message: {e}")
        return False

    async def send_message(self, 
                           message: Dict[str, Any]) -> bool:
        """Send a message to the server."""
        if not self.websocket or self.connection_state != ConnState.CONNECTED:
            logger.error("Cannot send message: not connected")
            return False
        try:
            await self.websocket.send_text(json.dumps(message))
            return True
        except (httpx.WriteError, httpx.LocalProtocolError) as e:
            logger.error(f"Error sending message: {e}")
        return False

    async def upload_file(
            self,
            file_id: str,
            file_path: str,
            content_type: str = "application/octet-stream") -> bool:
        """Upload a file to the server."""
        try:
            with open(file_path, "rb") as f:
                file_content = f.read()
                base64_content = base64.b64encode(file_content).decode('utf-8')

            upload_message = {
                "op": "file_upload",
                "data": {
                    "file_id": file_id,
                    "content_type": content_type,
                    "content_base64": base64_content
                }
            }
            await self.send_message(upload_message)
            return True

        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return False
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return False
