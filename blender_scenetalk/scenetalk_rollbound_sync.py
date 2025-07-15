import bpy
from bpy.app.handlers import persistent
from blender_scenetalk.async_wrap import run_async_bg
import hashlib
import json
from pydantic import BaseModel

from .host.app import session_manager
from .host.models import GeometrySet
from .host.ops import Ops
from .export_mesh_scenetalk import export_mesh_scenetalk

STATE_HASH_KEY = "scenetalk_hash"
SYNC_DELAY = 5.0


class GeometryOp(BaseModel):
    op: Ops = Ops.GEOMETRY
    data: GeometrySet


class OBJECT_OT_track_changes_rollbound(bpy.types.Operator):
    """Track changes to objects in real-time"""
    bl_idname = "object.track_changes_rollbound"
    bl_label = "Track Object Changes for Rollbound Sync"
    
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

        # Gather all changed geometry from all collections
        geometry = GeometrySet(geometry={})

        for collection in bpy.data.collections:
            export_enabled = collection.get("export_scenetalk", False)

            if not export_enabled or not collection.objects:
                continue

            # Serialize objects to geometry
            for obj in collection.objects:
                if obj.type != 'MESH':
                    continue

                object_geometry = export_mesh_scenetalk(obj.name, obj)
                hash = hashlib.sha1(json.dumps(object_geometry.model_dump()).encode("utf-8")).digest().hex()

                if hash == obj.get(STATE_HASH_KEY, None):
                    continue

                obj[STATE_HASH_KEY] = hash
                geometry.geometry.update(object_geometry.geometry)

        # Send geometry to clients
        if (len(geometry.geometry) > 0):
            geometry_op = GeometryOp(data=geometry)
            for [_,session] in session_manager.sessions.items():
                print(f"Syncing geometry to session {session.id}")
                run_async_bg(session.broadcast(geometry_op)) 


    def invoke(self, context, event):
        self.is_tracking = True
        wm = context.window_manager
        self._timer = wm.event_timer_add(SYNC_DELAY, window=context.window)
        wm.modal_handler_add(self)
        self.capture_object_data(context)
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        self.is_tracking = False
    
    @classmethod
    def stop_tracking(cls):
        cls.is_tracking = False
        print("Tracking will stop on next timer event")


# Registration

@persistent
def _rollbound_after_load(_dummy):
    bpy.ops.object.track_changes_rollbound('INVOKE_DEFAULT')

def register():
    bpy.utils.register_class(OBJECT_OT_track_changes_rollbound)
    bpy.app.handlers.load_post.append(_rollbound_after_load)

def unregister():
    bpy.app.handlers.load_post.remove(_rollbound_after_load)
    bpy.utils.unregister_class(OBJECT_OT_track_changes_rollbound)
