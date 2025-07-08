print("scenetalk_blender __init__.py loaded")

import bpy
import asyncio
import logging
import os
import sys

# Add the 'libs' folder to the Python path for included libraries
libs_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "lib")
if libs_path not in sys.path:
    sys.path.append(libs_path)

from .build_object import upsert_object_data

from .scenetalk_connection import init_client
from .event_types import EventType
from .async_wrap import stop_event_loop

from .panels import object_panel, scene_panel
from .operators import connection_operators, object_operators, collection_operators
from .panels.scene_panel import refresh_connection_panel
from . import properties
from . import scenetalk_sync
from . import scenetalk_host
from . import scenetalk_rollbound_sync

logger = logging.getLogger("extension.__init__")
_event_queue = None

bl_info = {
    "name": "Blender SceneTalk",
    "author": "Jacob Repp",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Object > Procedural Generation",
    "description": "Integrates generative assets such as HDAs into Blender",
    "warning": "Experimental",
    "doc_url": "",
    "category": "Object",
}


def register():
    global _event_queue

    properties.register()
    connection_operators.register()
    object_operators.register()
    collection_operators.register()
    scene_panel.register()
    object_panel.register()
    scenetalk_sync.register()
    scenetalk_rollbound_sync.register()
    scenetalk_host.register()
    
    _event_queue = asyncio.Queue()
    init_client(_event_queue)

    # periodically process the queue on the main blender thread
    def process_queue():
        while not _event_queue.empty():
            ev = _event_queue.get_nowait()
            if not ev:
                continue
            event_type = ev[0]
            if event_type == EventType.GEOMETRY:
                model_type, obj_name, input_objects, geometry, schema = ev[1], ev[2], ev[3], ev[4], ev[5]
                upsert_object_data(model_type, obj_name, input_objects, geometry, schema)
            elif event_type == EventType.STATUS:
                logger.info("Status: %s", ev[1])
            elif event_type == EventType.ERROR:
                logger.error("Error: %s", ev[1])
            elif event_type == EventType.CONNECTED:
                logger.info("Connected to %s", ev[1])
                refresh_connection_panel()
                # enable object tracking TODO-jrepp re-enable
                # bpy.ops.object.track_changes('INVOKE_DEFAULT')
            elif event_type == EventType.DISCONNECTED:
                logger.info("Disconnected")
                refresh_connection_panel()
            elif event_type == EventType.ERROR:
                logger.error("Error: %s", ev[1])
            elif event_type == EventType.QUIT:
                logger.info("Quitting")
                bpy.app.timers.unregister(process_queue)
                return
            
        return 0.1
    
    bpy.app.timers.register(process_queue)


def unregister():
    global _event_queue
    _event_queue.put_nowait([EventType])
    stop_event_loop()

    scenetalk_host.unregister()
    scenetalk_sync.unregister()
    scenetalk_rollbound_sync.unregister()
    scene_panel.unregister()
    object_panel.unregister()
    collection_operators.unregister()
    object_operators.unregister()
    connection_operators.unregister()
    properties.unregister()
    
    

if __name__ == "__main__":
    register()
