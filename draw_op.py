import bpy
from bpy.types import Operator
from bpy_extras.view3d_utils import region_2d_to_location_3d

import bgl
import blf

import bmesh

import gpu
from gpu_extras.batch import batch_for_shader

class OT_draw_operator(Operator):
    bl_idname = "object.draw_op"
    bl_label = "Draw operator"
    bl_description = "Operator for drawing" 
    bl_options = {'REGISTER'}
    	
    def __init__(self):
        self.draw_handle_2d = None
        self.draw_handle_3d = None
        self.draw_event  = None

        self.vertices = []
        self.create_batch()
                
    def invoke(self, context, event):
        args = (self, context)                   
        self.register_handlers(args, context)
                   
        context.window_manager.modal_handler_add(self)
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
        
    def modal(self, context, event):
        if context.area:
            context.area.tag_redraw()
                
        if event.type in {"ESC"}:
            self.unregister_handlers(context)
            return {'CANCELLED'}
 
        if event.value == "PRESS":
            
            # Left mouse button pressed            
            if event.type == "LEFTMOUSE":
                x, y = event.mouse_region_x, event.mouse_region_y
                region = context.region
                rv3d = context.space_data.region_3d
    
                vec = region_2d_to_location_3d(region, rv3d, (x, y), (0, 0, 0))

                self.vertices.append(vec)

                self.create_batch()

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
        
        self.shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        self.batch = batch_for_shader(self.shader, 'LINE_STRIP', 
        {"pos": self.vertices})

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