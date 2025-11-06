@tool
extends Node

signal snapshot_captured(data: Dictionary)

var editor_plugin: EditorPlugin
var enabled := false
var last_snapshot_b64 := ""
var last_snapshot_meta := {}

func set_editor_plugin(p: EditorPlugin) -> void:
	editor_plugin = p

func enable_auto_capture() -> void:
	enabled = true
	_connect_signals()

func disable_auto_capture() -> void:
	enabled = false
	_disconnect_signals()

func capture_snapshot(reason: String = "manual", extra: Dictionary = {}) -> Dictionary:
	var img_b64 := ""
	var size := Vector2i(0, 0)
	var ei := editor_plugin.get_editor_interface() if editor_plugin else null
	var viewport: Viewport = ei.get_editor_viewport().get_viewport() if ei else get_viewport()
	if viewport:
		var tex := viewport.get_texture()
		if tex:
			var image: Image = tex.get_image()
			if image:
				size = image.get_size()
				var bytes: PackedByteArray = image.save_png_to_buffer()
				img_b64 = _bytes_to_base64(bytes)
	last_snapshot_b64 = img_b64
	last_snapshot_meta = {
		"timestamp": Time.get_unix_time_from_system(),
		"reason": reason,
		"size": {"w": size.x, "h": size.y},
		"selection": _get_selection_paths(ei),
		"scene_path": _current_scene_path(ei),
	}
	var data := {"image_b64": img_b64, "meta": last_snapshot_meta}
	snapshot_captured.emit(data)
	return data

func get_last_snapshot() -> Dictionary:
	return {"image_b64": last_snapshot_b64, "meta": last_snapshot_meta}

func _connect_signals() -> void:
	var ei := editor_plugin.get_editor_interface() if editor_plugin else null
	if not ei: return
	var sel := ei.get_selection()
	if sel and not sel.is_connected("selection_changed", Callable(self, "_on_selection_changed")):
		sel.selection_changed.connect(_on_selection_changed)
	var root := ei.get_edited_scene_root()
	if root and root.get_tree():
		var tree := root.get_tree()
		if not tree.is_connected("node_added", Callable(self, "_on_tree_changed")):
			tree.node_added.connect(_on_tree_changed)
		if not tree.is_connected("node_removed", Callable(self, "_on_tree_changed")):
			tree.node_removed.connect(_on_tree_changed)

func _disconnect_signals() -> void:
	var ei := editor_plugin.get_editor_interface() if editor_plugin else null
	if not ei: return
	var sel := ei.get_selection()
	if sel and sel.is_connected("selection_changed", Callable(self, "_on_selection_changed")):
		sel.selection_changed.disconnect(_on_selection_changed)
	var root := ei.get_edited_scene_root()
	if root and root.get_tree():
		var tree := root.get_tree()
		if tree.is_connected("node_added", Callable(self, "_on_tree_changed")):
			tree.node_added.disconnect(_on_tree_changed)
		if tree.is_connected("node_removed", Callable(self, "_on_tree_changed")):
			tree.node_removed.disconnect(_on_tree_changed)

func _on_selection_changed() -> void:
	if enabled:
		capture_snapshot("selection_changed")

func _on_tree_changed(node: Node) -> void:
	if not enabled: return
	var ei := editor_plugin.get_editor_interface() if editor_plugin else null
	var root := ei.get_edited_scene_root() if ei else null
	if root and node and (node == root or root.is_ancestor_of(node)):
		var rel := ""
		if root:
			rel = str(root.get_path_to(node))
		capture_snapshot("scene_tree_changed", {"node": node.name, "path": rel})

func _get_selection_paths(ei: EditorInterface) -> Array:
	var paths: Array = []
	if ei:
		var sel := ei.get_selection()
		if sel:
			for n in sel.get_selected_node_list():
				paths.append(_node_path_str(ei, n))
	return paths

func _node_path_str(ei: EditorInterface, node: Node) -> String:
	var root := ei.get_edited_scene_root() if ei else null
	if root and node:
		return str(root.get_path_to(node))
	return ""

func _current_scene_path(ei: EditorInterface) -> String:
	var root := ei.get_edited_scene_root() if ei else null
	if root and "scene_file_path" in root:
		return root.scene_file_path
	return ""


# Fallback Base64 encoder compatible across Godot versions
func _bytes_to_base64(bytes: PackedByteArray) -> String:
	var table := "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
	var out := ""
	var i := 0
	while i < bytes.size():
		var b0 := int(bytes[i])
		var has_b1 := i + 1 < bytes.size()
		var has_b2 := i + 2 < bytes.size()
		var b1 := int(bytes[i + 1]) if has_b1 else 0
		var b2 := int(bytes[i + 2]) if has_b2 else 0
		var triple := (b0 << 16) | (b1 << 8) | b2
		out += table.substr((triple >> 18) & 0x3F, 1)
		out += table.substr((triple >> 12) & 0x3F, 1)
		out += table.substr((triple >> 6) & 0x3F, 1) if has_b1 else "="
		out += table.substr(triple & 0x3F, 1) if has_b2 else "="
		i += 3
	return out

