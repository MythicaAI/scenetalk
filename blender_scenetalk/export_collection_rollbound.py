import bpy
from pydantic import BaseModel
from .async_wrap import run_async_bg
from .export_mesh_scenetalk import export_mesh_scenetalk

from .host.app import session_manager
from .host.models import GeometrySet, GeometryFlat
from .host.ops import Ops


class GeometryOp(BaseModel):
    op: Ops = Ops.GEOMETRY
    data: GeometrySet


def export_collection_rollbound():
    """
    """
    print("Attempting to export collection to scenetalk...")

    # Loop through all collections in the scene
    for collection in bpy.data.collections:
        # Check if this collection is marked for export
        export_enabled = collection.get("export_scenetalk", False)

        if not export_enabled:
            #print(f"Skipping collection (export disabled): {collection.name}")
            continue

        # Skip empty collections
        if not collection.objects:
            print(f"Skipping empty collection: {collection.name}")
            continue
                
        print(f"exporting collection: {collection.name}")

        # Serialize objects to geometry
        geometry = GeometrySet(geometry={})
        for obj in collection.objects:
            if obj.type != 'MESH':
                continue

            object_geometry = export_mesh_scenetalk(obj.name, obj)
            geometry.geometry.update(object_geometry.geometry)

        # Send geometry to clients
        geometry_op = GeometryOp(data=geometry)
        for [_,session] in session_manager.sessions.items():
            print(f"sending geometry to {session.id}")
            run_async_bg(session.broadcast(geometry_op)) 
            
