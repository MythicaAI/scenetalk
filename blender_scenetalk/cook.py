from blender_scenetalk.scenetalk_client import CookRequest
import bpy

import json
import os
import secrets
import string
import logging

from tempfile import TemporaryDirectory
import threading
import time

from .async_wrap import run_async_bg
from .scenetalk_connection import get_client
from .model_db import find_by_name
from .selection import save_and_restore_selection

logger = logging.getLogger("cook")


_export_dir = TemporaryDirectory()

# Global variables to handle debouncing
_timer = None
_last_update_time = 0
_debounce_delay = 0.1  # Delay in seconds
_pending_value = None
_update_lock = threading.Lock()

def cook(obj, params):
    global _last_update_time, _pending_value, _timer

    assert obj.gen
    obj.gen.status = 'cooking'

    # Store the current value
    with _update_lock:
        _pending_value = (obj, params,)
        _last_update_time = time.time()
    
        # If no timer is running, start one
        if _timer is None:
            _timer = threading.Timer(_debounce_delay, cook_timer)
            _timer.start()


def cook_timer():
    global _timer, _pending_value, _last_update_time
    
    logger.info("cook timer")

    current_time = time.time()
    def reschedule():
        # Not enough time has passed, restart the timer
        _timer = threading.Timer(_debounce_delay, cook_timer)
        _timer.start()

    with _update_lock:
        # Check if enough time has passed since the last update
        if current_time - _last_update_time >= _debounce_delay:
            # Time has passed, send the request with the latest value
            obj, params = _pending_value
            if obj.get("model_type", None) is None:
                logger.error("Object %s has no model_type", obj.name)
                _timer = None
                return
            
            # Object is still cooking, reschedule for when it's ready to cook again
            # if obj.gen.status == "cooking":
            #     reschedule()
            #     return
            
            # Swap out pending value
            _pending_value = None
            _timer = None
            
            # Execute in the main thread to avoid object data threading issues
            bpy.app.timers.register(
                lambda: cook_internal(obj, params),
                first_interval=0.0)
        else:
            reschedule()


@save_and_restore_selection
def export_objects_for_huodini_input(file_type, objects):
    global _export_dir

    for obj in objects:
        obj.select_set(True)

    export_directory = bpy.context.scene.scenetalk_props.export_directory
    if not export_directory or not os.path.exists(export_directory):
        export_directory = _export_dir.name
        bpy.context.scene.scenetalk_props.export_directory = export_directory

    if file_type.startswith('usd'):
        export_path = os.path.join(export_directory, obj.name + "." + file_type)
        bpy.ops.wm.usd_export(
            filepath=export_path,
            selected_objects_only=True,
            export_materials=True,
            custom_properties_namespace="Attributes",
            convert_orientation=True,
            export_global_forward_selection="NEGATIVE_Z",
            export_global_up_selection="Y",
        )
    elif file_type == 'fbx':
        export_path = os.path.join(export_directory, obj.name + ".fbx")
        bpy.ops.export_scene.fbx(
            filepath=export_path,
            check_existing=False,
            use_selection=True,
            use_active_collection=True,
            apply_scale_options='FBX_SCALE_ALL',
            bake_space_transform=True,
            object_types={'MESH'},
            add_leaf_bones=False,
            mesh_smooth_type='FACE',
            colors_type='SRGB',
            axis_up='Y',
            axis_forward='-Z')
    file_id = 'file_' + ''.join(secrets.choice(string.ascii_lowercase) for i in range(10))
    logger.info("exported %s objects to %s: %s", len(objects), file_id, export_path)
    return file_id, export_path


def cook_internal(obj, params):
    client = get_client()
    assert client is not None
    assert obj is not None
    
    model_type = obj.get("model_type", None)
    if model_type is None:
        logger.error("Object has no `model_type`")
        return

    obj.gen.params_json = json.dumps(params)

    schema = find_by_name(model_type)
    if not schema:
        logger.error("Schema not found for %s", model_type)
        return
    
    default_params = schema["parameters"]

    # TODO: collect object inputs
    # TODO: cache file ID on the input ref, only recalculate if 'cook' action
    # is invoked, otherwise continue passing same file_id
    inputs = obj.gen.inputs
    object_inputs = []
    file_inputs = [(name, param['file_type']) for name, param in default_params.items() \
                   if param.get('file_type', None)]
    assert len(file_inputs) < 2  # TODO: support multiple file inputs
    if len(inputs) > 0 and len(file_inputs) > 0:
        for i in inputs:
            if i.input_ref is None:
                continue
            object_inputs.append(i.input_ref)
        param_name, file_type = file_inputs[0]
        file_id, file_path = export_objects_for_huodini_input(file_type, object_inputs) 
        run_async_bg(client.upload_file(file_id, file_path, f'application/{file_type}'))
        params[param_name] = { 'file_id': file_id }

    # Extract the default parameters, override with user supplied params
    all_params = {param_id: param["default"]
                for param_id, param in default_params.items()}
    all_params.update(params)
    req = CookRequest(
            model_type=model_type,
            obj_name=obj.name,
            object_inputs=object_inputs,
            params=params
        )
    run_async_bg(client.send_cook(req))
    

def update_float_value(self, context):
    cook(context.object, self.get_params())

def update_int_value(self, context):
    cook(context.object, self.get_params())

def update_bool_value(self, context):
    cook(context.object, self.get_params())

def update_string_value(self, context):
    cook(context.object, self.get_params())