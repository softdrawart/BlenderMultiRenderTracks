bl_info = {
    "name": "Render Sequences",
    "author": "Mikhail Lebedev",
    "version": (1, 4, 1),
    "blender": (4, 0, 0),
    "location": "3d Viewport > Animation Panel",
    "description": "Full featured render sequences with multi-scene support",
    "category": "Animation",
}
    
import bpy
import json
import os

CHARACTER_NAME = "character"

# --- HELPERS ---

def get_props_scene():
    """Find the scene that contains the render blocks."""
    # 1. Check current
    if len(bpy.context.scene.render_panel_props) > 0:
        return bpy.context.scene
    # 2. Check all others
    for sc in bpy.data.scenes:
        if len(sc.render_panel_props) > 0:
            return sc
    return bpy.context.scene

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

def apply_render_block_settings(context, source_scene, index):
    """Safely apply settings from source_scene to target scenes."""
    props = source_scene.render_panel_props
    if index >= len(props): return False
    prop = props[index]
    
    # 1. Scene Switch
    target_scene = bpy.data.scenes.get(prop.scene_name)
    if not target_scene: return False
    context.window.scene = target_scene

    # 2. View Layer
    view_layer = target_scene.view_layers.get(prop.view_name)
    if view_layer: context.window.view_layer = view_layer

    # 3. Camera
    if prop.cam_name and prop.cam_name != "NONE":
        cam_obj = bpy.data.objects.get(prop.cam_name)
        if cam_obj and cam_obj.type == 'CAMERA': target_scene.camera = cam_obj

    # 4. Armature/NLA
    arm_obj = bpy.data.objects.get(prop.rig_name)
    if arm_obj and arm_obj.animation_data:
        if arm_obj.animation_data.action: arm_obj.animation_data.action = None
        for track in arm_obj.animation_data.nla_tracks:
            track.mute = (track.name != prop.track_name)

    # 5. Frames
    target_scene.frame_start = prop.frame_start
    target_scene.frame_end = prop.frame_end

    # 6. Collections
    if prop.collection_visibility:
        try:
            visibility_dict = json.loads(prop.collection_visibility)
            set_collection_visibility(visibility_dict)
        except: pass
            
    target_scene.view_layers.update()
    return True

# --- PROPERTY UPDATES ---

def update_output_folder(self, context):
    output = "//../render/"
    match self.character_name:
        case 'scene': output += f"{self.scene_name}/"
        case 'view_layer': output += f"{self.view_name}/"
        case _: output += f"{self.character_name}/"
            
    if self.track_name:
        cleaned = '_'.join([p for p in self.track_name.split('_') if p.lower() not in ['up', 'down']])
        output += f"{cleaned}/"
        
    combined = (self.cam_name + self.scene_name + self.view_name + self.track_name).lower()
    if "up" in combined: output += "up/"
    elif "down" in combined: output += "down/"
    self.output_path = output

def update_time(self, context):
    update_output_folder(self, context) 
    arm = bpy.data.objects.get(self.rig_name)
    if arm and arm.animation_data and self.track_name in arm.animation_data.nla_tracks:
        track = arm.animation_data.nla_tracks[self.track_name]
        if track.strips:
            self.frame_start = int(track.strips[0].frame_start_ui)
            self.frame_end = int(track.strips[0].frame_end_ui) - 1

def update_enable_all(self, context):
    for prop in self.render_panel_props: prop.enabled = self.render_enable_all

def update_folded_all(self, context):
    for prop in self.render_panel_props: 
        if prop.enabled: prop.folded = self.render_folded_all

def form_render_text(self, property):
    output = ""
    match property.character_name:
        case 'scene': output += f"{property.scene_name}"
        case 'view_layer': output += f"{property.view_name}"
        case _: output += f"{property.character_name}"
    if property.track_name:
        cleaned = '_'.join([p for p in property.track_name.split('_') if p not in ['up', 'down']])
        output += f"|{cleaned}"
    path_norm = property.output_path.replace('\\', '/')
    if 'up/' in path_norm: output += "|up"
    elif 'down/' in path_norm: output += "|down"
    return output

# --- DATA STRUCTURE ---

class RENDER_Props(bpy.types.PropertyGroup):
    folded: bpy.props.BoolProperty(name="", default=True)
    enabled: bpy.props.BoolProperty(name="", default=True)
    rig_name: bpy.props.EnumProperty(items=lambda s,c: [(o.name, o.name, '') for o in bpy.data.objects if o.type == 'ARMATURE'], update=update_output_folder)
    character_name: bpy.props.StringProperty(default=CHARACTER_NAME, update=update_output_folder)
    scene_name: bpy.props.EnumProperty(items=lambda s,c: [(sc.name, sc.name, '') for sc in bpy.data.scenes], update=update_output_folder)
    view_name: bpy.props.EnumProperty(items=lambda s,c: [(l.name, l.name, '') for l in bpy.data.scenes.get(s.scene_name).view_layers] if bpy.data.scenes.get(s.scene_name) else [], update=update_output_folder)
    cam_name: bpy.props.EnumProperty(items=lambda s,c: [("NONE", "None", "")] + [(o.name, o.name, '') for o in bpy.data.objects if o.type == 'CAMERA'], update=update_output_folder)
    track_name: bpy.props.EnumProperty(items=lambda s,c: [(t.name, t.name, '') for t in bpy.data.objects.get(s.rig_name).animation_data.nla_tracks] if bpy.data.objects.get(s.rig_name) and bpy.data.objects.get(s.rig_name).animation_data else [], update=update_time)
    frame_start: bpy.props.IntProperty(default=0)
    frame_end: bpy.props.IntProperty(default=0)
    output_path: bpy.props.StringProperty(description="Path to Directory", default="//../render/", maxlen=1024, subtype='DIR_PATH')
    collection_visibility: bpy.props.StringProperty()

# --- UI OPERATORS ---

class CLEAR_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.clear_collection_visibility"
    bl_label = "Clear"
    index: bpy.props.IntProperty()
    def execute(self, context):
        get_props_scene().render_panel_props[self.index].collection_visibility = ''
        return {'FINISHED'}

class STORE_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.store_collection_visibility"
    bl_label = "Store Status"
    index: bpy.props.IntProperty()
    def execute(self, context):
        prop = get_props_scene().render_panel_props[self.index]
        prop.collection_visibility = json.dumps(get_collection_path(context.view_layer.layer_collection))
        return {'FINISHED'}

class RESTORE_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.restore_collection_visibility"
    bl_label = "Apply to View"
    index: bpy.props.IntProperty() 
    def execute(self, context):
        success = apply_render_block_settings(context, get_props_scene(), self.index)
        return {'FINISHED'} if success else {'CANCELLED'}

class RENDER_OT_MoveRender(bpy.types.Operator):
    bl_idname = "render.move_render"
    bl_label = "Move"
    index: bpy.props.IntProperty()
    direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])
    def execute(self, context):
        props = get_props_scene().render_panel_props
        if self.direction == 'UP' and self.index > 0: props.move(self.index, self.index - 1)
        elif self.direction == 'DOWN' and self.index < len(props)-1: props.move(self.index, self.index + 1)
        return {'FINISHED'}

class RENDER_OT_MoveSelectedTracks(bpy.types.Operator):
    bl_idname = "render.move_selected_tracks"
    bl_label = "Move Selected"
    direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])
    def execute(self, context):
        props = get_props_scene().render_panel_props
        count = len(props)
        if self.direction == 'UP':
            for i in range(count):
                if props[i].enabled and i > 0: props.move(i, i - 1)
        else:
            for i in reversed(range(count)):
                if props[i].enabled and i < count - 1: props.move(i, i + 1)
        return {'FINISHED'}

class RENDER_OT_UpdateTrackTime(bpy.types.Operator):
    bl_idname = "render.update_track_time"
    bl_label = "Update Time"
    def execute(self, context):
        for prop in get_props_scene().render_panel_props:
            if prop.enabled:
                old = prop.track_name
                prop.track_name = old
        return {'FINISHED'}

class RENDER_OT_DuplicateTracks(bpy.types.Operator):
    bl_idname = "render.duplicate_tracks"
    bl_label = "Duplicate Selected"
    def execute(self, context):
        props = get_props_scene().render_panel_props
        for initial in list(props):
            if initial.enabled:
                new = props.add()
                for p in initial.bl_rna.properties:
                    if not p.is_readonly: setattr(new, p.identifier, getattr(initial, p.identifier))
        return {'FINISHED'}

class RENDER_OT_DeleteTracks(bpy.types.Operator):
    bl_idname = "render.delete_tracks"
    bl_label = "Remove Selected"
    def execute(self, context):
        props = get_props_scene().render_panel_props
        for i in reversed(range(len(props))):
            if props[i].enabled: props.remove(i)
        return {'FINISHED'}

class RENDER_OT_DeleteRender(bpy.types.Operator):
    bl_idname = "render.delete_render"
    bl_label = "Remove"
    index: bpy.props.IntProperty()
    def execute(self, context):
        get_props_scene().render_panel_props.remove(self.index)
        return {'FINISHED'}

class RENDER_OT_DuplicateRender(bpy.types.Operator):
    bl_idname = "render.duplicate_render"
    bl_label = "Duplicate"
    index: bpy.props.IntProperty()
    def execute(self, context):
        props = get_props_scene().render_panel_props
        initial = props[self.index]
        new = props.add()
        for p in initial.bl_rna.properties:
            if not p.is_readonly: setattr(new, p.identifier, getattr(initial, p.identifier))
        return {'FINISHED'}

class RENDER_OT_AddRender(bpy.types.Operator):
    bl_idname = "render.add_render"
    bl_label = "Add"
    def execute(self, context):
        get_props_scene().render_panel_props.add()
        return {'FINISHED'}

class RENDER_OT_AddAllTracks(bpy.types.Operator):
    bl_idname = "render.add_all_tracks"
    bl_label = "Add all tracks"
    def execute(self, context):
        scene = get_props_scene()
        arm = context.active_object
        if arm and arm.animation_data:
            for track in arm.animation_data.nla_tracks:
                new = scene.render_panel_props.add()
                new.character_name = scene.render_character_name
                new.rig_name = arm.name
                new.scene_name = scene.name
                new.track_name = track.name
        return {'FINISHED'}

# --- CORE RENDER OPERATOR ---

class RENDER_SEQ_OT(bpy.types.Operator):
    bl_idname = "render.render_seq_operator"
    bl_label = "Render"
    
    index = 0
    stop = False
    rendering = False

    def complete(self, scene, context=None):
        try:
            ws = self.source_scene
            finished = json.loads(ws.render_finished_ids) if ws.render_finished_ids else []
            if self.index not in finished: finished.append(self.index)
            ws.render_finished_ids = json.dumps(finished)
            self.index += 1
            ws.render_current_idx = self.index
            self.rendering = False
        except: pass
        
    def canceled(self, scene, context=None):
        self.stop = True
    
    def execute(self, context):
        self.source_scene = get_props_scene()
        self.render_list = self.source_scene.render_panel_props
        self.index = 0
        self.stop = False
        self.rendering = False
        self.source_scene.render_current_idx = 0
        self.source_scene.render_finished_ids = "[]"
        
        bpy.app.handlers.render_complete.append(self.complete)
        bpy.app.handlers.render_cancel.append(self.canceled)
        
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
        
    def modal(self, context, event):
        if event.type == 'TIMER':

            while self.index < len(self.render_list) and not self.render_list[self.index].enabled:
                self.index += 1
            
            if self.index >= len(self.render_list) or self.stop:
                if self.complete in bpy.app.handlers.render_complete: bpy.app.handlers.render_complete.remove(self.complete)
                if self.canceled in bpy.app.handlers.render_cancel: bpy.app.handlers.render_cancel.remove(self.canceled)
                context.window_manager.event_timer_remove(self._timer)
                self.source_scene.render_current_idx = -1 
                return {'FINISHED'}
            
            self.source_scene.render_current_idx = self.index

            if not self.rendering:
                if apply_render_block_settings(context, self.source_scene, self.index):
                    render_data = self.render_list[self.index]
                    context.scene.render.filepath = bpy.path.abspath(render_data.output_path)
                    context.scene.render.fps = self.source_scene.render_fps
                    bpy.ops.render.render('INVOKE_DEFAULT', animation=True)
                else:
                    self.index += 1
        return {'PASS_THROUGH'}

# --- UI PANEL ---

class RENDER_PT_Panel(bpy.types.Panel):
    bl_idname = 'RENDER_PT_Panel'
    bl_label = 'Render Sequences'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'render'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = get_props_scene()
        props = scene.render_panel_props
        
        # Header
        header = layout.row()
        header.prop(scene, 'render_character_name', text="character")
        header.operator("render.add_all_tracks")
        
        row = layout.row()
        row.prop(scene, 'render_fps', text="fps")
        
        # Bulk Controls
        if len(props) > 0:
            row = layout.row()
            row.prop(scene, 'render_enable_all', text="")
            
            bulk_move = row.row(align=True)
            op_up = bulk_move.operator("render.move_selected_tracks", icon='TRIA_UP', text="")
            op_up.direction = 'UP'
            op_down = bulk_move.operator("render.move_selected_tracks", icon='TRIA_DOWN', text="")
            op_down.direction = 'DOWN'

            row.operator("render.update_track_time")
            row.operator("render.duplicate_tracks", text="Duplicate")
            row.alert = True
            row.operator("render.delete_tracks", text="- Remove selected -")
            row.alert = False
            row.prop(scene, "render_folded_all", icon='DISCLOSURE_TRI_DOWN' if scene.render_folded_all else 'DISCLOSURE_TRI_RIGHT')

        # List
        finished_list = json.loads(scene.render_finished_ids) if scene.render_finished_ids else []

        for i, prop in enumerate(props):
            render_box = layout.box()
            header = render_box.row()
            header.prop(prop, "enabled")

            # Individual move
            move_col = header.row(align=True)
            up_btn = move_col.row(align=True)
            up_btn.enabled = (i > 0)
            op_up = up_btn.operator("render.move_render", icon='TRIA_UP', text="")
            op_up.index = i; op_up.direction = 'UP'
            
            down_btn = move_col.row(align=True)
            down_btn.enabled = (i < len(props) - 1)
            op_down = down_btn.operator("render.move_render", icon='TRIA_DOWN', text="")
            op_down.index = i; op_down.direction = 'DOWN'

            # Label
            render_text = form_render_text(self, prop)
            status = " (rendering)" if scene.render_current_idx == i else (" (rendered)" if i in finished_list else "")
            header.label(text=f'Render {i+1}{status}|{render_text}')
            header.prop(prop, "folded", icon='DISCLOSURE_TRI_DOWN' if prop.folded else 'DISCLOSURE_TRI_RIGHT')

            if prop.folded:
                col = render_box.column()
                col.prop(prop, "character_name")
                col.label(text="Snapshot parameters:")
                row = col.row()
                row.operator("view3d.store_collection_visibility", text="Store Status").index=i
                row.operator("view3d.restore_collection_visibility", text="Apply to View").index=i
                if prop.collection_visibility:
                    row.alert = True
                    row.operator("view3d.clear_collection_visibility", text="Clear Collections").index=i
                    row.alert = False

                col.prop(prop, "scene_name")
                col.prop(prop, "view_name")
                col.prop(prop, "rig_name")
                col.prop(prop, "track_name")
                col.prop(prop, "cam_name")
                row = col.row()
                row.prop(prop, "frame_start")
                row.prop(prop, "frame_end")
                col.prop(prop, "output_path")
                
                row = col.row()
                row.alert = True
                row.operator("render.delete_render", text="- Remove -").index = i
                row.alert = False
                row.operator("render.duplicate_render", text="duplicate").index = i 
                
        footer = layout.row()
        footer.operator('render.add_render', text="Add")
        footer.operator("render.render_seq_operator", text="Render", icon='RENDER_ANIMATION')

# --- REGISTRATION ---

classes = (
    RENDER_Props, RENDER_PT_Panel, RENDER_SEQ_OT, RESTORE_OT_collection_visibility,
    STORE_OT_collection_visibility, CLEAR_OT_collection_visibility, RENDER_OT_MoveRender,
    RENDER_OT_MoveSelectedTracks, RENDER_OT_UpdateTrackTime, RENDER_OT_DuplicateTracks,
    RENDER_OT_DeleteTracks, RENDER_OT_AddRender, RENDER_OT_DeleteRender,
    RENDER_OT_DuplicateRender, RENDER_OT_AddAllTracks
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    s = bpy.types.Scene
    s.render_panel_props = bpy.props.CollectionProperty(type=RENDER_Props)
    s.render_enable_all = bpy.props.BoolProperty(name="", default=True, update=update_enable_all)
    s.render_character_name = bpy.props.StringProperty(name="character name", default=CHARACTER_NAME)
    s.render_folded_all = bpy.props.BoolProperty(name="", default=True, update=update_folded_all)
    s.render_fps = bpy.props.IntProperty(name="fps:", default=12)
    s.render_current_idx = bpy.props.IntProperty(default=-1)
    s.render_finished_ids = bpy.props.StringProperty(default="[]")

def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    s = bpy.types.Scene
    del s.render_panel_props
    del s.render_enable_all
    del s.render_character_name
    del s.render_folded_all
    del s.render_fps
    del s.render_current_idx
    del s.render_finished_ids

if __name__ == '__main__':
    register()