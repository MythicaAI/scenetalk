from blender_scenetalk.async_wrap import run_async_bg
from blender_scenetalk.scenetalk_connection import get_client
import bpy
import numpy as np
import json
from datetime import datetime
from pycrdt import Doc, Array, Map, ArrayEvent, MapEvent, TransactionEvent
import hashlib
from .scenetalk_state import doc, scene, observe_changes
from .scenetalk_connection import get_client

def handle_changes(event: TransactionEvent):
    client = get_client()
    if client:
        run_async_bg(client.send_update(event.update))

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
                
                h = hash(verts.tobytes())
                # Store state
                state = {
                    "position": (position.x, position.y, position.z),
                    "rotation": (rotation.x, rotation.y, rotation.z),
                    "scale": (scale.x, scale.y, scale.z),
                    #"verts": obj.data.vertices.to_bytes()
                }
                obj_hash = hashlib.sha1(json.dumps(state).encode("utf-8")).digest().hex()
                last_hash = obj.get('state_hash', None)
                if last_hash and last_hash == obj_hash:
                    # No change detected
                    continue

                # Store new hash
                obj['state_hash'] = obj_hash

                # Only store if different from last entry
                with doc.new_transaction() as txn:
                    # m = scene.get(obj.name, type=Map)
                    m = scene.get(obj.name)
                    if not m:
                        m = Map()
                        scene[obj.name] = m             
                    
                    m["position"] = Array(state["position"])
                    m["rotation"] = Array(state["rotation"])
                    m["scale"] = Array(state["scale"])
                    #m["verts_checksum"] = Array(state['verts_checksum'])
                    #m["verts_count"] = Array(state['verts_count'])
                
                    if self._is_significant_change(obj.name, state):
                        verts_reshape = verts.reshape(-1, 3).tolist()    
                        #m["vertices"] = Array(obj.data.vertices)

                # print(f"Change detected: {obj.name} at {timestamp}")
    
    def _state_changed(self, obj_name, new_state):
        """Check if state is different from last recorded state"""
        if not self.tracked_objects[obj_name]:
            return True
            
        last_state = self.tracked_objects[obj_name][-1]
        
        # Check for position or vertex changes
        pos_changed = last_state["position"] != new_state["position"]
        rot_changed = last_state["rotation"] != new_state["rotation"]
        scale_changed = last_state["scale"] != new_state["scale"]
        #verts_changed = last_state["verts_checksum"] != new_state["verts_checksum"]
        #count_changed = last_state["verts_count"] != new_state["verts_count"]
        
        return pos_changed or rot_changed or scale_changed
    
    def _is_significant_change(self, obj_name, new_state):
        """Determine if change is significant enough to store full vertex data"""
        if not scene.get(obj_name):
            return True
            
        last_state = scene.get(obj_name)
        
        # Check for vertex count changes (like adding faces)
        #if last_state is None or (last_state["verts_count"] != new_state["verts_count"]):
        #    return True
            
        return False
    
    def invoke(self, context, event):
        self.is_tracking = True
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
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
