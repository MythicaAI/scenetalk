import bpy
from bpy.props import StringProperty, BoolProperty

from ..scenetalk_connection import connect_to_server, disconnect_from_server, get_client, get_connection_state
from ..scenetalk_client import ConnState

# Connect operator
class SCENETALK_OT_Connect(bpy.types.Operator):
    """Connect to Houdini Server"""
    bl_idname = "scenetalk.connect"
    bl_label = "Connect to SceneTalk Endpoint"
    bl_options = {'REGISTER'}
    
    timer = None
        
    def modal(self, context, event):
        if event.type == 'TIMER':
            client = get_client()
            if client is None:
                return {'CANCELLED'}
            
            state = client.connection_state
            if state == ConnState.CONNECTING:
                return {'RUNNING_MODAL'}
            elif state == ConnState.DISCONNECTING:
                return {'RUNNING_MODAL'}
            elif state == ConnState.CONNECTED:
                self.report({'INFO'}, f"Connected to {client.ws_url}")
                return {'FINISHED'}
            elif state == ConnState.ERROR or state == ConnState.DISCONNECTED:
                error_msg = client.last_error or "Disconnected"
                self.report({'ERROR'}, error_msg)
                return {'CANCELLED'}

            self.report({'ERROR'}, f"Unknown client state: {state}")
            return {'CANCELLED'}
        return {'PASS_THROUGH'}  # Let other events through
    
    def invoke(self, context, event):
        self.timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)

        endpoint = context.scene.scenetalk_props.endpoint
        self.report({'INFO'}, f"Connecting to {endpoint}")
        connect_to_server(endpoint)
        return {'RUNNING_MODAL'}    

# Disconnect operator
class SCENETALK_OT_Disconnect(bpy.types.Operator):
    """Disconnect from SceneTalk Server"""
    bl_idname = "scenetalk.disconnect"
    bl_label = "Disconnect from SceneTalk Endpoint"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        if disconnect_from_server():
            self.report({'INFO'}, "Disconnecting from SceneTalk server")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Disconnection failed")
            return {'CANCELLED'}

            
classes = (
    SCENETALK_OT_Connect,
    SCENETALK_OT_Disconnect,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)