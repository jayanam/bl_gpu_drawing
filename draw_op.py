import bpy
from bpy.types import Operator

import bgl
import blf

import bmesh

import gpu
from gpu_extras.batch import batch_for_shader

import mathutils
import math

from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_line_plane

from bpy_extras.view3d_utils import (
    region_2d_to_vector_3d,
    region_2d_to_origin_3d
)

class OT_draw_operator(Operator):
    bl_idname = "object.draw_op"
    bl_label = "Draw operator"
    bl_description = "Operator for drawing" 
    bl_options = {'REGISTER'}
    	
    def __init__(self):
        self.draw_handle_2d = None
        self.draw_handle_3d = None
        self.draw_event  = None
        self.mouse_vert = None
        self.offset = 0.02

        self.vertices = []
        self.create_batch()
                
    @classmethod
    def poll(cls, context):
        return (context.active_object is not None
            and context.active_object.mode == 'OBJECT')

    def invoke(self, context, event):
        args = (self, context)                   
        self.register_handlers(args, context)
                   
        context.window_manager.modal_handler_add(self)

        self.bvhtree = self.bvhtree_from_object(context, context.active_object)

        return {"RUNNING_MODAL"}
    
    def register_handlers(self, args, context):
        self.draw_handle_3d = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback_3d, args, "WINDOW", "POST_VIEW")

        self.draw_handle_2d = bpy.types.SpaceView3D.draw_handler_add(
            self.draw_callback_2d, args, "WINDOW", "POST_PIXEL")

        self.draw_event = context.window_manager.event_timer_add(0.1, window=context.window)
        
    def unregister_handlers(self, context):
        
        context.window_manager.event_timer_remove(self.draw_event)
        bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle_2d, "WINDOW")
        bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle_3d, "WINDOW")
        
        self.draw_handle_2d = None
        self.draw_handle_3d = None
        self.draw_event  = None
        self.bvhtree = None

    def bvhtree_from_object(self, context, object):
        bm = bmesh.new()

        depsgraph = context.evaluated_depsgraph_get()
        ob_eval = object.evaluated_get(depsgraph)
        mesh = ob_eval.to_mesh()

        bm.transform(object.matrix_world)

        bvhtree = BVHTree.FromBMesh(bm)
        ob_eval.to_mesh_clear()
        return bvhtree

    def get_origin_and_direction(self, event, context):
        region    = context.region
        region_3d = context.space_data.region_3d
        
        mouse_coord = (event.mouse_region_x, event.mouse_region_y)

        origin    = region_2d_to_origin_3d(region, region_3d, mouse_coord)
        direction = region_2d_to_vector_3d(region, region_3d, mouse_coord)

        return origin, direction

        
    def get_mouse_3d_on_mesh(self, event, context):
        
        origin, direction = self.get_origin_and_direction(event, context)

        self.hit, self.normal, *_ = self.bvhtree.ray_cast(origin, direction)
        if self.hit is not None:
            self.hit = self.hit + (self.normal * self.offset)

        return self.hit
    
    def get_mouse_3d_on_plane(self, event, context):
        
        origin, direction = self.get_origin_and_direction(event, context)
               
        # get the intersection point on infinite plane
        return intersect_line_plane(origin, origin + direction, 
        self.hit, self.normal)
        
            
    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()
                               
        if event.type in {"ESC"}:
            self.unregister_handlers(context)
            return {'CANCELLED'}
 
        if event.type == "MOUSEMOVE":
            
            if len(self.vertices) > 0:
                self.mouse_vert = self.get_mouse_3d_on_plane(event, context)
                self.create_batch()
        
        if event.value == "PRESS":
            
            # Left mouse button pressed            
            if event.type == "LEFTMOUSE":
                if len(self.vertices) == 0:
                    vertex = self.get_mouse_3d_on_mesh(event, context)
                else:
                    vertex = self.get_mouse_3d_on_plane(event, context)

                if vertex is not None: 
                    self.vertices.append(vertex)
                    self.create_batch()

                return {"RUNNING_MODAL"}

            # Return (Enter) key is pressed
            if event.type == "RET":
                self.create_object()
                self.unregister_handlers(context)
                return {'CANCELLED'}
                    
        return {"PASS_THROUGH"}

    def create_object(self):

        # Create a mesh and an object and 
        # add the object to the scene collection
        mesh = bpy.data.meshes.new("MyMesh")
        obj  = bpy.data.objects.new("MyObject", mesh)

        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj

        bpy.ops.object.select_all(action='DESELECT')
    
        obj.select_set(state=True)
        
        # Create a bmesh and add the vertices
        # added with mouse clicks
        bm = bmesh.new()

        for v in self.vertices:
            bm.verts.new(v)

        bm.to_mesh(mesh)  
        bm.free()

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        bpy.ops.mesh.edge_face_add()

        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY')

    def finish(self):
        self.unregister_handlers(context)
        return {"FINISHED"}

    def create_batch(self):
        
        points = self.vertices.copy()
        
        if self.mouse_vert is not None:
            points.append(self.mouse_vert)
                    
        self.shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        self.batch = batch_for_shader(self.shader, 'LINE_LOOP', 
        {"pos": points})

	# Draw handler to paint in pixels
    def draw_callback_2d(self, op, context):
        # Draw text to indicate that draw mode is active
        region = context.region
        text = "- Draw mode active -"
        subtext = "Esc : Close | Enter : Create"

        xt = int(region.width / 2.0)
        
        blf.size(0, 24, 72)
        blf.position(0, xt - blf.dimensions(0, text)[0] / 2, 60 , 0)
        blf.draw(0, text) 

        blf.size(1, 20, 72)
        blf.position(1, xt - blf.dimensions(0, subtext)[0] / 2, 30 , 1)
        blf.draw(1, subtext) 

	# Draw handler to paint onto the screen
    def draw_callback_3d(self, op, context):

        # Draw lines
        bgl.glLineWidth(5)
        self.shader.bind()
        self.shader.uniform_float("color", (0.1, 0.3, 0.7, 1.0))
        self.batch.draw(self.shader)