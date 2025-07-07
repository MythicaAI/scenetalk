import bpy
from pydantic import BaseModel
from .async_wrap import run_async_bg
from .export_mesh_simple import export_mesh_simple

from .host.app import session_manager
from .host.models import GeometrySet, GeometryFlat
from .host.ops import Ops


class GeometryOp(BaseModel):
    op: Ops = Ops.GEOMETRY
    data: GeometrySet


def encode_scenetalk_geometry(mesh_data: dict) -> GeometryFlat:
    # Flatten indices from list of lists to single list, tessellating quads into triangles
    flat_indices = []
    for face_indices in mesh_data['indices']:
        if len(face_indices) == 3:
            flat_indices.extend(face_indices)
        elif len(face_indices) == 4:
            flat_indices.extend([face_indices[0], face_indices[1], face_indices[2]])
            flat_indices.extend([face_indices[0], face_indices[2], face_indices[3]])
        else:
            print(f"Warning: Unsupported face type: {len(face_indices)}")

    return GeometryFlat(
        points=mesh_data['vertices'],
        normals=mesh_data['normals'],
        uvs=mesh_data['uvs'],
        colors=mesh_data['colors'],
        indices=flat_indices
    )


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
            mesh_data = export_mesh_simple(obj.name, obj)
            geometry.geometry[obj.name] = encode_scenetalk_geometry(mesh_data)

        # Send geometry to clients
        geometry_op = GeometryOp(data=geometry)
        for [_,session] in session_manager.sessions.items():
            print(f"sending geometry to {session.id}")
            run_async_bg(session.broadcast(geometry_op)) 
            
