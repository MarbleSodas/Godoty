#!/usr/bin/env -S godot --headless -s
extends SceneTree

var debug_mode = false

func _init():
	var args = OS.get_cmdline_args()
	debug_mode = "--debug-godot" in args

	if debug_mode:
		print("[DEBUG] Viewport capture script starting...")

	# Wait for viewport to render
	await get_tree().process_frame
	await get_tree().process_frame

	var viewport = root.get_viewport()
	if not viewport:
		printerr("[ERROR] Could not get viewport")
		quit(1)

	var img = viewport.get_texture().get_image()
	if not img:
		printerr("[ERROR] Could not capture viewport image")
		quit(1)

	if debug_mode:
		print("[DEBUG] Image captured: " + str(img.get_width()) + "x" + str(img.get_height()))

	var path = "res://screenshot.png"
	var abs_path = ProjectSettings.globalize_path(path)

	var error = img.save_png(path)
	if error != OK:
		printerr("[ERROR] Failed to save screenshot: " + str(error))
		quit(1)

	print("SCREENSHOT_PATH:" + abs_path)

	if debug_mode:
		print("[DEBUG] Screenshot saved successfully to: " + abs_path)

	quit(0)
