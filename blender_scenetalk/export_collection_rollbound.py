import bpy
from .export_mesh_simple import export_mesh_simple

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
        geometry = {}
        for obj in collection.objects:
            if obj.type != 'MESH':
                continue
            
            geometry[obj.name] = export_mesh_simple(obj.name, obj)

        print(f"geometry: {geometry}")

        # Send geometry to scenetalk


