

import bpy
from bpy.props import PointerProperty, StringProperty, BoolProperty

import json
import logging

from ..build_object import create_object

from ..cook import cook
from ..async_wrap import run_async_bg
from ..scenetalk_client import random_obj_name, ConnState
from ..scenetalk_connection import get_connection_state, get_client
from ..model_db import find_by_name
from ..properties.models import get_model_props

logger = logging.getLogger("object_operators")

class GEN_OT_AddToObject(bpy.types.Operator):
    """Add generative properties to object"""
    bl_idname = "gen.add_to_object"
    bl_label = "Add gen properties"
    bl_description = "Add the generative property to the object data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.object

        if not obj:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}

        obj.gen.enabled = True
        obj.gen.status = "initialized"

        self.report({'INFO'}, "Added to object")
        return {'FINISHED'}

# Operator to create the selected model
class GEN_OT_CreateModel(bpy.types.Operator):
    bl_idname = "gen.create_model"
    bl_label = "Create Model"
    bl_description = "Create the selected model type at the default location"
    bl_options = {'REGISTER', 'UNDO'}
    
    track_inputs: BoolProperty(
        name="track_inputs",
        description="Track inputs",
        default=False
    )

    def execute(self, context):
        model_type = context.scene.scenetalk_props.model_type
        schema = find_by_name(model_type)
        if not schema:
            self.report({'ERROR'}, f"Schema not found for {model_type}")
            return {'CANCELLED'}
        
        client = get_client()
        if not client:
            self.report({'ERROR'}, "No client initialized")
            return {'CANCELLED'}
        
        obj_name = random_obj_name(model_type)
        input_objects = []
        if self.track_inputs:
            logger.info("input objects %s", context.selected_objects)
            if len(context.selected_objects) == 0:
                self.report({'ERROR'}, "No input objects selected")
                return {'CANCELLED'}
            
            # Create the placeholder object
            obj = create_object(obj_name, model_type, schema, mesh=None)
            
            # Add all the inputs
            for sel in bpy.context.selected_objects:
                input_ref = obj.gen.inputs.add()
                input_ref.input_ref = sel
                input_ref.input_type = "MESH"
                input_ref.enabled = True

            # Collect the object references for the 
            input_objects.extend(bpy.context.selected_objects)
        else:
            # Create the placeholder object
            obj = create_object(obj_name, model_type, schema, mesh=None)

        # Extract parameters into a dictionary mapping label -> default value
        params = {param_id: param["default"]
                  for param_id, param in schema["parameters"].items()}

        cook(obj, params)
        
        return {'FINISHED'}
    
    
class GEN_OT_InitParams(bpy.types.Operator):
    bl_idname = "gen.init_params"
    bl_label = "Initialize parameters"
    bl_description = "Initialize parameters from schema"
    bl_options = {'REGISTER'}

    def execute(self, context):
        obj = context.object
        if not obj:
            self.report({'ERROR'}, "No object selected")
            return {'CANCELLED'}
        
        model_type = obj.get('model_type', None)
        if not model_type:
            model_type = context.scene.scenetalk_props.model_type
            if not model_type: 
                self.report({'WARNING'}, "Object has no HDA or parameters")
                return {'CANCELLED'}
            obj['model_type'] = model_type
        
        schema = find_by_name(model_type)
        if not schema:
            self.report({'ERROR'}, f"Schema not found for {model_type}")
            return {'CANCELLED'}

        gen = obj.hdgena
        props = get_model_props(gen, model_type)
        if not props:
            return {'CANCELLED'}
        
        # TODO: pause updates while initializing
        # HACK: pass object data to inputX parameters
        
        # default values already handled in property creation
        for param_id, param_def in schema['parameters'].items():
            # Initialize the property with the default value
            if "default" in param_def:
                default = param_def["default"]
                setattr(props, param_id, default)
            else:
                continue

        obj.update_tag(refresh={'DATA'})
        return {'FINISHED'}
    
# Operator to process HDA
class GEN_OT_Process(bpy.types.Operator):
    """Process the generative model"""
    bl_idname = "gen.process"
    bl_label = "Process the generative model"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Only enable if connected and object has model_type and connected to backend
        obj = context.object
        is_connected = get_connection_state() == ConnState.CONNECTED
        return obj.get("model_type", None) and is_connected

    def execute(self, context):
        obj = context.object
        gen = obj.gen
        model_type = obj.get("model_type", None)
        assert model_type is not None
        props = get_model_props(gen, model_type)
        assert props is not None
        params = props.get_params()
        cook(obj, params)
        return {'FINISHED'}


# Operator to add input objects
class GEN_OT_AddInput(bpy.types.Operator):
    bl_idname = "gen.add_input"
    bl_label = "Add Input Object"
    bl_description = "Add selected object as an input"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if context.object is None:
            self.report({'WARNING'}, "No object selected")
            return {'CANCELLED'}
        
        input = context.object.gen.inputs.add()
        input.input_ref = getattr(self, 'input', None)
        input.input_type = 'MESH'
        input.enabled = input.input_ref is not None
                
        return {'FINISHED'}

class GEN_OT_AddInputInteractive(bpy.types.Operator):
    bl_idname = "gen.add_input_interactive"
    bl_label = "Add Inputs"
    bl_description = "Add Input Objects Interactively"
    bl_options = {'REGISTER', 'UNDO'}

    waiting_for_input: BoolProperty(default=True)
    
    def execute(self, context):
        if not self.waiting_for_input:
            # Process the selected objects
            selected_objects = context.selected_objects
            if not selected_objects:
                self.report({'WARNING'}, "No objects selected")
                return {'CANCELLED'}
            
            # Do something with the selected objects
            self.report({'INFO'}, f"Processing {len(selected_objects)} objects")
            
            # Example: Move selected objects up by 1 unit
            for obj in selected_objects:
                obj.location.z += 1.0
            
            return {'FINISHED'}
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        if event.type == 'SPACE' and event.value == 'PRESS':
            # User pressed space, confirm selection
            self.waiting_for_input = False
            return self.execute(context)
        
        elif event.type == 'ESC':
            # User cancelled
            self.report({'INFO'}, "Cancelled")
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        self.waiting_for_input = True
        self.report({'INFO'}, "Select objects and press SPACEBAR to confirm")
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


# Operator to remove input objects
class GEN_OT_RemoveInput(bpy.types.Operator):
    bl_idname = "gen.remove_input"
    bl_label = "Remove PCG Input"
    bl_description = "Remove selected PCG input"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        model_type = context.object.get("model_type", None)
        if not model_type:
            self.report({'WARNING'}, "Object has no `model_type` property")
            return {'CANCELLED'}
        
        last_index = len(context.object.gen.inputs) - 1
        context.object.gen.inputs.remove(last_index)
            
        return {'FINISHED'}


classes = (
    GEN_OT_AddToObject,
    GEN_OT_CreateModel,
    GEN_OT_Process,
    GEN_OT_InitParams,
    GEN_OT_AddInput,
    GEN_OT_AddInputInteractive,
    GEN_OT_RemoveInput)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)  # Unregister in reverse order


