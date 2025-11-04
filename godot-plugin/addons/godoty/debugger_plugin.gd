@tool
extends EditorDebuggerPlugin

signal log_message(entry: Dictionary)

var enabled: bool = true
var buffer: Array = []
const MAX_BUFFER := 1000

func enable_capture():
	enabled = true

func disable_capture():
	enabled = false

func clear():
	buffer.clear()

func get_buffer(max_items: int = 200) -> Array:
	var start := max(buffer.size() - max_items, 0)
	return buffer.slice(start, buffer.size())

func _has_capture(prefix: String) -> bool:
	# Capture all message prefixes when enabled.
	return enabled

func _capture(message: String, data: Array, session_id: int) -> bool:
	if not enabled:
		return false
	var entry := {
		"timestamp": Time.get_datetime_string_from_system(),
		"session_id": session_id,
		"message": message,
		"data": data
	}
	buffer.append(entry)
	if buffer.size() > MAX_BUFFER:
		buffer.pop_front()
	log_message.emit(entry)
	# Do not consume so messages still appear in the Output panel
	return false

