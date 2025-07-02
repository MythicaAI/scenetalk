from blender_scenetalk.async_wrap import run_async_bg
from blender_scenetalk.scenetalk_connection import get_client
import bpy
from .scenetalk_state import doc, scene, observe_changes
from .scenetalk_connection import get_client
from .export_collection_rollbound import export_collection_rollbound

STATE_HASH_KEY = "scenetalk_hash"
SYNC_DELAY = 0.5



def send_verts(vert_hash, obj):
    client = get_client()
    if client:
        # data = export_mesh_simple(vert_hash, obj)
        # run_async_bg(client.send_mesh(data))
        pass

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
        export_collection_rollbound()

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
        print("Tracking stopped")
    
    @classmethod
    def stop_tracking(cls):
        cls.is_tracking = False
        print("Tracking will stop on next timer event")


# Registration
def register():
    bpy.utils.register_class(OBJECT_OT_track_changes_rollbound)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_track_changes_rollbound)
