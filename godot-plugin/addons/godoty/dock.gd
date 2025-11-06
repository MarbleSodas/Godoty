@tool
extends Control

signal status_changed(status: String)

@onready var status_label: Label = $VBoxContainer/StatusLabel
@onready var log_text: TextEdit = $VBoxContainer/LogText
@onready var clear_button: Button = $VBoxContainer/HBoxContainer/ClearButton

var log_lines: Array[String] = []
const MAX_LOG_LINES = 100

func _ready():
	if clear_button:
		clear_button.pressed.connect(_on_clear_pressed)
	
	update_status("Waiting for connection...")

func update_status(message: String):
	if status_label:
		status_label.text = "Status: %s" % message
	
	_add_log(message)
	status_changed.emit(message)

func _add_log(message: String):
	var timestamp = Time.get_datetime_string_from_system()
	var log_entry = "[%s] %s" % [timestamp, message]
	
	log_lines.append(log_entry)
	if log_lines.size() > MAX_LOG_LINES:
		log_lines.pop_front()
	
	if log_text:
		log_text.text = "\n".join(log_lines)
		# Scroll to bottom
		log_text.scroll_vertical = log_text.get_line_count()

func _on_clear_pressed():
	log_lines.clear()
	if log_text:
		log_text.text = ""

