bl_info = {
    "name": "Render Sequences",
    "author": "Mikhail Lebedev",
    "version": (1, 4, 5),
    "blender": (4, 0, 0),
    "location": "3d Viewport > Animation Panel",
    "description": "Render sequences of animation with bulk reordering and undo support",
    "category": "Animation",
}
    
import bpy
import json
import os

CHARACTER_NAME = "character"

# --- GLOBAL CACHE FOR ENUMS (PREVENTS MEMORY CORRUPTION/UTF-8 ERRORS) ---
enum_cache = {}

def get_rig_items(self, context):
    enum_cache['rigs'] = [(o.name, o.name, '') for o in bpy.data.objects if o.type == 'ARMATURE']
    if not enum_cache['rigs']: enum_cache['rigs'] = [("NONE", "None", "")]
    return enum_cache['rigs']

def get_scene_items(self, context):
    enum_cache['scenes'] = [(sc.name, sc.name, '') for sc in bpy.data.scenes]
    if not enum_cache['scenes']: enum_cache['scenes'] = [("NONE", "None", "")]
    return enum_cache['scenes']

def get_view_items(self, context):
    sc = bpy.data.scenes.get(self.scene_name)
    if sc:
        enum_cache[f'views_{self.scene_name}'] = [(l.name, l.name, '') for l in sc.view_layers]
        return enum_cache[f'views_{self.scene_name}']
    enum_cache['views_none'] = [("NONE", "None", "")]
    return enum_cache['views_none']

def get_cam_items(self, context):
    enum_cache['cams'] = [("NONE", "None", "")] + [(o.name, o.name, '') for o in bpy.data.objects if o.type == 'CAMERA']
    return enum_cache['cams']

def get_track_items(self, context):
    arm = bpy.data.objects.get(self.rig_name)
    if arm and arm.animation_data and arm.animation_data.nla_tracks:
        enum_cache[f'tracks_{self.rig_name}'] = [(t.name, t.name, '') for t in arm.animation_data.nla_tracks]
        return enum_cache[f'tracks_{self.rig_name}']
    enum_cache['tracks_none'] = [("NONE", "None", "")]
    return enum_cache['tracks_none']


# --- HELPERS ---

def copy_render_props(source, target):
    """Safely copies properties, ignoring strict Enum validation errors."""
    for prop in source.bl_rna.properties:
        if prop.is_readonly or prop.identifier == 'rna_type':
            continue
        try:
            setattr(target, prop.identifier, getattr(source, prop.identifier))
        except TypeError:
            pass # Ignore if enum is uninitialized ("")

def get_collection_path(layer_collection, path=""):
    path = f"{path}/{layer_collection.collection.name}" if path else layer_collection.collection.name 
    paths = {path: layer_collection.exclude} 
    for child in layer_collection.children:
        paths.update(get_collection_path(child, path))
    return paths

def set_collection_visibility(visibility_dict):
    def restore_visibility(layer_collection, path=""):
        path = f"{path}/{layer_collection.collection.name}" if path else layer_collection.collection.name
        if path in visibility_dict:
            layer_collection.exclude = visibility_dict[path]
        for child in layer_collection.children:
            restore_visibility(child, path)

    restore_visibility(bpy.context.view_layer.layer_collection)

def get_rendered_status(render_list):
    finished = []
    valid_exts = {'.png', '.jpg', '.jpeg', '.exr', '.bmp', '.tif', '.tiff', '.tga'}
    
    for i, prop in enumerate(render_list):
        expected = prop.frame_end - prop.frame_start + 1
        if expected <= 0: continue
            
        abs_path = bpy.path.abspath(prop.output_path)
        if not os.path.exists(abs_path): continue
            
        count = 0
        try:
            for f in os.listdir(abs_path):
                if os.path.isfile(os.path.join(abs_path, f)):
                    ext = os.path.splitext(f)[1].lower()
                    if ext in valid_exts:
                        count += 1
        except Exception:
            pass
            
        if count >= expected:
            finished.append(i)
            
    return finished

# --- PROPERTY UPDATES ---

def update_time(self, context):
    update_output_folder(self, context) 
    if self.track_name == "NONE": return
    arm_data = bpy.data.objects.get(self.rig_name)
    track_index = arm_data.animation_data.nla_tracks.find(self.track_name) if arm_data and arm_data.animation_data and arm_data.animation_data.nla_tracks else None
    if track_index is not None and track_index != -1:
        self.frame_start = int(bpy.data.objects[self.rig_name].animation_data.nla_tracks[self.track_name].strips[0].frame_start_ui)
        self.frame_end = int(bpy.data.objects[self.rig_name].animation_data.nla_tracks[self.track_name].strips[0].frame_end_ui) - 1 

def update_output_folder(self, context):
    output = "//..\\render\\"
    
    def split_parts(name):
        return name.split('_') if name else []
    
    match self.character_name:
        case '': pass
        case 'scene': output += f"{self.scene_name}\\"
        case 'view_layer': output += f"{self.view_name}\\"
        case _: output += f"{self.character_name}\\"
            
    track_parts = []
    if self.track_name and self.track_name != "NONE":
        track_parts = split_parts(self.track_name)
        cleaned_name = '_'.join([part for part in track_parts if part.lower() not in ['up', 'down']])
        output += f"{cleaned_name}\\"
        
    combined_names = "".join([
        self.cam_name if self.cam_name and self.cam_name != "NONE" else "",
        self.scene_name if self.scene_name and self.scene_name != "NONE" else "",
        self.view_name if self.view_name and self.view_name != "NONE" else "",
        self.track_name if self.track_name and self.track_name != "NONE" else ""
    ]).lower()
    
    if "up" in combined_names: output += "up\\"
    elif "down" in combined_names: output += "down\\"
        
    self.output_path = output

def update_enable_all(self, context):
    props = bpy.data.workspaces[0].render_panel_props
    if props and len(props) > 0:
        for prop in props:
            if prop.enabled != self.render_enable_all:
                prop.enabled = self.render_enable_all

def update_folded_all(self, context):
    props = bpy.data.workspaces[0].render_panel_props
    if props and len(props) > 0:
        for prop in props:
            if prop.enabled:
                if prop.folded != self.render_folded_all:
                    prop.folded = self.render_folded_all

def form_render_text(self, property):
    output = ""
    match property.character_name:
        case '': pass
        case 'scene': output += f"{property.scene_name}\\"
        case 'view_layer': output += f"{property.view_name}\\"
        case _: output += f"{property.character_name}"
            
    if property.track_name and property.track_name != "NONE":
        track_separated = property.track_name.split('_')
        cleaned_name = '_'.join([part for part in track_separated if part not in ['up', 'down']])
        output += f"|{cleaned_name}"
        
    name_parts = property.output_path.split('\\') if property.output_path else []
    if 'up' in name_parts: output += "|up"
    elif 'down' in name_parts: output += "|down"
        
    return output

# --- DATA STRUCTURE ---

class RENDER_Props(bpy.types.PropertyGroup):
    folded: bpy.props.BoolProperty(name="", default=True)
    enabled: bpy.props.BoolProperty(name="", description="Enable Render Layer", default=True)
    rig_name: bpy.props.EnumProperty(items=get_rig_items, description="Armatures", update=update_output_folder)
    character_name: bpy.props.StringProperty(description="Name of the Character", default=CHARACTER_NAME, update=update_output_folder)
    scene_name: bpy.props.EnumProperty(items=get_scene_items, description="Scenes", update=update_output_folder)
    view_name: bpy.props.EnumProperty(items=get_view_items, description="View Layers", update=update_output_folder)
    cam_name: bpy.props.EnumProperty(items=get_cam_items, description="Cameras", update=update_output_folder)
    track_name: bpy.props.EnumProperty(items=get_track_items, description="Actions", update=update_time)
    frame_start: bpy.props.IntProperty(default=0, description="start:")
    frame_end: bpy.props.IntProperty(default=0, description="end:")
    output_path: bpy.props.StringProperty(description="Path to Directory", default="//..\\render\\", maxlen=1024, subtype='DIR_PATH')
    collection_visibility: bpy.props.StringProperty(description="Stored Collections Exclude parametr")


# --- OPERATORS ---

class CLEAR_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.clear_collection_visibility"
    bl_label = "Clear Collection Visibility"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty()
    def execute(self, context):
        property = bpy.data.workspaces[0].render_panel_props[self.index]
        property.collection_visibility = ''
        return {'FINISHED'}
    
class STORE_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.store_collection_visibility"
    bl_label = "Store Collection Visibility"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty()
    def execute(self, context):
        property = bpy.data.workspaces[0].render_panel_props[self.index]
        property.collection_visibility = json.dumps(get_collection_path(bpy.context.view_layer.layer_collection))
        return {'FINISHED'}

class RESTORE_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.restore_collection_visibility"
    bl_label = "Restore Properties"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty() 
    def execute(self, context):
        property = bpy.data.workspaces[0].render_panel_props[self.index]
        
        scene = bpy.data.scenes.get(property.scene_name)
        if scene: context.window.scene = scene
        else: return {'CANCELLED'}

        view_layer = scene.view_layers.get(property.view_name)
        if view_layer: context.window.view_layer = view_layer

        if property.cam_name and property.cam_name != "NONE":
            cam_obj = bpy.data.objects.get(property.cam_name)
            if cam_obj and cam_obj.type == 'CAMERA': scene.camera = cam_obj

        arm_obj = bpy.data.objects.get(property.rig_name)
        if arm_obj and arm_obj.type == 'ARMATURE' and arm_obj.animation_data:
            if arm_obj.animation_data.action:
                try: arm_obj.animation_data.action = None
                except AttributeError: pass 
                
            for track in arm_obj.animation_data.nla_tracks:
                if track.name == property.track_name: track.mute = False
                else: track.mute = True  

        scene.frame_start = property.frame_start
        scene.frame_end = property.frame_end

        if property.collection_visibility:
            try:
                visibility_dict = json.loads(property.collection_visibility)
                set_collection_visibility(visibility_dict)
            except Exception: pass

        return {'FINISHED'}

class RENDER_OT_CopyProperty(bpy.types.Operator):
    """Copy parameter to all enabled blocks"""
    bl_idname = "render.copy_property"
    bl_label = "Copy Parameter"
    bl_options = {'REGISTER', 'UNDO'}
    
    source_index: bpy.props.IntProperty()
    property_name: bpy.props.StringProperty()
    
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        if self.source_index >= len(props): return {'CANCELLED'}
            
        val = getattr(props[self.source_index], self.property_name)
        
        for i, p in enumerate(props):
            if p.enabled and i != self.source_index:
                try:
                    setattr(p, self.property_name, val)
                except TypeError:
                    pass # Ignore enum validation errors
        return {'FINISHED'}

class RENDER_PT_Panel(bpy.types.Panel):
    bl_idname = 'RENDER_PT_Panel'
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
        header.prop(workspace, 'render_character_name')
        header.operator("render.add_all_tracks", text="Add all tracks")
        
        header = layout.row()
        header.prop(workspace, 'render_fps')
        
        if len(properties) > 0:
            header = layout.row()
            header.prop(workspace, 'render_enable_all')
            
            bulk_move_col = header.row(align=True)
            op_bulk_up = bulk_move_col.operator("render.move_selected_tracks", icon='TRIA_UP', text="")
            op_bulk_up.direction = 'UP'
            op_bulk_down = bulk_move_col.operator("render.move_selected_tracks", icon='TRIA_DOWN', text="")
            op_bulk_down.direction = 'DOWN'

            header.operator("render.update_track_time", text="Update Time")
            header.operator("render.duplicate_tracks", text="Duplicate")
            header.alert = True
            header.operator("render.delete_tracks", text="-Remove selected-")
            header.alert = False
            header.prop(workspace, "render_folded_all", icon='DISCLOSURE_TRI_DOWN' if workspace.render_folded_all else 'DISCLOSURE_TRI_RIGHT')

        finished_list = []
        if workspace.render_finished_ids:
            try: finished_list = json.loads(workspace.render_finished_ids)
            except: pass

        for i, prop in enumerate(properties):
            render_box = layout.box()
            header = render_box.row()
            header.prop(prop, "enabled")

            move_col = header.row(align=True)
            
            up_btn = move_col.row(align=True)
            up_btn.enabled = (i > 0)
            op_up = up_btn.operator("render.move_render", icon='TRIA_UP', text="")
            op_up.index = i
            op_up.direction = 'UP'
            
            down_btn = move_col.row(align=True)
            down_btn.enabled = (i < len(properties) - 1)
            op_down = down_btn.operator("render.move_render", icon='TRIA_DOWN', text="")
            op_down.index = i
            op_down.direction = 'DOWN'

            render_text = form_render_text(self, prop)
            status_suffix = ""
            
            if workspace.render_current_idx == i: status_suffix = " (rendering)"
            elif i in finished_list: status_suffix = " (rendered)"
                
            header.label(text=f'Render {i + 1}{status_suffix}|{render_text}')
            header.prop(prop, "folded", icon='DISCLOSURE_TRI_DOWN' if prop.folded else 'DISCLOSURE_TRI_RIGHT')

            if prop.folded:
                col = render_box.column()
                col.prop(prop, "character_name")
                col.label(text="Snapshot parameters:")
                row = col.row()
                row.operator("view3d.store_collection_visibility", text="Store Status").index=i
                row.operator("view3d.restore_collection_visibility", text="Apply to View").index=i
                if prop.collection_visibility and prop.collection_visibility != '':
                    row.alert = True
                    row.operator("view3d.clear_collection_visibility", text="Clear Collections").index=i
                    row.alert = False

                for p_name in ["scene_name", "view_name", "rig_name", "track_name", "cam_name"]:
                    r = col.row(align=True)
                    r.prop(prop, p_name)
                    op = r.operator("render.copy_property", text="", icon='COPYDOWN')
                    op.source_index = i
                    op.property_name = p_name

                row_frames = col.row(align=True)
                row_frames.prop(prop, "frame_start")
                op_start = row_frames.operator("render.copy_property", text="", icon='COPYDOWN')
                op_start.source_index = i
                op_start.property_name = "frame_start"
                
                row_frames.prop(prop, "frame_end")
                op_end = row_frames.operator("render.copy_property", text="", icon='COPYDOWN')
                op_end.source_index = i
                op_end.property_name = "frame_end"

                r_out = col.row(align=True)
                r_out.prop(prop, "output_path")
                op_out = r_out.operator("render.copy_property", text="", icon='COPYDOWN')
                op_out.source_index = i
                op_out.property_name = "output_path"

                col.alert = True
                row = col.row()
                row.operator("render.delete_render", text="-Remove-").index=i
                row.alert = False
                row.operator("render.duplicate_render", text="duplicate").index=i 
                
        footer = layout.row()
        footer.operator('render.add_render', text="Add")
        footer.operator("render.check_status", text="Check Status", icon='FILE_REFRESH')
        footer.operator("render.render_seq_operator", text="Render", icon='RENDER_ANIMATION')

class RENDER_OT_MoveRender(bpy.types.Operator):
    bl_idname = "render.move_render"
    bl_label = "Move Layer Item"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty()
    direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        if self.direction == 'UP' and self.index > 0:
            props.move(self.index, self.index - 1)
        elif self.direction == 'DOWN' and self.index < len(props) - 1:
            props.move(self.index, self.index + 1)
        return {'FINISHED'}

class RENDER_OT_MoveSelectedTracks(bpy.types.Operator):
    bl_idname = "render.move_selected_tracks"
    bl_label = "Move Selected Layer Items"
    bl_options = {'REGISTER', 'UNDO'}
    direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        count = len(props)
        if count <= 1: return {'FINISHED'}
        if self.direction == 'UP':
            for i in range(count):
                if props[i].enabled and i > 0: props.move(i, i - 1)
        else:
            for i in reversed(range(count)):
                if props[i].enabled and i < count - 1: props.move(i, i + 1)
        return {'FINISHED'}

class RENDER_OT_AddAllTracks(bpy.types.Operator):
    bl_idname = "render.add_all_tracks"
    bl_label = "Add All Tracks of Active Armature"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        arm = context.active_object
        return arm and arm.type == 'ARMATURE' and arm.animation_data and len(arm.animation_data.nla_tracks) > 0
    def execute(self, context):
        workspace = bpy.data.workspaces[0]
        props = workspace.render_panel_props  
        arm = context.active_object  
        camera = None 
        scene = context.scene.name
        view = context.view_layer.name

        existing = {p.track_name: p.character_name for p in props}
        c_name = workspace.render_character_name

        if arm.animation_data and arm.animation_data.nla_tracks:
            for track in arm.animation_data.nla_tracks:
                if (track.name not in existing) or (existing[track.name] != c_name):
                    prop = props.add()
                    prop.character_name = c_name
                    prop.rig_name = arm.name
                    prop.scene_name = scene
                    prop.view_name = view
                    prop.track_name = track.name
                    if camera: prop.cam_name = camera.name
        return {'FINISHED'}

class RENDER_OT_UpdateTrackTime(bpy.types.Operator):
    bl_idname = "render.update_track_time"
    bl_label = "update selected tracks"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        for prop in props:
            if prop.enabled and prop.track_name:
                old_name = prop.track_name
                prop.track_name = old_name
        return {'FINISHED'}

class RENDER_OT_DuplicateTracks(bpy.types.Operator):
    bl_idname = "render.duplicate_tracks"
    bl_label = "duplicate selected tracks"
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context):
        tracks = bpy.data.workspaces[0].render_panel_props
        return len(tracks) > 0 and True in [t.enabled for t in tracks]
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        for i in range(len(props) - 1, -1, -1):
            initial = props[i]
            if initial.enabled:
                duplicate = props.add()
                copy_render_props(initial, duplicate)
                props.move(len(props) - 1, i + 1)
        return {'FINISHED'}

class RENDER_OT_DeleteTracks(bpy.types.Operator):
    bl_idname = "render.delete_tracks"
    bl_label = "delete selected tracks"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        for index in reversed(range(len(props))):  
            if props[index].enabled: props.remove(index)  
        return {'FINISHED'}

class RENDER_OT_AddRender(bpy.types.Operator):
    bl_idname = "render.add_render"
    bl_label = "Create new render"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        bpy.data.workspaces[0].render_panel_props.add()
        return {'FINISHED'}
    
class RENDER_OT_DeleteRender(bpy.types.Operator):
    bl_idname = "render.delete_render"
    bl_label = "Delete render"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty()
    def execute(self, context):
        bpy.data.workspaces[0].render_panel_props.remove(self.index)
        return {'FINISHED'}

class RENDER_OT_DuplicateRender(bpy.types.Operator):
    bl_idname = "render.duplicate_render"
    bl_label = "Duplicate render"
    bl_options = {'REGISTER', 'UNDO'}
    index: bpy.props.IntProperty()
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        initial = props[self.index]
        duplicate = props.add()
        copy_render_props(initial, duplicate)
        props.move(len(props) - 1, self.index + 1)
        return {'FINISHED'}

class RENDER_OT_CheckRenderStatus(bpy.types.Operator):
    bl_idname = "render.check_status"
    bl_label = "Check Rendered Status"
    bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        props = bpy.data.workspaces[0].render_panel_props
        finished_list = get_rendered_status(props)
        bpy.data.workspaces[0].render_finished_ids = json.dumps(finished_list)
        self.report({'INFO'}, f"Checked files: {len(finished_list)} blocks fully rendered.")
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
        scene = bpy.data.scenes.get(scene_name)
        if scene is None: return False
        
        bpy.context.window.scene = scene
        view = scene.view_layers.get(view_name)
        if view is None: return False
        
        bpy.context.window.view_layer = view
        bpy.ops.view3d.restore_collection_visibility(index=self.index)
                    
        armature_obj = bpy.data.objects.get(rig_name)
        if armature_obj is None or armature_obj.type != 'ARMATURE': return False
        
        track_index = armature_obj.animation_data.nla_tracks.find(track_name)
        if track_index == -1: return False
        else:
            if armature_obj.animation_data.action:
                try: armature_obj.animation_data.action = None
                except AttributeError: pass
            for track in armature_obj.animation_data.nla_tracks:
                track.mute = True
            armature_obj.animation_data.nla_tracks[track_index].mute = False
        
        cam_obj = bpy.data.objects.get(cam_name)
        if cam_obj and cam_obj.type == 'CAMERA':
            scene.camera = cam_obj

        scene.frame_start = frame_start
        scene.frame_end = frame_end
        scene.render.fps = fps
        scene.render.use_file_extension = True
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.filepath = output_path
        
        if scene.node_tree and scene.node_tree.nodes and len(scene.node_tree.nodes) > 0:
            for node in [node for node in scene.node_tree.nodes if node.type == 'OUTPUT_FILE']:
                node.base_path = output_path
        
        bpy.context.scene.render.filepath = output_path
        return True 
    
    def pre(self, scene, context=None):
        try: self.rendering = True
        except ReferenceError: pass
        
    def complete(self, scene, context=None):
        try:
            workspace = bpy.data.workspaces[0]
            try: finished_list = json.loads(workspace.render_finished_ids)
            except: finished_list = []
            
            if self.index not in finished_list:
                finished_list.append(self.index)
            workspace.render_finished_ids = json.dumps(finished_list)
            
            self.index += 1
            workspace.render_current_idx = self.index
            self.rendering = False
            
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
        except ReferenceError: pass
        
    def canceled(self, scene, context=None):
        try: self.stop = True
        except ReferenceError: pass
    
    def execute(self, context):
        if self.pre in bpy.app.handlers.render_pre: bpy.app.handlers.render_pre.remove(self.pre)
        if self.complete in bpy.app.handlers.render_complete: bpy.app.handlers.render_complete.remove(self.complete)
        if self.canceled in bpy.app.handlers.render_cancel: bpy.app.handlers.render_cancel.remove(self.canceled)
            
        self.index = 0
        self.stop = False
        self.rendering = False
        self.props = props = bpy.data.workspaces[0]
        self.render_list = props.render_panel_props
        self.props.render_current_idx = 0

        finished_list = get_rendered_status(self.render_list)
        self.props.render_finished_ids = json.dumps(finished_list)
        
        bpy.app.handlers.render_pre.append(self.pre)
        bpy.app.handlers.render_complete.append(self.complete)
        bpy.app.handlers.render_cancel.append(self.canceled)
        
        self._timer = bpy.context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
        
    def modal(self, context, event):
        if event.type == 'TIMER':
            if self.index >= len(self.render_list) or self.stop:
                if self.pre in bpy.app.handlers.render_pre: bpy.app.handlers.render_pre.remove(self.pre)
                if self.complete in bpy.app.handlers.render_complete: bpy.app.handlers.render_complete.remove(self.complete)
                if self.canceled in bpy.app.handlers.render_cancel: bpy.app.handlers.render_cancel.remove(self.canceled)

                bpy.context.window_manager.event_timer_remove(self._timer)
                bpy.data.workspaces[0].render_current_idx = -1 
                return {'FINISHED'}
            
            elif not self.rendering:
                if self.render_list[self.index].enabled:
                    render_data = self.render_list[self.index]
                    bpy.data.workspaces[0].render_current_idx = self.index 
                    
                    success = self.set_render_settings(
                        render_data.rig_name, render_data.scene_name, render_data.cam_name,
                        render_data.view_name, render_data.track_name, render_data.frame_start,
                        render_data.frame_end, render_data.output_path, self.props.render_fps
                    )
                    if not success:
                        bpy.data.workspaces[0].render_current_idx = -1
                        return {'FINISHED'}
                    bpy.ops.render.render('INVOKE_DEFAULT', animation=True, write_still=True)
                else:
                    self.index += 1
                    bpy.data.workspaces[0].render_current_idx = self.index
        return {'PASS_THROUGH'}

classes = (
    RENDER_Props,
    RENDER_PT_Panel,
    RENDER_OT_CopyProperty,
    RENDER_OT_AddRender,
    RENDER_OT_DeleteRender,
    RENDER_OT_DuplicateRender,
    RENDER_OT_UpdateTrackTime,
    RENDER_OT_DeleteTracks,
    RENDER_OT_AddAllTracks,
    RENDER_SEQ_OT,
    RENDER_OT_CheckRenderStatus,
    STORE_OT_collection_visibility,
    RESTORE_OT_collection_visibility,
    CLEAR_OT_collection_visibility,
    RENDER_OT_DuplicateTracks,
    RENDER_OT_MoveRender,
    RENDER_OT_MoveSelectedTracks,
)

props = [
    "render_panel_props",
    "render_enable_all",
    "render_character_name",
    "render_folded_all",
    "render_fps",
    "render_current_idx",
    "render_finished_ids"
]
        
def register():
    for my_class in classes: bpy.utils.register_class(my_class)
    bpy.types.WorkSpace.render_panel_props = bpy.props.CollectionProperty(type = RENDER_Props)
    bpy.types.WorkSpace.render_enable_all = bpy.props.BoolProperty(name="", default=False, update=update_enable_all)
    bpy.types.WorkSpace.render_character_name = bpy.props.StringProperty(name="character name", default=CHARACTER_NAME)
    bpy.types.WorkSpace.render_folded_all = bpy.props.BoolProperty(name="", default=True, update=update_folded_all)
    bpy.types.WorkSpace.render_fps = bpy.props.IntProperty(name="fps:", default=12)
    bpy.types.WorkSpace.render_current_idx = bpy.props.IntProperty(name="", default=-1)
    bpy.types.WorkSpace.render_finished_ids = bpy.props.StringProperty(name="", default="[]")
    
def unregister():
    for my_class in classes: bpy.utils.unregister_class(my_class)
    for prop in props:
        if hasattr(bpy.types.WorkSpace, prop): delattr(bpy.types.WorkSpace, prop)
            
if __name__ == '__main__':
    register()