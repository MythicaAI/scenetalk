import bpy
import asyncio
import threading
import logging

# Import the SceneTalk client
from .scenetalk_client import SceneTalkClient
from .async_wrap import run_async_bg

# Global connection state
_client = None

logger = logging.getLogger("scenetalk_connection")

def init_client(event_queue: asyncio.Queue):
    """Initialize the SceneTalk client."""
    global _client
    _client = SceneTalkClient(event_queue)
    return _client

# Connection management functions
def get_client():
    """Get the SceneTalk client instance."""
    global _client
    return _client

    
def get_connection_state():
    """Get the current connection state."""
    global _client
    if _client is None:
        return "uninitialized"
    return _client.connection_state

def connect_to_server(endpoint):
    """Connect to the Houdini server."""
    
    client = get_client()
    if not client:
        logger.error("Client not initialized")
        return
    run_async_bg(client.connect(endpoint))
    return True

def disconnect_from_server():
    """Disconnect from the Houdini server."""
    client = get_client()    
    if client:
        run_async_bg(client.disconnect(msg="disconnect_from_server"))
    return True