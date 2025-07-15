import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty
from . import models

def endpoint_updated(self, context):
    """Update function for the endpoint property."""
    if self.auto_connect:
        bpy.ops.scenetalk.connect('INVOKE_DEFAULT')

# Connection properties
class SceneTalkProperties(bpy.types.PropertyGroup):
    """Connection properties for SceneTalk integration."""
    endpoint: StringProperty(
        name="Endpoint",
        description="SceneTalk endpoint e.g.: wss://hostname:port/path",
        default="wss://scenetalk.mythica.gg/ws/",
        update=endpoint_updated)
    
    auto_connect: BoolProperty(
        name="Auto Connect",
        description="Automatically connect on startup",
        default=False
    )

    show_connection_settings: BoolProperty(
        name="Show Connection Settings",
        description="Expand/collapse connection settings",
        default=False
    )

    # for creating models
    model_type: EnumProperty(
        name="Type",
        description="Select model type to generate",
        items=models.get_model_item_enum(),
        default='CRYSTALS',
    )

    export_directory: bpy.props.StringProperty(
        name="Export Directory",
        description="Directory to save temporary export files",
        subtype='DIR_PATH'
    )



def register():
    bpy.utils.register_class(SceneTalkProperties)
    bpy.types.Scene.scenetalk_props = bpy.props.PointerProperty(type=SceneTalkProperties)

def unregister():
    bpy.utils.unregister_class(SceneTalkProperties)
    del bpy.types.Scene.scenetalk_props