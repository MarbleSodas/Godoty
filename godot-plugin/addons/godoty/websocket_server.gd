extends Node

signal command_received(command: Dictionary)
signal client_connected(ws: WebSocketPeer)

var server: TCPServer
var peers: Array[StreamPeerTCP] = []
var websocket_peers: Array[WebSocketPeer] = []
# Track which WebSocket peers have fired the client_connected signal after OPEN
var ws_open_emitted: Dictionary = {}
var port: int = 9001

func start_server():
	server = TCPServer.new()
	var err = server.listen(port)
	if err != OK:
		push_error("Godoty: Failed to start WebSocket server on port %d: %s" % [port, error_string(err)])
		return



	set_process(true)
	print("Godoty: WebSocket server listening on port %d" % port)

func stop_server():
	set_process(false)

	# Close all connections
	for ws in websocket_peers:
		ws.close()
	websocket_peers.clear()

	for peer in peers:
		peer.disconnect_from_host()
	peers.clear()

	# Stop server
	if server:
		server.stop()
		server = null

	print("Godoty: WebSocket server stopped")


func _process(_delta):
	if not server:
		return

	# Accept new connections
	if server.is_connection_available():
		var peer = server.take_connection()
		peers.append(peer)

		print("Godoty: New TCP connection from ", peer.get_connected_host())

	# Process existing connections
	var i = 0
	while i < peers.size():
		var peer = peers[i]

		# Check if connection is still alive
		if peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
			print("Godoty: TCP connection closed")

			peers.remove_at(i)
			continue

		# Try to upgrade to WebSocket
		if peer.get_available_bytes() > 0:
			var ws = WebSocketPeer.new()
			var err = ws.accept_stream(peer)
			if err == OK:
				websocket_peers.append(ws)
				peers.remove_at(i)
				print("Godoty: WebSocket connection established")

				# Defer client_connected until the WebSocket is fully OPEN
				# (will be emitted in the poll loop when state == STATE_OPEN)

				continue

		i += 1

	# Process WebSocket peers
	i = 0
	while i < websocket_peers.size():
		var ws = websocket_peers[i]
		ws.poll()

		var state = ws.get_ready_state()

		if state == WebSocketPeer.STATE_OPEN:
			# Emit client_connected once per peer when it transitions to OPEN
			var id := ws.get_instance_id()
			if not ws_open_emitted.has(id):
				ws_open_emitted[id] = true
				print("Godoty: WebSocket is OPEN, emitting client_connected")
				client_connected.emit(ws)
			# Receive messages
			while ws.get_available_packet_count() > 0:
				var packet = ws.get_packet()
				var message = packet.get_string_from_utf8()
				_handle_message(message, ws)

		elif state == WebSocketPeer.STATE_CLOSED:

			# Cleanup tracking and remove peer
			var id := ws.get_instance_id()
			if ws_open_emitted.has(id):
				ws_open_emitted.erase(id)
			print("Godoty: WebSocket connection closed")
			websocket_peers.remove_at(i)
			continue

		i += 1

func _handle_message(message: String, ws: WebSocketPeer):


	print("Godoty: Received message: ", message)
	# Parse JSON
	var json = JSON.new()
	var parse_result = json.parse(message)

	if parse_result != OK:
		var error_response = {
			"status": "error",
			"message": "Invalid JSON: %s" % json.get_error_message()
		}
		_send_to_peer(ws, error_response)
		return

	var command = json.data
	if typeof(command) != TYPE_DICTIONARY:
		var error_response = {
			"status": "error",
			"message": "Command must be a JSON object"
		}
		_send_to_peer(ws, error_response)
		return

	# Emit signal for command processing
	command_received.emit(command)

func send_response(response: Dictionary):
	# Send response to all connected clients
	for ws in websocket_peers:
		_send_to_peer(ws, response)

func _send_to_peer(ws: WebSocketPeer, data: Dictionary):
	var json_string = JSON.stringify(data)
	var err = ws.send_text(json_string)
	if err != OK:
		push_error("Godoty: Failed to send response: %s" % error_string(err))

