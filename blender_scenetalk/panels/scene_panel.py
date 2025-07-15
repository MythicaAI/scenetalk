import bpy
import logging
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.app.handlers import persistent


# Import the SceneTalk client
from ..scenetalk_client import SceneTalkClient, ConnState
from ..scenetalk_connection import get_client, get_connection_state, connect_to_server, disconnect_from_server
from ..properties.scenetalk_properties import SceneTalkProperties

from ..properties import models

logger = logging.getLogger("connection_panel")


# Connection Panel
class SCENETALK_PT_ConnectionPanel(bpy.types.Panel):
    """SceneTalk Connection Panel"""
    bl_label = "SceneTalk Connection"
    bl_idname = "SCENETALK_PT_ConnectionPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SceneTalk'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.scenetalk_props

        # Create a button to toggle scene talk collection export
        box = layout.box()
        row = box.row()
        row.label(text="SceneTalk Collection Export:")
        row.scale_x = 1.5  # Make button bigger
        row.operator("scenetalk.toggle_collection_export", text="Toggle Export", icon='EXPORT')
        
        # Connection endpoint
        box = layout.box()
        
        # Status display
        row = box.row()
        row.prop(props, "show_connection_settings", 
                 icon="TRIA_DOWN" if props.show_connection_settings else "TRIA_RIGHT",
                 icon_only=True, emboss=False)
        client = get_client()
        state = client.connection_state if client else ConnState.DISCONNECTED
        if state == ConnState.CONNECTED:
            row.label(text="Connected", icon='CHECKMARK')
        elif state == ConnState.CONNECTING:
            row.label(text="Connecting...", icon='SORTTIME')
        elif state == ConnState.DISCONNECTING:
            row.label(text="Disconnecting...", icon='SORTTIME')
        elif state == ConnState.ERROR:
            row.label(text=f"Error: {client.last_error}", icon='ERROR')
        else:
            row.label(text="Disconnected", icon='X')
        
        # Endpoint input
        if props.show_connection_settings:
            row = box.row()
            row.label(text="Endpoint:")
            row = box.row()
            row.prop(props, "endpoint", text="")
            
            # Button row
            row = box.row(align=True)
            
            if state == "connected":
                row.operator("scenetalk.disconnect", text="Disconnect", icon='CANCEL')
            else:
                row.operator("scenetalk.connect", text="Connect", icon='PLAY')
                     
            # Auto-connect toggle
            row = box.row()
            row.prop(props, "auto_connect")

            # Export directory
            row = box.row()
            row.label(text="Export Directory:")
            row = box.row()
            row.prop(props, "export_directory", text="")

        # Show connected controls
        if state != "connected":
            return
        
        box = layout.box()
        row = box.row()
        row.prop(props, "model_type")

        row = box.row()
        op = row.operator("gen.create_model", text="Create")
        op.track_inputs = False
        
        op = row.operator("gen.create_model", text="Use Input")
        op.track_inputs = True

        # Get the active object
        active_object = context.active_object
        if active_object and not active_object.select_get():
            active_object = None
    
        # Count the number of selected objects
        is_multi_select = len(context.selected_objects) > 1
        first_obj = context.selected_objects[0] if is_multi_select else None
        selected = active_object or first_obj

        box = layout.box()
        row = box.row()
        row.label(text="Selection:")
        
        if is_multi_select:
            row.label(text=f"{len(context.selected_objects)} objects selected")
        else:
            obj_name = selected.name if selected else "None"
            row.label(text=obj_name)

        if not active_object and not is_multi_select:
            return
        
        model_type = selected.get('model_type', None)
        if model_type is None:
            return
        
        all_matching_type = all(obj.get("model_type", None) == model_type for obj in context.selected_objects)

        # TODO overlap properties?
        if not all_matching_type:
            row = box.row()
            row.label(text="various types")
            return
        
        # Reset/init button
        row = box.row()
        row.scale_y = 1.5  # Make button bigger
        row.operator("gen.init_params", text="Reset", icon='FILE_REFRESH')

        # Process button
        row.scale_y = 1.5  # Make button bigger
        row.operator("gen.process", text="Cook", icon='MOD_HUE_SATURATION')

        # Status information
        status_row = box.row()

        # Status with icon
        gen = selected.gen
        if gen.status == "cooking":
            status_row.label(text="Cooking", icon='SORTTIME')
        elif gen.status == "cooked":
            status_row.label(text="Cooked", icon='CHECKMARK')
        elif gen.status == "initialized":
            status_row.label(text="Initialized", icon='SORTTIME')
        else:
            status_row.label(text=f"Status: {gen.status}", icon='INFO')

        # Show properties based on selected model type
        props = models.get_model_props(gen, model_type)
        box.label(text=model_type + ":")
        if props:
            props.draw(box)

        # File selection - TODO make dropdown
        box = layout.box()
        box.label(text="File name", icon='FILE_BLEND')
        row = box.row()
        row.prop(gen, "file_name", text="")

        # List of inputs
        box = layout.box()
        for input in gen.inputs:
            row = box.row()
            row.prop(input, "input_ref", text="")
            

            row.prop(input, "input_type", text="")
            row.prop(input, "enabled")

        row = box.row()
        row.operator("gen.add_input", text="Add", icon='ADD')
        row.operator("gen.remove_input", text="Remove", icon='REMOVE')
        

# Auto-connect on startup
def connect_on_startup():
    # Check if auto-connect is enabled
    if bpy.context.scene.scenetalk_props.auto_connect:
        logger.info("Auto-connecting to SceneTalk server...")
        endpoint = bpy.context.scene.scenetalk_props.endpoint
        connect_to_server(endpoint)

# Registration
classes = (
    SCENETALK_PT_ConnectionPanel,
)

# Define update callback for selection changes
@persistent
def selection_change_callback(_scene):
    refresh_connection_panel()

def refresh_connection_panel():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register selection change handler
    bpy.app.handlers.depsgraph_update_post.append(selection_change_callback)

    # This avoids issues with trying to connect before the UI is ready
    bpy.app.timers.register(connect_on_startup, first_interval=.5)


def unregister():
    # Ensure disconnection
    if get_connection_state() == ConnState.CONNECTED:
        disconnect_from_server()

    # Remove selection change handler
    if selection_change_callback in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(selection_change_callback)

    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()