extends SceneTree

func _init():
	await get_tree().process_frame
	await get_tree().process_frame
	
	var img = get_viewport().get_texture().get_image()
	var path = "res://screenshot.png"
	var abs_path = ProjectSettings.globalize_path(path)
	
	img.save_png(path)
	
	print("SCREENSHOT_PATH:" + abs_path)
	quit()
