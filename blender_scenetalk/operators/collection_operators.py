import bpy


class SCENETALK_OT_ToggleSceneTalkCollectionExport(bpy.types.Operator):
    """Add generative properties to object"""
    bl_idname = "scenetalk.toggle_collection_export"
    bl_label = "Toggle export of collection"
    bl_description = "Toggle the export property for the collection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        active_collection = context.collection
        new_status = not active_collection.get("export_scenetalk", False)
        active_collection["export_scenetalk"] = new_status
        if new_status:
            self.report({'INFO'}, f"SceneTalk collection export enabled: `{active_collection.name}`")
        else:
            self.report({'INFO'}, f"SceneTalk collection export disabled: `{active_collection.name}`")
        return {'FINISHED'}

classes = (
    SCENETALK_OT_ToggleSceneTalkCollectionExport,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)