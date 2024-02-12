bl_info = {
    "name": "Render Sequences",
    "author": "Mikhail Lebedev",
    "version": (1, 0, 0),
    "blender": (3, 6, 5),
    "location": "3d Viewport > Animation Panel",
    "description": "Render sequences of animation",
    "category": "Animation",
}
    
import bpy

def update_armature_list(self, context):
    armature_items = [(obj.name, obj.name, '') for obj in bpy.data.scenes[self.scene_name].objects if obj.type == 'ARMATURE']
    return armature_items

def update_scene_list(self, context):
    scene_items = [(sc.name, sc.name, '') for sc in bpy.data.scenes]
    return scene_items

def update_camera_list(self, context):
    camera_items = [(obj.name, obj.name, '') for obj in bpy.data.objects if obj.type == 'CAMERA']
    return camera_items

def update_track_list(self, context):
    arm_name = self.rig_name
    track_items = []
    if arm_name and bpy.data.objects[arm_name].animation_data and bpy.data.objects[arm_name].animation_data.nla_tracks:
        track_items = [(trk.name, trk.name, '') for trk in bpy.data.objects[arm_name].animation_data.nla_tracks] #check object not armature 
    return track_items

def update_output_folder(self, context):
    #set output folder based on the context
    output = "//..\\render\\"
    '''if self.character_name:
        output += f"{self.character_name}\\"'''
    if self.scene_name:
        output += f"{self.scene_name}\\"
    if self.track_name:
        output += f"{self.track_name}\\"
    if self.cam_name:
        output += f"{self.cam_name}\\"
        
    self.output_path = output
    
    #set start and end frames
    if self.track_name:
        self.frame_start = int(bpy.data.objects[self.rig_name].animation_data.nla_tracks[self.track_name].strips[0].frame_start_ui)
        self.frame_end = int(bpy.data.objects[self.rig_name].animation_data.nla_tracks[self.track_name].strips[0].frame_end_ui)

class RENDER_Props(bpy.types.PropertyGroup):
    
    folded: bpy.props.BoolProperty(
        name="",
        default=True
    )
    enabled: bpy.props.BoolProperty( 
        name="",
        description="Enable Render Layer",
        default=True
    )
    '''character_name: bpy.props.StringProperty(
        name="character_name",
        description="Used in the folder structure",
        update=update_output_folder
    )'''
    rig_name: bpy.props.EnumProperty(
        items=update_armature_list, 
        description="Armatures", 
        update=update_output_folder
    )
    scene_name: bpy.props.EnumProperty(
        items=update_scene_list, 
        description="Scenes", 
        update=update_output_folder
    )
    cam_name: bpy.props.EnumProperty(
        items=update_camera_list, 
        description="Cameras", 
        update=update_output_folder
    )
    track_name: bpy.props.EnumProperty(
        items=update_track_list, 
        description="Actions", 
        update=update_output_folder
    )
    frame_start: bpy.props.IntProperty(default=0, description="start:")
    frame_end: bpy.props.IntProperty(default=0, description="end:")
    output_path: bpy.props.StringProperty(
        description="Path to Directory",
        default="//..\\render\\",
        maxlen=1024,
        subtype='DIR_PATH')

class RENDER_PT(bpy.types.Panel):
    bl_idname = 'RENDER_PT'
    bl_label = 'Render Sequences'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'render'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        
        add_button= layout.row()
        add_button.operator('render.add_render', text = "Add")

        
        # Here you want to iterate over your properties and keep the index for the Delete button
        properties = bpy.data.workspaces[0].render_panel_props
        for i, prop in enumerate(properties):
            render_box = layout.box()
            header = render_box.row()
            header.prop(prop, "enabled")
            header.label(text = f'Render {i + 1}')
            header.label(text = properties[i].output_path)
            header.prop(prop, "folded", icon='DISCLOSURE_TRI_DOWN' if prop.folded else 'DISCLOSURE_TRI_RIGHT')
            if prop.folded:
                col = render_box.column()
                #col.prop(prop, "character_name")
                col.prop(prop, "scene_name")
                col.prop(prop, "rig_name")
                col.prop(prop, "cam_name")
                col.prop(prop, "track_name")
                row = col.row()
                row.prop(prop, "frame_start")
                row.prop(prop, "frame_end")
                col.prop(prop, "output_path")
                #button delete
                col.alert = True
                col.operator('render.delete_render', text = "-").index=i
        #render button
        render_button = layout.row()
        render_button.operator('render.render_seq_operator', text = "Render", icon='RENDER_ANIMATION')

class RENDER_OT_AddRender(bpy.types.Operator):
    """ Create a new render with its sensor(s) and/or effector(s) """
    bl_idname = "render.add_render"
    bl_label = "Create new render"

    def execute(self, context):
        bpy.data.workspaces[0].render_panel_props.add()
        return {'FINISHED'}
    
class RENDER_OT_DeleteRender(bpy.types.Operator):
    """ Delete a render with its sensor(s) and/or effector(s) """
    bl_idname = "render.delete_render"
    bl_label = "Delete render"
    # We use an index here so we can delete a specific item from the list, not the last or first one
    index: bpy.props.IntProperty()

    def execute(self, context):
        bpy.data.workspaces[0].render_panel_props.remove(self.index)
        return {'FINISHED'}

class RENDER_SEQ_OT(bpy.types.Operator):
    bl_idname = "render.render_seq_operator"
    bl_label = "Render Sequence Operator"
    
    index = 0
    render_list = []
    stop = False
    rendering = False
    _timer = None
    
    def set_render_settings(self, rig_name, scene_name, cam_name, track_name, frame_start, frame_end, output_path):
        # Get the armature object
        if not rig_name:
            print("No armature selected!")
            return False
        
        armature_obj = bpy.data.objects[rig_name]
        if armature_obj.type != 'ARMATURE':
            print("Selected object is not an armature!")
            return False
            
        # Get the scene by name
        scene = bpy.data.scenes.get(scene_name)
        if scene is None:
            print(f"Scene '{scene_name}' not found!")
            return False

        # Set the current scene
        if(scene_name):
            bpy.context.window.scene = scene

        if (track_name):
            # Mute all tracks
            for track in armature_obj.animation_data.nla_tracks:
                track.mute = True

            # Activate the specified track
            track_index = armature_obj.animation_data.nla_tracks.find(track_name)
            if track_index == -1:
                print(f"Track '{track_name}' not found!")
                return False

            armature_obj.animation_data.nla_tracks[track_index].mute = False
        
        #set the camera active
        if(cam_name):
            cam_obj = bpy.data.objects[cam_name]
            if cam_obj.type != 'CAMERA':
                print("Selected object is not a camera!")
                return False
            bpy.context.scene.camera = cam_obj
        else:
            print("No camera in the scene!")
            return False
        

        # Set the render frame range
        bpy.context.scene.frame_start = frame_start
        bpy.context.scene.frame_end = frame_end
        #bpy.context.scene.cycles.samples = samples
        bpy.context.scene.render.fps = 12
        bpy.context.scene.render.use_file_extension = True
        bpy.context.scene.render.image_settings.color_mode = 'RGBA'

        # Set the render output path
        bpy.context.scene.render.filepath = output_path
        return True #everything is set up corectly 
    
    def pre(self, scene, context=None):
        self.rendering = True
        
    def complete(self, scene, context=None):
        self.index += 1
        self.rendering = False
        
        
    def canceled(self, scene, context=None):
        self.stop = True
    
    def execute(self, context):
        #set default params
        self.index = 0
        self.stop = False
        self.rendering = False
        self.render_list = bpy.data.workspaces[0].render_panel_props
        #append threads
        bpy.app.handlers.render_pre.append(self.pre)
        bpy.app.handlers.render_complete.append(self.complete)
        bpy.app.handlers.render_cancel.append(self.canceled)
        #add timer
        self._timer = bpy.context.window_manager.event_timer_add(0.5, window=context.window)
        #add modal
        context.window_manager.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
        
    def modal(self, context, event):
        if event.type == 'TIMER':
            if True in (self.index >= len(self.render_list), self.stop is True):
                #render is done or canceled
                #removing all threads and timers
                bpy.app.handlers.render_pre.remove(self.pre)
                bpy.app.handlers.render_complete.remove(self.complete)
                bpy.app.handlers.render_cancel.remove(self.canceled)
                bpy.context.window_manager.event_timer_remove(self._timer)
                print("Nothing to Render!")
                return {'FINISHED'}
            elif self.rendering is False:
                if self.render_list[self.index].enabled:
                    #set the render settings and render
                    rig_name = self.render_list[self.index].rig_name
                    scene_name = self.render_list[self.index].scene_name
                    cam_name = self.render_list[self.index].cam_name
                    track_name = self.render_list[self.index].track_name
                    frame_start = self.render_list[self.index].frame_start
                    frame_end = self.render_list[self.index].frame_end
                    output_path = self.render_list[self.index].output_path
                    
                    if self.set_render_settings(rig_name, scene_name, cam_name, track_name, frame_start, frame_end, output_path) is False:
                        print("please check the render settings")
                        return {'FINISHED'}
                    
                    print(f"Currently rendering:{rig_name},{scene_name}, {cam_name}, {track_name}, {frame_start}, {frame_end}, {output_path}")
                    # Call another instance of render with animation
                    bpy.ops.render.render('INVOKE_DEFAULT', animation=True, write_still=True)
                else:
                    self.index += 1

        return {'PASS_THROUGH'}

classes = (
            RENDER_Props,
            RENDER_PT,
            RENDER_OT_AddRender,
            RENDER_OT_DeleteRender,
            RENDER_SEQ_OT
        )
        
def register():
    for my_class in classes:
        bpy.utils.register_class(my_class)
    # We only need a single collection property after all.
    bpy.types.WorkSpace.render_panel_props = bpy.props.CollectionProperty(type = RENDER_Props)
        
def unregister():
    for my_class in classes:
        bpy.utils.unregister_class(my_class)
            
if __name__ == '__main__':
    register()


#undo operation NLA turn off