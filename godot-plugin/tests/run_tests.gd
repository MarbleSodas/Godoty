#!/usr/bin/env godot
# Run Tests Script
# Usage: godot --headless --script run_tests.gd

extends SceneTree

func _init():
	print("Starting Godoty Plugin Tests...")

	# Load and run the test suite
	var test_script = load("res://tests/plugin_tests.gd").new()
	test_script._run()

	# Quit with appropriate exit code
	quit(0)