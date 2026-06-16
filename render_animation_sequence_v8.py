import bpy, re
import json

bl_info = {
    "name": "Render Sequences Pro",
    "author": "Mikhail Lebedev",
    "version": (1, 3, 2),
    "blender": (3, 6, 5),
    "location": "3d Viewport > Animation Panel",
    "description": "Render sequences with persistent data and filtered camera selection",
    "category": "Animation",
}

CHARACTER_NAME = "character"

# --- HELPER FUNCTIONS ---

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

# --- UPDATE LOGIC ---

def update_output_folder(self, context):
    output = "//..\\render\\"
    def split_parts(name):
        pattern = r"[\W_]+"
        return re.split(pattern, name) if name else []
    
    if not self.character_name:
        pass
    elif self.character_name == 'scene':
        output += f"{self.scene_name}\\"
    elif self.character_name == 'view_layer':
        output += f"{self.view_name}\\"
    else:
        output += f"{self.character_name}\\"

    track_parts = []
    if self.track_name:
        track_parts = split_parts(self.track_name)
        cleaned_name = '_'.join([part for part in track_parts if part not in ['up', 'down']])
        output += f"{cleaned_name}\\"

    name_parts = (split_parts(self.scene_name) + split_parts(self.view_name) + track_parts + split_parts(self.cam_name))   
    lowered_parts = [n.lower() for n in name_parts]
    if 'up' in lowered_parts: output += "up\\"
    elif 'down' in lowered_parts: output += "down\\"
    self.output_path = output

def update_time(self, context):
    update_output_folder(self, context)
    rig = bpy.data.objects.get(self.rig_name)
    if rig and rig.animation_data and self.track_name:
        track = rig.animation_data.nla_tracks.get(self.track_name)
        if track and track.strips:
            self.frame_start = int(track.strips[0].frame_start_ui)
            self.frame_end = int(track.strips[0].frame_end_ui) - 1

def update_camera_ptr(self, context):
    """Sync the pointer selection to our persistent string"""
    if self.cam_ptr:
        self.cam_name = self.cam_ptr.name
    update_output_folder(self, context)

def poll_cameras(self, object):
    return object.type == 'CAMERA'

def update_enable_all(self, context):
    for prop in context.workspace.render_panel_props:
        prop.enabled = context.workspace.render_enable_all
                
def update_folded_all(self, context):
    for prop in context.workspace.render_panel_props:
        if prop.enabled: prop.folded = context.workspace.render_folded_all

def form_render_text(property):
    output = property.character_name if property.character_name not in ['', 'scene', 'view_layer'] else (property.character_name or "Unknown")
    if property.track_name:
        parts = property.track_name.split('_')
        cleaned = '_'.join([p for p in parts if p not in ['up', 'down']])
        output += f" | {cleaned}"
    if 'up' in property.output_path.lower(): output += " | up"
    elif 'down' in property.output_path.lower(): output += " | down"
    return output

# --- DATA MODELS ---

class RENDER_Props(bpy.types.PropertyGroup):
    folded: bpy.props.BoolProperty(name="", default=True)
    enabled: bpy.props.BoolProperty(name="", description="Enable Render Layer", default=True)
    rig_name: bpy.props.StringProperty(name="Rig", update=update_time)
    character_name: bpy.props.StringProperty(name="Character", default=CHARACTER_NAME, update=update_output_folder)
    scene_name: bpy.props.StringProperty(name="Scene", update=update_output_folder)
    view_name: bpy.props.StringProperty(name="View Layer", update=update_output_folder)
    
    # Persistent String
    cam_name: bpy.props.StringProperty(name="Camera", update=update_output_folder)
    # UI Filtered Pointer
    cam_ptr: bpy.props.PointerProperty(
        type=bpy.types.Object, 
        name="Camera", 
        poll=poll_cameras, 
        update=update_camera_ptr
    )
    
    track_name: bpy.props.StringProperty(name="Track", update=update_time)
    frame_start: bpy.props.IntProperty(default=0)
    frame_end: bpy.props.IntProperty(default=0)
    output_path: bpy.props.StringProperty(default="//..\\render\\", subtype='DIR_PATH')
    collection_visibility: bpy.props.StringProperty()

# --- OPERATORS ---

class RENDER_OT_MoveSelected(bpy.types.Operator):
    bl_idname = "render.move_selected"
    bl_label = "Move Selected"
    direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])
    def execute(self, context):
        props = context.workspace.render_panel_props
        indices = [i for i, p in enumerate(props) if p.enabled]
        if self.direction == 'UP':
            for i in indices:
                if i > 0: props.move(i, i - 1)
        else:
            for i in reversed(indices):
                if i < len(props) - 1: props.move(i, i + 1)
        return {'FINISHED'}

class RENDER_OT_StoreSelectedVisibility(bpy.types.Operator):
    bl_idname = "render.store_selected_visibility"
    bl_label = "Store Selected Vis"
    def execute(self, context):
        props = context.workspace.render_panel_props
        vis_state = json.dumps(get_collection_path(bpy.context.view_layer.layer_collection))
        for p in props:
            if p.enabled: p.collection_visibility = vis_state
        return {'FINISHED'}

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
        workspace = context.workspace
        properties = workspace.render_panel_props
        
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(workspace, 'render_character_name')
        row.operator("render.add_all_tracks", text="Add All", icon='ADD')
        
        row = col.row(align=True)
        row.prop(workspace, 'render_fps')
        
        if len(properties) > 0:
            row = layout.row(align=True)
            move_batch = row.row(align=True)
            move_batch.operator("render.move_selected", text="", icon='TRIA_UP_BAR').direction = 'UP'
            move_batch.operator("render.move_selected", text="", icon='TRIA_DOWN_BAR').direction = 'DOWN'
            row.separator(factor=1.0)
            row.prop(workspace, 'render_enable_all', text="All", icon='CHECKBOX_HLT')
            row.operator("render.update_track_time", text="Sync", icon='FILE_REFRESH')
            row.operator("render.store_selected_visibility", text="Store Vis", icon='HIDE_OFF')
            row.operator("render.delete_tracks", text="Clear", icon='TRASH')
            row.prop(workspace, "render_folded_all", icon='DISCLOSURE_TRI_DOWN' if workspace.render_folded_all else 'DISCLOSURE_TRI_RIGHT')

        for i, prop in enumerate(properties):
            box = layout.box()
            header = box.row(align=True)
            
            move_row = header.row(align=True)
            up = move_row.operator("render.move_render", text="", icon='TRIA_UP')
            up.index, up.direction = i, 'UP'
            down = move_row.operator("render.move_render", text="", icon='TRIA_DOWN')
            down.index, down.direction = i, 'DOWN'
            
            header.separator(factor=0.5)
            header.prop(prop, "enabled")
            header.label(text=f"{i+1} | {form_render_text(prop)}")
            header.prop(prop, "folded", icon='DISCLOSURE_TRI_DOWN' if prop.folded else 'DISCLOSURE_TRI_RIGHT')

            if prop.folded:
                col = box.column(align=True)
                col.prop(prop, "character_name")
                
                # Visibility Block
                cv_row = col.row(align=True)
                cv_row.label(text="Vis Cache:")
                cv_row.operator("view3d.store_collection_visibility", text="Store").index=i
                if prop.collection_visibility:
                    cv_row.operator("view3d.restore_collection_visibility", text="Restore").index=i
                    cv_row.operator("view3d.clear_collection_visibility", text="", icon='X').index=i

                # Dynamic Scene Search
                target_scene = bpy.data.scenes.get(prop.scene_name)
                row = col.row(); row.alert = not target_scene
                row.prop_search(prop, "scene_name", bpy.data, "scenes", text="Scene", icon='SCENE_DATA')
                
                row = col.row()
                if target_scene: row.prop_search(prop, "view_name", target_scene, "view_layers", text="Layer")
                else: row.alert = True; row.prop(prop, "view_name", text="Layer (No Scene)")

                # Dynamic Rig Search
                target_rig = bpy.data.objects.get(prop.rig_name)
                row = col.row(); row.alert = not (target_rig and target_rig.type == 'ARMATURE')
                row.prop_search(prop, "rig_name", bpy.data, "objects", text="Rig", icon='OUTLINER_OB_ARMATURE')

                # Dynamic Track Search
                row = col.row()
                if target_rig and target_rig.animation_data: row.prop_search(prop, "track_name", target_rig.animation_data, "nla_tracks", text="Track")
                else: row.alert = True; row.prop(prop, "track_name", text="Track (No Rig)")

                # --- FILTERED CAMERA SELECTION ---
                row = col.row()
                # Check if the object currently named in 'cam_name' exists and is a camera
                current_cam_obj = bpy.data.objects.get(prop.cam_name)
                
                # Logic: If the pointer is lost (deleted) but we have a name, show alert
                if not prop.cam_ptr and prop.cam_name:
                    if current_cam_obj and current_cam_obj.type == 'CAMERA':
                        prop.cam_ptr = current_cam_obj # Auto-repair pointer if object exists
                    else:
                        row.alert = True
                
                row.prop(prop, "cam_ptr", text="Camera", icon='CAMERA_DATA')
                # ----------------------------------

                row = col.row(align=True)
                row.prop(prop, "frame_start", text="Start")
                row.prop(prop, "frame_end", text="End")
                col.prop(prop, "output_path")

                row = col.row(align=True)
                row.operator("render.duplicate_render", text="Duplicate", icon='DUPLICATE').index = i
                row.alert = True
                row.operator("render.delete_render", text="Remove", icon='X').index = i

        footer = layout.row(align=True); footer.scale_y = 1.4
        footer.operator('render.add_render', text="Add Block", icon='ADD')
        footer.operator("render.render_seq_operator", text="Render IMG", icon='RENDER_ANIMATION')
        footer.operator("render.render_gl_seq_operator", text="Render VID", icon='RENDER_RESULT')

# --- REMAINING LOGIC & REGISTRATION ---

class RENDER_SEQ_BASE:
    def prepare_render(self, prop, fps):
        scene = bpy.data.scenes.get(prop.scene_name)
        if not scene: return False
        bpy.context.window.scene = scene
        view = scene.view_layers.get(prop.view_name)
        if view: bpy.context.window.view_layer = view
        if prop.collection_visibility: set_collection_visibility(json.loads(prop.collection_visibility))
        rig = bpy.data.objects.get(prop.rig_name)
        if rig and rig.animation_data:
            for t in rig.animation_data.nla_tracks: t.mute = (t.name != prop.track_name)
        # Use the name string for the actual render process
        cam = bpy.data.objects.get(prop.cam_name)
        if cam and cam.type == 'CAMERA': scene.camera = cam
        scene.frame_start, scene.frame_end = prop.frame_start, prop.frame_end
        scene.render.fps, scene.render.filepath = fps, prop.output_path
        return True

class RENDER_SEQ_OT(bpy.types.Operator, RENDER_SEQ_BASE):
    bl_idname = "render.render_seq_operator"; bl_label = "Render Images"
    _timer = None; index = 0; rendering = False; stop = False
    def execute(self, context):
        self.index, self.stop, self.rendering = 0, False, False
        self.props = context.workspace.render_panel_props
        bpy.app.handlers.render_pre.append(self.pre); bpy.app.handlers.render_complete.append(self.complete)
        bpy.app.handlers.render_cancel.append(self.cancel)
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def pre(self, scene): self.rendering = True
    def complete(self, scene): 
        self.props[self.index].enabled = False
        self.index += 1; self.rendering = False
    def cancel(self, scene): self.stop = True
    def modal(self, context, event):
        if event.type == 'TIMER':
            if self.index >= len(self.props) or self.stop:
                bpy.app.handlers.render_pre.remove(self.pre); bpy.app.handlers.render_complete.remove(self.complete)
                bpy.app.handlers.render_cancel.remove(self.cancel); context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}
            if not self.rendering:
                p = self.props[self.index]
                if p.enabled and self.prepare_render(p, context.workspace.render_fps):
                    bpy.ops.render.render('INVOKE_DEFAULT', animation=True)
                else: self.index += 1
        return {'PASS_THROUGH'}

class RENDER_GL_SEQ_OT(bpy.types.Operator, RENDER_SEQ_BASE):
    bl_idname = "render.render_gl_seq_operator"; bl_label = "Viewport Render"
    _timer = None; index = 0
    def execute(self, context):
        self.index = 0
        self.props = context.workspace.render_panel_props
        self._timer = context.window_manager.event_timer_add(0.2, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def modal(self, context, event):
        if event.type == 'TIMER':
            if self.index >= len(self.props):
                context.window_manager.event_timer_remove(self._timer)
                return {'FINISHED'}
            p = self.props[self.index]
            if p.enabled and self.prepare_render(p, context.workspace.render_fps):
                bpy.context.scene.render.image_settings.file_format = 'FFMPEG'
                area = next((a for a in context.screen.areas if a.type == 'VIEW_3D'), None)
                with context.temp_override(area=area): bpy.ops.render.opengl('EXEC_DEFAULT', animation=True)
                p.enabled = False; self.index += 1
            else: self.index += 1
        return {'PASS_THROUGH'}

class RENDER_OT_MoveRender(bpy.types.Operator):
    bl_idname = "render.move_render"; bl_label = "Move"
    index: bpy.props.IntProperty(); direction: bpy.props.EnumProperty(items=[('UP', 'Up', ''), ('DOWN', 'Down', '')])
    def execute(self, context):
        props = context.workspace.render_panel_props
        new_idx = self.index - 1 if self.direction == 'UP' else self.index + 1
        if 0 <= new_idx < len(props): props.move(self.index, new_idx); return {'FINISHED'}
        return {'CANCELLED'}

class RENDER_OT_AddAllTracks(bpy.types.Operator):
    bl_idname = "render.add_all_tracks"; bl_label = "Add Tracks"
    def execute(self, context):
        arm = context.active_object
        if not (arm and arm.type == 'ARMATURE' and arm.animation_data): return {'CANCELLED'}
        for track in arm.animation_data.nla_tracks:
            item = context.workspace.render_panel_props.add()
            item.character_name, item.rig_name = context.workspace.render_character_name, arm.name
            item.scene_name, item.view_name, item.track_name = context.scene.name, context.view_layer.name, track.name
            if context.scene.camera:
                item.cam_ptr = context.scene.camera
                item.cam_name = context.scene.camera.name
        return {'FINISHED'}

class RENDER_OT_UpdateTrackTime(bpy.types.Operator):
    bl_idname = "render.update_track_time"; bl_label = "Update Time"
    def execute(self, context):
        for prop in context.workspace.render_panel_props:
            if prop.enabled: update_time(prop, context)
        return {'FINISHED'}

class RENDER_OT_DeleteTracks(bpy.types.Operator):
    bl_idname = "render.delete_tracks"; bl_label = "Delete Selected"
    def execute(self, context):
        props = context.workspace.render_panel_props
        for i in reversed(range(len(props))):
            if props[i].enabled: props.remove(i)
        return {'FINISHED'}

class RENDER_OT_AddRender(bpy.types.Operator):
    bl_idname = "render.add_render"; bl_label = "Add"
    def execute(self, context):
        context.workspace.render_panel_props.add(); return {'FINISHED'}

class RENDER_OT_DeleteRender(bpy.types.Operator):
    bl_idname = "render.delete_render"; bl_label = "Delete"
    index: bpy.props.IntProperty()
    def execute(self, context):
        context.workspace.render_panel_props.remove(self.index); return {'FINISHED'}

class RENDER_OT_DuplicateRender(bpy.types.Operator):
    bl_idname = "render.duplicate_render"; bl_label = "Duplicate"
    index: bpy.props.IntProperty()
    def execute(self, context):
        props = context.workspace.render_panel_props
        orig, dup = props[self.index], props.add()
        for p in orig.bl_rna.properties:
            if not p.is_readonly: setattr(dup, p.identifier, getattr(orig, p.identifier))
        return {'FINISHED'}

class STORE_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.store_collection_visibility"; bl_label = "Store"
    index: bpy.props.IntProperty()
    def execute(self, context):
        prop = context.workspace.render_panel_props[self.index]
        prop.collection_visibility = json.dumps(get_collection_path(bpy.context.view_layer.layer_collection))
        return {'FINISHED'}

class RESTORE_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.restore_collection_visibility"; bl_label = "Restore"
    index: bpy.props.IntProperty()
    def execute(self, context):
        prop = context.workspace.render_panel_props[self.index]
        if prop.collection_visibility: set_collection_visibility(json.loads(prop.collection_visibility))
        return {'FINISHED'}

class CLEAR_OT_collection_visibility(bpy.types.Operator):
    bl_idname = "view3d.clear_collection_visibility"; bl_label = "Clear"
    index: bpy.props.IntProperty()
    def execute(self, context):
        context.workspace.render_panel_props[self.index].collection_visibility = ''; return {'FINISHED'}

classes = (
    RENDER_Props, RENDER_PT_Panel, RENDER_OT_AddRender, RENDER_OT_DeleteRender,
    RENDER_OT_DuplicateRender, RENDER_OT_UpdateTrackTime, RENDER_OT_DeleteTracks,
    RENDER_OT_AddAllTracks, RENDER_SEQ_OT, RENDER_GL_SEQ_OT, RENDER_OT_MoveRender,
    RENDER_OT_MoveSelected, RENDER_OT_StoreSelectedVisibility,
    STORE_OT_collection_visibility, RESTORE_OT_collection_visibility, CLEAR_OT_collection_visibility,
)

def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.WorkSpace.render_panel_props = bpy.props.CollectionProperty(type=RENDER_Props)
    bpy.types.WorkSpace.render_enable_all = bpy.props.BoolProperty(name="Enable All", update=update_enable_all)
    bpy.types.WorkSpace.render_character_name = bpy.props.StringProperty(name="Char Name", default=CHARACTER_NAME)
    bpy.types.WorkSpace.render_folded_all = bpy.props.BoolProperty(name="Fold All", update=update_folded_all)
    bpy.types.WorkSpace.render_fps = bpy.props.IntProperty(name="FPS", default=12)

def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)
    del bpy.types.WorkSpace.render_panel_props
    del bpy.types.WorkSpace.render_enable_all
    del bpy.types.WorkSpace.render_character_name
    del bpy.types.WorkSpace.render_folded_all
    del bpy.types.WorkSpace.render_fps

if __name__ == '__main__':
    register()