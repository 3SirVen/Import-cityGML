import os
import re
from xml.etree import ElementTree as et

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    FloatProperty,
)
from bpy_extras.io_utils import ImportHelper

bl_info = {
    "name": "Import cityGML",
    "description": "Import cityGML files",
    "author": "3SirVen",
    "version": (1, 0, 1),
    "blender": (4, 2, 0),
    "doc_url": "https://github.com/3SirVen/Import-cityGML",
    "support": "COMMUNITY",
    "category": "Import-Export",
}

# Constants
WALL_MATERIAL_COLOR = "#c9c9c9"
ROOF_MATERIAL_COLOR = "#a62f20"


def hex_to_rgba(hex_color):
    """Convert hex color to RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1.0,)


def convert_to_3d_coords(coords, scale, origin):
    """Convert flat coordinate list to 3D coordinates with scaling and origin adjustment."""
    return [
        (
            (coords[i] - origin[0]) * scale,
            (coords[i + 1] - origin[1]) * scale,
            (coords[i + 2] - origin[2]) * scale,
        )
        for i in range(0, len(coords), 3)
    ]


def process_faces(
    faces,
    face_type,
    max_coord,
    master_verts,
    extend_verts,
    append_faces,
    face_materials,
    scale,
    origin,
    separate_materials,
):
    """Add faces to the mesh."""
    for p in faces:
        pos_list = p.find(".//{http://www.opengis.net/gml}posList")
        if pos_list is not None:
            text_full = pos_list.text
        else:
            texts = [
                pos.text.strip()
                for pos in p.findall(".//{http://www.opengis.net/gml}pos")
            ]
            text_full = " ".join(texts)

        text_reduced = re.sub(
            " +", " ", re.sub("\t", " ", re.sub("\n", " ", text_full))
        ).strip()
        coords = [float(i) for i in text_reduced.split(" ")]

        max_v = max(coords)
        if max_v > max_coord:
            max_coord = max_v

        verts = convert_to_3d_coords(coords, scale, origin)

        start_idx = len(master_verts)
        end_idx = start_idx + len(verts)
        extend_verts(verts)
        append_faces([i for i in range(start_idx, end_idx)])

        if separate_materials:
            if "RoofSurface" in face_type:
                face_materials.append(1)  # Add only RoofSurface to roof material
            else:
                face_materials.append(0)  # Add everything else to wall material

    return max_coord


def main(filename, scale, origin, viewport, separate_materials, wall_mat, roof_mat):
    """Main function to import CityGML file and create Blender mesh."""
    tree = et.parse(filename)

    roof_surface = tree.findall(
        ".//{http://www.opengis.net/citygml/building/1.0}RoofSurface"
    )

    roof_polygons = [
        polygon
        for roof in roof_surface
        for polygon in roof.findall(".//{http://www.opengis.net/gml}Polygon")
    ]
    roof_triangles = [
        triangle
        for roof in roof_surface
        for triangle in roof.findall(".//{http://www.opengis.net/gml}Triangle")
    ]

    other_polygons = tree.findall(".//{http://www.opengis.net/gml}Polygon")
    other_triangles = tree.findall(".//{http://www.opengis.net/gml}Triangle")

    # Remove roof polygons and triangles from other polygons and triangles
    other_polygons = [op for op in other_polygons if op not in roof_polygons]
    other_triangles = [ot for ot in other_triangles if ot not in roof_triangles]

    roof_faces = roof_polygons + roof_triangles
    wall_faces = other_polygons + other_triangles

    master_verts = []
    master_faces = []
    face_materials = []
    extend_verts = master_verts.extend
    append_faces = master_faces.append

    max_coord = 1.0

    max_coord = process_faces(
        roof_faces,
        "RoofSurface",
        max_coord,
        master_verts,
        extend_verts,
        append_faces,
        face_materials,
        scale,
        origin,
        separate_materials,
    )
    max_coord = process_faces(
        wall_faces,
        "WallSurface",
        max_coord,
        master_verts,
        extend_verts,
        append_faces,
        face_materials,
        scale,
        origin,
        separate_materials,
    )

    ob_name = os.path.basename(filename)

    mesh = bpy.data.meshes.new(ob_name)
    mesh.from_pydata(master_verts, [], master_faces)
    mesh.update()

    obj = bpy.data.objects.new(ob_name, mesh)

    current_collection = bpy.context.collection
    current_collection.objects.link(obj)

    # Assign materials to the object
    obj.data.materials.append(wall_mat)
    obj.data.materials.append(roof_mat)

    # Assign materials to faces
    for i, face in enumerate(mesh.polygons):
        mat_index = face_materials[i]
        if mat_index != -1:
            face.material_index = mat_index

    if viewport:
        screen = bpy.context.screen
        for area in screen.areas:
            if area.type == "VIEW_3D":
                viewport = area
                break
        a = int((max_coord - min(origin[:])) * scale)
        b = len(str(a))
        c = 10**b
        while c < 100:
            c = 100
        viewport.spaces[0].clip_end = c * 10
        viewport.spaces[0].clip_start = c / 1000000


class CityGMLDirectorySelector(bpy.types.Operator, ImportHelper):
    """Operator to select and import CityGML files."""

    bl_idname = "import_create.citygml"
    bl_label = "Import cityGML file(s)"

    filename_ext = ".gml, .xml"
    use_filter_folder = True

    files: CollectionProperty(type=bpy.types.PropertyGroup)  # type: ignore
    scale: FloatProperty(
        name="Import Scale",
        description="1 for meters, 0.001 for kilometers",
        soft_min=0.0,
        soft_max=1.0,
        precision=3,
        default=0.1,
    )  # type: ignore
    origin_setting_x: FloatProperty(
        name="Origin Point X",
        description="X value from imported file to be 0",
        precision=1,
        default=0.0,
    )  # type: ignore
    origin_setting_y: FloatProperty(
        name="Origin Point Y",
        description="Y value from imported file to be 0",
        precision=1,
        default=0.0,
    )  # type: ignore
    origin_setting_z: FloatProperty(
        name="Origin Point Z",
        description="Z value from imported file to be 0",
        precision=1,
        default=0.0,
    )  # type: ignore
    viewport_setting: BoolProperty(
        name="Recalculate View Clip Start and End",
        description="Try to align start clip and end clip in current viewport based on objects size",
        default=False,
    )  # type: ignore
    separate_materials: BoolProperty(
        name="Separate Materials",
        description="Create separate materials for roof and walls. By default, the roof is red and walls are light gray. Note that only the Elements with the 'RoofSurface' tag will be assigned to the roof material. Everything else will be assigned to the wall material.",
        default=True,
    )  # type: ignore

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Origin Point (X,Y,Z):")
        row = box.row(align=True)
        row.prop(self, "origin_setting_x", text="X:")
        row = box.row(align=True)
        row.prop(self, "origin_setting_y", text="Y:")
        row = box.row(align=True)
        row.prop(self, "origin_setting_z", text="Z:")

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Import Scale:")
        row.prop(self, "scale", text="")

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Recalculate View Clips:")
        row.prop(self, "viewport_setting", text="")

        box = layout.box()
        row = box.row(align=True)
        row.label(text="Separate Materials:")
        row.prop(self, "separate_materials", text="")

    def execute(self, context):
        folder = os.path.dirname(self.filepath)
        wall_mat = bpy.data.materials.new(name="Wall_Material")
        wall_mat.diffuse_color = hex_to_rgba(WALL_MATERIAL_COLOR)  # Light gray color
        wall_mat.specular_intensity = 0.0
        wall_mat.roughness = 1

        roof_mat = bpy.data.materials.new(name="Roof_Material")
        roof_mat.diffuse_color = hex_to_rgba(ROOF_MATERIAL_COLOR)  # Red color
        roof_mat.specular_intensity = 0.0
        roof_mat.roughness = 1

        for i, file in enumerate(self.files):
            print(f"File {i + 1}/{len(self.files)}: {file.name}")
            path_to_file = os.path.join(folder, file.name)
            try:
                main(
                    filename=path_to_file,
                    scale=self.scale,
                    origin=(
                        self.origin_setting_x,
                        self.origin_setting_y,
                        self.origin_setting_z,
                    ),
                    viewport=self.viewport_setting,
                    separate_materials=self.separate_materials,
                    wall_mat=wall_mat,
                    roof_mat=roof_mat,
                )
                self.report({"INFO"}, f"{file.name} imported")
                print(f"{file.name} imported")
            except Exception as e:
                self.report({"ERROR"}, f"Error importing {file.name}: {e}")
                print(f"Error importing {file.name}: {e}")
        return {"FINISHED"}


def menu_import(self, context):
    self.layout.operator(CityGMLDirectorySelector.bl_idname, text="cityGML (.gml)")


def register():
    bpy.utils.register_class(CityGMLDirectorySelector)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.utils.unregister_class(CityGMLDirectorySelector)


if __name__ == "__main__":
    register()
