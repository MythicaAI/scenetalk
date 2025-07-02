import bpy

def export_collection_rollbound():
    """
    """
    exported_count = 0
    
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
        
        # Create filename using only the collection name
        safe_collection_name = "".join(c for c in collection.name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        

        # Export selected objects as GLTF
        try:
            print("exporting colllection to scenetalk...")
            for obj in collection.objects:
                print("exporting object: ", obj.name)
            # bpy.ops.export_scene.gltf(
            #     filepath=filepath,
            #     use_selection=True,  # Only export selected objects
            #     export_apply=True    # Apply modifiers before export
            # )
            # print(f"Exported collection '{collection.name}' to: {filepath}")
            exported_count += 1
            
        except Exception as e:
            print(f"Failed to export collection '{collection.name}': {str(e)}")
