from blender_scenetalk.async_wrap import run_async_bg
from blender_scenetalk.scenetalk_connection import get_client
import bpy
import numpy as np
import json
from datetime import datetime
from pycrdt import Doc, Array, Map, ArrayEvent, MapEvent, TransactionEvent, Text
import hashlib
from .scenetalk_state import doc, scene, observe_changes
from .scenetalk_connection import get_client
from .export_mesh_simple import export_mesh_simple

STATE_HASH_KEY = "scenetalk_hash"
SYNC_DELAY = 0.5

def handle_changes(event: TransactionEvent):
    client = get_client()
    if client:
        run_async_bg(client.send_update(event.update))

def send_verts(vert_hash, obj):
    client = get_client()
    if client:
        data = export_mesh_simple(vert_hash, obj)
        run_async_bg(client.send_mesh(data))

class OBJECT_OT_track_changes(bpy.types.Operator):
    """Track changes to objects in real-time"""
    bl_idname = "object.track_changes"
    bl_label = "Track Object Changes"
    
    # Storage for tracked data
    is_tracking = False
    
    def modal(self, context, event):
        if not self.is_tracking:
            return {'CANCELLED'}
            
        # Only check on timer events to avoid performance issues
        if event.type == 'TIMER':
            self.capture_object_data(context)
            
        return {'PASS_THROUGH'}
    
    def capture_object_data(self, context):
        """Capture current state of objects"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        for obj in context.visible_objects:
            if obj.type == 'MESH':    
                # Get world position
                position = obj.matrix_world.translation.copy()
                rotation = obj.matrix_world.to_euler()
                scale = obj.matrix_world.to_scale()
                
                # Get vertex positions (local space)
                verts = np.zeros(len(obj.data.vertices) * 3, dtype=np.float32)
                obj.data.vertices.foreach_get("co", verts)
                
                vert_hash = hashlib.sha1(verts.tobytes()).digest().hex()
                # Store state
                state = {
                    "position": (position.x, position.y, position.z),
                    "rotation": (rotation.x, rotation.y, rotation.z),
                    "scale": (scale.x, scale.y, scale.z),
                    "verts_checksum": vert_hash,
                    "verts_count": len(obj.data.vertices),
                }
                obj_hash = hashlib.sha1(json.dumps(state).encode("utf-8")).digest().hex()
                last_hash = obj.get(STATE_HASH_KEY, None)
                if last_hash and last_hash == obj_hash:
                    # No change detected
                    continue

                # Store new hash
                obj[STATE_HASH_KEY] = obj_hash

                # seed the vertex data in the session with it's immutable hash
                send_verts(vert_hash, obj)

                print(f"Change detected: {obj.name} obj: {obj_hash}, mesh: {vert_hash} at {timestamp}")

                # Only store if different from last entry
                with doc.transaction() as _txn:
                    m = scene.get(obj.name)
                    if not m:
                        m = Map()
                    
                    # first integrate into document
                    scene[obj.name] = m

                    # convert state to map
                    m["position"] = Array(state["position"])
                    m["rotation"] = Array(state["rotation"])
                    m["scale"] = Array(state["scale"])
                    m["verts_checksum"] = Text(state['verts_checksum'])
                    m["verts_count"] = state['verts_count']

                    
                    
    
    def invoke(self, context, event):
        self.is_tracking = True
        wm = context.window_manager
        self._timer = wm.event_timer_add(SYNC_DELAY, window=context.window)
        wm.modal_handler_add(self)
        self.capture_object_data(context)
        observe_changes(handle_changes)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.is_tracking = False
        print("Tracking stopped")
    
    @classmethod
    def stop_tracking(cls):
        cls.is_tracking = False
        print("Tracking will stop on next timer event")


# Registration
def register():
    bpy.utils.register_class(OBJECT_OT_track_changes)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_track_changes)
