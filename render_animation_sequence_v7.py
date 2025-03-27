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
import json

CHARACTER_NAME = "character"

'''FIX 1. currently default scene is None, if it will be called none it will be ambigous whether its a scene or not
        2.  current value '0' matches no enum in 'RENDER_Props', '', 'track_name
        3. group in a way where scene 
        4. Store Settings before changing them
        5. remove solo from all tracks if any and remove if present Action from Active Action (edited action) (maybe first put a guard and then remove) turn off preview range if set
        6. move UP/Down render blocks
        7. copy settings from one to another with a button copy/paste
        8. Fold all button
        9. keep track name when rig selection is changed (if track name is set and new rig selection has same track, then keep it)
        10. add groups for render blocks (this is useful when there are a lot of similar render blocks such as same character name etc.)
        11. add button to automatically add all rig Tracks for the selected rig
        12. add button to update all render blocks for track length change and output name (currently it updates when we change/select track) and button to enable all or disable all blocks
        13. disable renders that are finished render or highlight the render that is currently rendering'''

'''1. First we select the scene name
   2. then we select the view layer 
   3. then we select Armature Or Camera
   4. then we select Track of the Armature'''

def get_collection_path(layer_collection, path=""):
    """ Recursively build the full path for a collection. """
    path = f"{path}/{layer_collection.collection.name}" if path else layer_collection.collection.name #include path/collection name (first item will be just collection name) 
    paths = {path: layer_collection.exclude} #collect exclude (collection visibility) (path: Boolean)
    for child in layer_collection.children:
        paths.update(get_collection_path(child, path))
    return paths

def set_collection_visibility(visibility_dict):
    """ Apply stored visibility states using full paths. """
    def restore_visibility(layer_collection, path=""):
        path = f"{path}/{layer_collection.collection.name}" if path else layer_collection.collection.name
        if path in visibility_dict:
            layer_collection.exclude = visibility_dict[path]
        for child in layer_collection.children:
            restore_visibility(child, path)

    restore_visibility(bpy.context.view_layer.layer_collection)

class CLEAR_OT_collection_visibility(bpy.types.Operator):
    """Clear collection visibility"""
    bl_idname = "view3d.clear_collection_visibility"
    bl_label = "Clear Collection Visibility"

    index: bpy.props.IntProperty() #index of the render block

    def execute(self, context):
        property = bpy.data.workspaces[0].render_panel_props[self.index]
        property.collection_visibility = ''
        self.report({'INFO'}, "Collection visibility cleared")
        return {'FINISHED'}
    
class STORE_OT_collection_visibility(bpy.types.Operator):
    """Store collection visibility"""
    bl_idname = "view3d.store_collection_visibility"
    bl_label = "Store Collection Visibility"

    index: bpy.props.IntProperty() #index of the render block

    def execute(self, context):
        property = bpy.data.workspaces[0].render_panel_props[self.index]
        property.collection_visibility = json.dumps(get_collection_path(bpy.context.view_layer.layer_collection))
        self.report({'INFO'}, "Collection visibility stored")
        return {'FINISHED'}

class RESTORE_OT_collection_visibility(bpy.types.Operator):
    """Restore collection visibility"""
    bl_idname = "view3d.restore_collection_visibility"
    bl_label = "Restore Collection Visibility"

    index: bpy.props.IntProperty() #index of the render block

    def execute(self, context):
        property = bpy.data.workspaces[0].render_panel_props[self.index]
        visibility_dict = json.loads(property.collection_visibility)
        set_collection_visibility(visibility_dict)
        self.report({'INFO'}, "Collection visibility restored")
        return {'FINISHED'}

def update_scene_list(self, context):
    scene_items = [(sc.name, sc.name, '') for sc in bpy.data.scenes]
    return scene_items

def update_view_list(self, context):
    scene_data = bpy.data.scenes.get(self.scene_name)
    if scene_data:
        view_items = [(layer.name, layer.name, '') for layer in scene_data.view_layers]
        return view_items
    return []

def update_armature_list(self, context):
    '''
    scene_data = bpy.data.scenes.get(self.scene_name)
    view_data = scene_data.view_layers.get(self.view_name) if scene_data else None
    if scene_data and view_data:
        armature_items = [(obj.name, obj.name, '') for obj in view_data.objects if obj.type == 'ARMATURE']
        return armature_items
    
    return []
    '''
    return [(obj.name, obj.name, '') for obj in bpy.data.objects if obj.type == 'ARMATURE']

def update_camera_list(self, context):
    '''
    scene_data = bpy.data.scenes.get(self.scene_name)
    view_data = scene_data.view_layers.get(self.view_name) if scene_data else None
    if scene_data and view_data:
        camera_items = [(obj.name, obj.name, '') for obj in view_data.objects if obj.type == 'CAMERA']
        camera_items.insert(0, ("NONE", "None", "No camera selected"))  # Add empty option
        return camera_items
    return []
    '''
    camera_items = [(obj.name, obj.name, '') for obj in bpy.data.objects if obj.type == 'CAMERA']
    camera_items.insert(0, ("NONE", "None", "No camera selected"))  # Add empty option
    return camera_items

def update_track_list(self, context):
    '''view_data = bpy.data.scenes[self.scene_name].view_layers.get(self.view_name) if bpy.data.scenes.get(self.scene_name) else None
    arm_data = view_data.objects.get(self.rig_name) if view_data else None
    if view_data and arm_data:
        if arm_data.animation_data and arm_data.animation_data.nla_tracks:
            track_items = [(trk.name, trk.name, '') for trk in arm_data.animation_data.nla_tracks] #check object not armature
            return track_items
    return []'''
    arm_data = bpy.data.objects.get(self.rig_name)
    if arm_data and arm_data.type == 'ARMATURE' and arm_data.animation_data and arm_data.animation_data.nla_tracks:
        return [(trk.name, trk.name, '') for trk in arm_data.animation_data.nla_tracks]
    return []

def update_time(self, context):
    update_output_folder(self, context) #update folder when track is changed
    #set start and end frames
    arm_data = bpy.data.objects.get(self.rig_name)
    track_index = arm_data.animation_data.nla_tracks.find(self.track_name) if arm_data and arm_data.animation_data and arm_data.animation_data.nla_tracks else None
    if track_index != None and track_index != -1:
        self.frame_start = int(bpy.data.objects[self.rig_name].animation_data.nla_tracks[self.track_name].strips[0].frame_start_ui)
        self.frame_end = int(bpy.data.objects[self.rig_name].animation_data.nla_tracks[self.track_name].strips[0].frame_end_ui) - 1 #minus one frame that is similar to the first frame

def update_output_folder(self, context):
    #format "{render\character_name\track_name\camera\}"
    #set output folder based on the context
    output = "//..\\render\\"

    #character
    match self.character_name:
        case '':
            pass
        case 'scene':
            output += f"{self.scene_name}\\"
        case 'view_layer':
            output += f"{self.view_name}\\"
        case _:
            output += f"{self.character_name}\\"
    #-track
    track_separated = self.track_name.split('_')
    if self.track_name:
        track_separated = self.track_name.split('_')
        cleaned_name = '_'.join([part for part in track_separated if part not in ['up', 'down']])
        output += f"{cleaned_name}\\"
    #--camera
    if self.cam_name == 'NONE':
        scene_separated = self.scene_name.split('_')
        view_separated = self.view_name.split('_')
        
        if 'up' in scene_separated or 'up' in view_separated or 'up' in track_separated:
                output += "up\\"
        elif 'down' in scene_separated or 'down' in view_separated or 'down' in track_separated:
                output += "down\\"
    else:
        output += f"{self.cam_name}\\"
        
    self.output_path = output

def update_enable_all(self, context):
    props = bpy.data.workspaces[0].render_panel_props
    if props and len(props)>0:
        for prop in props:
            if prop.enabled != self.render_enable_all:
                #copy enable from global enable boolean
                prop.enabled = self.render_enable_all
                print(f"Changed enable for {prop.track_name}")
def update_folded_all(self, context):
    props = bpy.data.workspaces[0].render_panel_props
    if props and len(props)>0:
        for prop in props:
            if prop.enabled:
                if prop.folded != self.render_folded_all:
                    #copy enable from global enable boolean
                    prop.folded = self.render_folded_all
                    print(f"Folded {prop.track_name}")

def form_render_text(self, property):
    #format "{character_name|track_name|camera}"
    #set output folder based on the context
    output = ""

    #character
    if property.character_name:
        output += f"{property.character_name}"
    #-track
    track_separated = property.track_name.split('_')
    if property.track_name:
        track_separated = property.track_name.split('_')
        cleaned_name = '_'.join([part for part in track_separated if part not in ['up', 'down']])
        output += f"|{cleaned_name}"
    #--camera
    if property.cam_name == 'NONE':
        scene_separated = property.scene_name.split('_')
        view_separated = property.view_name.split('_')
        
        if 'up' in scene_separated or 'up' in view_separated or 'up' in track_separated:
                output += "|up"
        elif 'down' in scene_separated or 'down' in view_separated or 'down' in track_separated:
                output += "|down"
    else:
        output += f"|{property.cam_name}"
        
    return output

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
    rig_name: bpy.props.EnumProperty(
        items=update_armature_list, 
        description="Armatures", 
        update=update_output_folder
    )
    character_name: bpy.props.StringProperty(
        description="Name of the Character",
        default=CHARACTER_NAME,
        update=update_output_folder
    )
    scene_name: bpy.props.EnumProperty(
        items=update_scene_list, 
        description="Scenes", 
        update=update_output_folder
    )
    view_name: bpy.props.EnumProperty(
        items=update_view_list, 
        description="View Layers", 
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
        update=update_time
    )
    frame_start: bpy.props.IntProperty(default=0, description="start:")
    frame_end: bpy.props.IntProperty(default=0, description="end:")
    output_path: bpy.props.StringProperty(
        description="Path to Directory",
        default="//..\\render\\",
        maxlen=1024,
        subtype='DIR_PATH')
    collection_visibility: bpy.props.StringProperty(
        description="Stored Collections Exclude parametr"
        )

class RENDER_PT(bpy.types.Panel):
    bl_idname = 'RENDER_PT'
    bl_label = 'Render Sequences'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'render'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        workspace = bpy.data.workspaces[0]
        properties = workspace.render_panel_props
        header = layout.row()
        #Utils | character name that is used to add all tracks
        header.prop(workspace, 'render_character_name')
        header.operator(RENDER_OT_AddAllTracks.bl_idname, text = "Add all tracks")
        header = layout.row()

        header.prop(workspace, 'render_fps')
        header = layout.row()
        #Global settings | update all tracks, fold or unfold all tracks, enable or disable tracks
        if len(properties) > 0:
            header.prop(workspace, 'render_enable_all')
            header.operator(RENDER_OT_UpdateTrackTime.bl_idname, text = "Update Time")
            header.operator(RENDER_OT_DeleteTracks.bl_idname, text = "Remove selected")
            header.prop(workspace, "render_folded_all", icon='DISCLOSURE_TRI_DOWN' if workspace.render_folded_all else 'DISCLOSURE_TRI_RIGHT')
        # Here you want to iterate over your properties and keep the index for the Delete button
        for i, prop in enumerate(properties):
            render_box = layout.box()
            header = render_box.row()
            header.prop(prop, "enabled")

            render_text = form_render_text(self, prop)
            header.label(text = f'Render {i + 1}|{render_text}')

            header.prop(prop, "folded", icon='DISCLOSURE_TRI_DOWN' if prop.folded else 'DISCLOSURE_TRI_RIGHT')

            if prop.folded:
                col = render_box.column()
                col.prop(prop, "character_name")
                col.label(text = "Store collection visibility:")
                row = col.row()
                row.operator(STORE_OT_collection_visibility.bl_idname, text = "Store").index=i
                
                if prop.collection_visibility and prop.collection_visibility != '':
                    row.operator(RESTORE_OT_collection_visibility.bl_idname, text = "Re-Store").index=i
                    row.alert = True
                    row.operator(CLEAR_OT_collection_visibility.bl_idname, text = "- remove -").index=i

                col.prop(prop, "scene_name")
                col.prop(prop, "view_name")
                col.prop(prop, "rig_name")
                col.prop(prop, "track_name")
                col.prop(prop, "cam_name")
                row = col.row()
                row.prop(prop, "frame_start")
                row.prop(prop, "frame_end")
                col.prop(prop, "output_path")
                #button delete
                col.alert = True
                row = col.row()
                row.operator(RENDER_OT_DeleteRender.bl_idname, text = "- remove -").index=i
                row.alert = False
                row.operator(RENDER_OT_DuplicateRender.bl_idname, text = "duplicate").index=i #duplicate
        #render button
        footer = layout.row()
        footer.operator('render.add_render', text = "Add")
        footer.operator(RENDER_SEQ_OT.bl_idname, text = "Render", icon='RENDER_ANIMATION')

class RENDER_OT_AddAllTracks(bpy.types.Operator):
    """Add all NLA tracks from the active armature"""
    bl_idname = "render.add_all_tracks"
    bl_label = "Add All Tracks of Active Armature"

    @classmethod
    def poll(cls, context):
        """Ensure an armature with NLA tracks is selected."""
        arm = context.active_object
        return (
            arm 
            and arm.type == 'ARMATURE' 
            and arm.animation_data 
            and len(arm.animation_data.nla_tracks) > 0
        )

    def execute(self, context):
        workspace = bpy.data.workspaces[0]
        props = workspace.render_panel_props  # Ensure this exists
        arm = context.active_object  # Get the active armature
        scene = context.scene.name
        view = context.view_layer.name

        existing_track_character_names = {prop.track_name: prop.character_name for prop in props}
        character_name = workspace.render_character_name

        if arm.animation_data and arm.animation_data.nla_tracks:
            #collect all collection visibiltiy
            collection_visibility = json.dumps(get_collection_path(bpy.context.view_layer.layer_collection))

            for track in arm.animation_data.nla_tracks:
                #if track name is in existing names and character name is not default CHARACTER_NAME
                if (track.name not in existing_track_character_names) or (existing_track_character_names[track.name] != character_name):
                    prop = props.add()
                    prop.character_name = character_name
                    prop.rig_name = arm.name
                    prop.scene_name = scene
                    prop.view_name = view
                    prop.track_name = track.name
                    prop.collection_visibility = collection_visibility
                    print(f"Added track: {track.name}")

        return {'FINISHED'}

class RENDER_OT_UpdateTrackTime(bpy.types.Operator):
    """ Update selected tracks"""
    bl_idname = "render.update_track_time"
    bl_label = "update selected tracks"

    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        if props and len(props)>0:
            for prop in props:
                if prop.enabled:
                    if prop.track_name:
                        #assign the same track name and it will call update frames function
                        old_name = prop.track_name
                        prop.track_name = old_name
                        print(f"Updated Times {prop.track_name}")
        return {'FINISHED'}

class RENDER_OT_DeleteTracks(bpy.types.Operator):
    """ delete selected tracks """
    bl_idname = "render.delete_tracks"
    bl_label = "delete selected tracks"

    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        #loop and delete only that prop that is enabled
        if props and len(props) > 0:
            for index in reversed(range(len(props))):  # Loop from last to first
                prop = props[index]
                if prop.enabled:
                    track_name = prop.track_name
                    props.remove(index)  # Safe removal
                    print(f"{track_name} is removed")
        return {'FINISHED'}

class RENDER_OT_AddRender(bpy.types.Operator):
    """ Create a new render with its sensor(s) and/or effector(s) """
    bl_idname = "render.add_render"
    bl_label = "Create new render"

    def execute(self, context):
        bpy.data.workspaces[0].render_panel_props.add()
        print(f"Added render")
        return {'FINISHED'}
    
class RENDER_OT_DeleteRender(bpy.types.Operator):
    """ Delete a render with its sensor(s) and/or effector(s) """
    bl_idname = "render.delete_render"
    bl_label = "Delete render"
    # We use an index here so we can delete a specific item from the list, not the last or first one
    index: bpy.props.IntProperty()

    def execute(self, context):
        bpy.data.workspaces[0].render_panel_props.remove(self.index)
        print(f"Removed {self.index} render")
        return {'FINISHED'}
#duplicate render
class RENDER_OT_DuplicateRender(bpy.types.Operator):
    bl_idname = "render.duplicate_render"
    bl_label = "Duplicate render"
    index: bpy.props.IntProperty()

    def execute(self, context):
        initial = bpy.data.workspaces[0].render_panel_props[self.index]
        duplicate = bpy.data.workspaces[0].render_panel_props.add()
        #copy properties from initial to duplicate
        for prop in initial.bl_rna.properties:
            prop_name = prop.name
            if hasattr(initial, prop_name):
                setattr(duplicate, prop_name, getattr(initial, prop_name))
        print(f"Duplicated {self.index} render")
        return {'FINISHED'}
    
class RENDER_SEQ_OT(bpy.types.Operator):
    bl_idname = "render.render_seq_operator"
    bl_label = "Render Sequence Operator"
    
    index = 0
    render_list = []
    stop = False
    rendering = False
    _timer = None
    
    def set_render_settings(self, rig_name, scene_name, cam_name, view_name, track_name, frame_start, frame_end, output_path, fps):
        
        # Get the scene by name
        scene = bpy.data.scenes.get(scene_name)
        if scene is None:
            print(f"Scene '{scene_name}' not found!")
            return False
        
        bpy.context.window.scene = scene

         # Get the view layer by name
        view = scene.view_layers.get(view_name)
        if view is None:
            print(f"View Layer '{view_name}' not found!")
            return False
        
        bpy.context.window.view_layer = view
        
        #set collection
        collection_visibility = self.render_list[self.index].collection_visibility
        if collection_visibility and collection_visibility != '':
            bpy.ops.view3d.restore_collection_visibility(index=self.index) #call restore collection vis operator'
                    
        # Get the armature object
        armature_obj = bpy.data.objects.get(rig_name)
        if armature_obj is None or armature_obj.type != 'ARMATURE':
            print("No armature selected!")
            return False
        
        track_index = armature_obj.animation_data.nla_tracks.find(track_name)
        if track_index == -1:
            print(f"Track '{track_name}' not found!")
            return False
        else:
            # Mute all tracks
            for track in armature_obj.animation_data.nla_tracks:
                track.mute = True
            # Activate the specified track
            armature_obj.animation_data.nla_tracks[track_index].mute = False
        
        #set the camera active
        cam_obj = bpy.data.objects.get(cam_name)
        if cam_obj and cam_obj.type == 'CAMERA':
            scene.camera = cam_obj

        # Set the render settings
        scene.frame_start = frame_start
        scene.frame_end = frame_end
        scene.render.fps = fps
        scene.render.use_file_extension = True
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.filepath = output_path
        
        # Additionally set compositor optional output paths if present
        if scene.node_tree and scene.node_tree.nodes and len(scene.node_tree.nodes) > 0:
            for node in [node for node in scene.node_tree.nodes if node.type == 'OUTPUT_FILE']:
                node.base_path = output_path
        

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
        # Unregister old handlers if they exist
        if self.pre in bpy.app.handlers.render_pre:
            bpy.app.handlers.render_pre.remove(self.pre)
        if self.complete in bpy.app.handlers.render_complete:
            bpy.app.handlers.render_complete.remove(self.complete)
        if self.canceled in bpy.app.handlers.render_cancel:
            bpy.app.handlers.render_cancel.remove(self.canceled)
        #set default params
        self.index = 0
        self.stop = False
        self.rendering = False
        self.props = props = bpy.data.workspaces[0]
        self.render_list = props.render_panel_props
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
            if self.index >= len(self.render_list) or self.stop:
                #render is done or canceled
                # Ensure handlers are removed before finishing
                if self.pre in bpy.app.handlers.render_pre:
                    bpy.app.handlers.render_pre.remove(self.pre)
                if self.complete in bpy.app.handlers.render_complete:
                    bpy.app.handlers.render_complete.remove(self.complete)
                if self.canceled in bpy.app.handlers.render_cancel:
                    bpy.app.handlers.render_cancel.remove(self.canceled)

                bpy.context.window_manager.event_timer_remove(self._timer)
                print("Nothing to Render!")
                return {'FINISHED'}
            
            elif not self.rendering:
                if self.render_list[self.index].enabled:
                    #set the render settings and render
                    render_data = self.render_list[self.index]
                    success = self.set_render_settings(
                        render_data.rig_name,
                        render_data.scene_name,
                        render_data.cam_name,
                        render_data.view_name,
                        render_data.track_name,
                        render_data.frame_start,
                        render_data.frame_end,
                        render_data.output_path,
                        self.prop.render_fps
                    )
                    
                    
                    if not success:
                        print("Please check the render settings")
                        return {'FINISHED'}
                    
                    print(f"Rendering: {render_data.rig_name}, {render_data.scene_name}, {render_data.cam_name}, {render_data.view_name}, {render_data.track_name}, {render_data.frame_start}, {render_data.frame_end}, {render_data.output_path}")
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
            RENDER_OT_DuplicateRender,
            RENDER_OT_UpdateTrackTime,
            RENDER_OT_DeleteTracks,
            RENDER_OT_AddAllTracks,
            RENDER_SEQ_OT,
            STORE_OT_collection_visibility,
            RESTORE_OT_collection_visibility,
            CLEAR_OT_collection_visibility,
        )
props = [
    "render_panel_props",
    "render_enable_all",
    "render_character_name",
    "render_folded_all",
    "render_fps"
]
        
def register():
    for my_class in classes:
        bpy.utils.register_class(my_class)
    bpy.types.WorkSpace.render_panel_props = bpy.props.CollectionProperty(type = RENDER_Props)
    bpy.types.WorkSpace.render_enable_all = bpy.props.BoolProperty(
        name="",
        default=False,
        update=update_enable_all
    )
    bpy.types.WorkSpace.render_character_name = bpy.props.StringProperty(
        name="character name",
        default=CHARACTER_NAME
    )
    bpy.types.WorkSpace.render_folded_all = bpy.props.BoolProperty(
        name="",
        default=True,
        update=update_folded_all
    )
    bpy.types.WorkSpace.render_fps = bpy.props.IntProperty(
        name="fps:",
        default=12,
    )
    
        
def unregister():
    for my_class in classes:
        bpy.utils.unregister_class(my_class)
    for prop in props:
        if hasattr(bpy.types.WorkSpace, prop):
            delattr(bpy.types.WorkSpace, prop)
            
if __name__ == '__main__':
    register()


#undo operation NLA turn off