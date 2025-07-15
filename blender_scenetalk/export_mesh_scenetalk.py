import bmesh
import bpy
from collections import defaultdict

from .host.models import GeometrySet, GeometryFlat


def export_mesh_scenetalk(name: str, mesh_obj) -> GeometrySet:
    if mesh_obj.type != 'MESH':
        print(f"Error: {mesh_obj.name} is not a mesh object.")
        return GeometrySet(geometry={})

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated_obj = mesh_obj.evaluated_get(depsgraph)
    mesh = evaluated_obj.data

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    bmesh.ops.triangulate(bm, faces=bm.faces[:])

    uv_layer = bm.loops.layers.uv.active
    color_layer = bm.loops.layers.color.active

    class PrimData:
        def __init__(self):
            self.points = []
            self.normals = []
            self.uvs = []
            self.colors = []
            self.indices = []
            self.vertex_map = {}
            self.next_index = 0

    primitives = defaultdict(PrimData)

    for face in bm.faces:
        mat_index = face.material_index
        # Group by material index, not name
        prim = primitives[mat_index]

        for loop in face.loops:
            v = loop.vert
            vid = v.index

            if vid not in prim.vertex_map:
                prim.vertex_map[vid] = prim.next_index
                prim.next_index += 1

                prim.points.extend([v.co.x, v.co.y, v.co.z])
                prim.normals.extend([v.normal.x, v.normal.y, v.normal.z])

                if uv_layer:
                    uv = loop[uv_layer].uv
                    prim.uvs.extend([uv.x, uv.y])
                if color_layer:
                    col = loop[color_layer]
                    prim.colors.extend([col.r, col.g, col.b, col.a])

            prim.indices.append(prim.vertex_map[vid])

    bm.free()

    # Name primitives to match GLB format: Mesh_primitive0, Mesh_primitive1, ...
    geometry_out = {}
    for i, (mat_index, prim) in enumerate(sorted(primitives.items())):
        prim_name = f"{name}_primitive{i}"
        geometry_out[prim_name] = GeometryFlat(
            points=prim.points,
            normals=prim.normals,
            uvs=prim.uvs,
            colors=prim.colors,
            indices=prim.indices
        )

    return GeometrySet(geometry=geometry_out)
