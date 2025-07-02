import bpy
from .export_mesh_simple import export_mesh_simple

from .host.app import session_manager
from .host.models import GeometrySet
from .host.ops import Ops

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

            geometry.geometry[obj.name] = export_mesh_simple(obj.name, obj)

        # Send geometry to clients
        geometry_op = {
            "op": Ops.GEOMETRY.value,
            "data": geometry
        }
        for [_,session] in session_manager.sessions.items():
            print(f"sending geometry to {session.id}")
            session.broadcast(geometry_op)
            
