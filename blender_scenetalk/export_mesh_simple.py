import bmesh
import bpy

def export_mesh_simple(name, mesh_obj) -> object:
    # Ensure the object is a mesh
    if mesh_obj.type != 'MESH':
        print(f"Error: {mesh_obj.name} is not a mesh object.")
        return False
    
    # Get the evaluated mesh data (includes modifiers like geometry nodes)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = mesh_obj.evaluated_get(depsgraph)
    mesh = evaluated_obj.data
    
    # Create bmesh for easier access to data
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    
    # Initialize data structures
    data = {
        "name": name,
        "vertices": [],
        "normals": [],
        "colors": [],
        "uvs": [],
        "indices": []
    }
    
    # Get vertex data
    for v in bm.verts:
        data["vertices"].extend([v.co.x, v.co.y, v.co.z])
        data["normals"].extend([v.normal.x, v.normal.y, v.normal.z])
    
    # Get face indices
    for f in bm.faces:
        face_verts = [v.index for v in f.verts]
        data["indices"].append(face_verts)
    
    # Get UV data if available
    uv_layer = bm.loops.layers.uv.active
    if uv_layer:
        for face in bm.faces:
            for loop in face.loops:
                uv = loop[uv_layer].uv
                data["uvs"].extend([uv.x, uv.y])
    
    # Get vertex colors if available
    color_layer = bm.loops.layers.color.active
    if color_layer:
        for face in bm.faces:
            for loop in face.loops:
                color = loop[color_layer]
                data["colors"].extend([color.r, color.g, color.b, color.a])
    
    # Free bmesh
    bm.free()
    
    return data