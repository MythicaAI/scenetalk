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
import os
from typing import Dict, Any, Optional, Tuple, Callable
from asyncio import Queue
from uuid import uuid4

from .scenetalk_state import apply_remote_update, set_remote_state
from .event_types import EventType
from .model_db import find_by_name

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

    def __init__(self, event_queue: Queue):
        self.event_queue = event_queue
        self.session_id: str | None = None
        self.client_id: str | None = None
        self.ws_url: str | None = None
        self.client: httpx.AsyncClient | None = None
        self.websocket = None
        self.connection_state = ConnState.DISCONNECTED
        self.last_error: str | None = None
        self.client_id: str | None = None
        self._client_task = None
        self._shutdown_event = None
        self._correlations = {}

    async def connect(self, endpoint) -> bool:
        """Connect to the SceneTalk WebSocket server."""
        # stop existing client task and detach it
        try:
            if self._client_task and self._shutdown_event:
                self._shutdown_event.set()
                await self._client_task
        finally:
            self._client_task = None
            self._shutdown_event = None
            self.last_error = None
        
        self.state = ConnState.CONNECTING
        logger.info(f"Connecting to {endpoint}")
        self._client_task = asyncio.create_task(self.start_connection(endpoint))
        return True

    async def start_connection(self, endpoint):
        try:
            self.client = httpx.AsyncClient(
                base_url=endpoint,
                timeout=5,
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                http2=False,
            )
            async with aconnect_ws(endpoint, self.client) as ws:
                self.websocket = ws
                self.ws_url = endpoint
                self._shutdown_event = asyncio.Event()
                self.connection_state = ConnState.CONNECTED
                await self.event_queue.put([EventType.CONNECTED, endpoint])
                # start the client service task inside this context
                await self.service()
        except Exception as e:
            self.last_error = f"Connection failure: {e}"
            logger.exception(self.last_error)
            await self.event_queue.put((EventType.ERROR, self.last_error))
        finally:
            self.websocket = None
            self.client = None
            self._shutdown_event = None
            self.connection_state = ConnState.DISCONNECTED

    async def process_message(self, response: dict[str, Any]) -> bool:
        """Generic SceneTalk response processor"""
        op_type = response['op']
        # logger.info(f"process_response: {op_type}")
        if op_type == "update":
            client_id = response["data"]["client_id"]   
            update_bytes = base64.b64decode(response["data"]["update"])
            apply_remote_update(client_id, update_bytes)
        elif op_type == "session_info":
            self.session_id = response["data"]["session_id"]
            self.client_id = response["data"]["client_id"]
            state_bytes = base64.b64decode(response["data"]["state"])
            set_remote_state(state_bytes)
            logger.info(f"session_info: {self.session_id}, client_id: {self.client_id}")    
        elif op_type == "error":
            await self.event_queue.put((EventType.ERROR, response["data"]))
        elif op_type == "geometry":
            # TODO - decide on model or schema or job def language
            await self.event_queue.put((EventType.GEOMETRY,
                                        self.current_model_type,
                                        self.current_object_name or random_obj_name(),
                                        self.current_inputs,
                                        response,
                                        self.current_object_schema))
        completed = op_type == "automation" and \
            response["data"] == "end"
        return completed


    async def service(self):
        """Client task to handle WebSocket events."""
        # cacne the connection objects, they will detach from the client
        # during disconnection
        ws = self.websocket
        if not ws:
            return False
        
        shutdown_event = self._shutdown_event
        last_ping = None
        while shutdown_event and not shutdown_event.is_set():
            try:
                text_message = await ws.receive_text(timeout=1.0)
                print("received event", text_message)
            except TimeoutError:
                continue
            
            try: 
                obj = json.loads(text_message)
                await self.process_message(obj)
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
                    await pong_callback.wait()
                    elapsed = asyncio.get_event_loop().time() - ping_sent_time
                    print("received pong", elapsed)
            except Exception as e:
                msg = f"Error: {e}"
                logger.exception(msg)
                await self.disconnect(msg)
                break

    async def disconnect(self, msg: str):
        """Disconnect from the WebSocket server."""
        logger.info("disconnect(%s)", msg)
        self.connection_state = ConnState.DISCONNECTING
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        if self._shutdown_event:
            self._shutdown_event.set()
            self._client_task = None
            self._shutdown_event = None

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
    
    async def send_mesh(self, data: object) -> bool:
        try:
            if not self.websocket or self.connection_state != ConnState.CONNECTED:
                logger.error("Cannot send message: not connected")
                return False
            msg = {
                "op": "geometry",
                "data": data
            }
            json_message = json.dumps(msg)
            await self.websocket.send_text(json_message)
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
        
    async def send_update(self, update: bytes) -> bool:
        try:
            if not self.websocket or self.connection_state != ConnState.CONNECTED:
                logger.error("Cannot send message: not connected")
                return False
            msg = {
                "op": "update",
                "data": {
                    "client_id": self.client_id,
                    "update": base64.b64encode(update).decode('utf-8')
                }
            }
            json_message = json.dumps(msg)
            await self.websocket.send_text(json_message)
            return True
        except Exception as e:
            logger.exception(f"Error sending message: {e}")
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
