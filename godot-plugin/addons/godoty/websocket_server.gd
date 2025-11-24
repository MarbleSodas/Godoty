extends Node

signal command_received(command: Dictionary)
signal client_connected(ws: WebSocketPeer)

var server: TCPServer
var peers: Array[StreamPeerTCP] = []
# Mapping from StreamPeerTCP (instance id or ref) to the pending WebSocketPeer
var pending_handshakes: Dictionary = {} 
var websocket_peers: Array[WebSocketPeer] = []
var ws_open_emitted: Dictionary = {}
var port: int = 9001

func start_server() -> void:
	server = TCPServer.new()
	var err = server.listen(port)
	if err != OK:
		push_error("Godoty: Failed to start WebSocket server on port %d: %s" % [port, error_string(err)])
		return

	set_process(true)
	print("Godoty: WebSocket server listening on port %d" % port)

func stop_server() -> void:
	set_process(false)
	_close_all_connections()
	_stop_server_instance()

func _close_all_connections() -> void:
	for ws in websocket_peers:
		ws.close()
	websocket_peers.clear()
	
	# Clear pending handshakes
	pending_handshakes.clear()

	for peer in peers:
		peer.disconnect_from_host()
	peers.clear()

func _stop_server_instance() -> void:
	if server:
		server.stop()
		server = null
	print("Godoty: WebSocket server stopped")


func _process(_delta: float) -> void:
	if not server:
		return

	_accept_new_connections()
	_process_tcp_peers()
	_process_websocket_peers()

func _accept_new_connections() -> void:
	if server.is_connection_available():
		var peer = server.take_connection()
		peers.append(peer)
		print("Godoty: New TCP connection from %s" % peer.get_connected_host())

func _process_tcp_peers() -> void:
	var i = 0
	while i < peers.size():
		var peer = peers[i]

		if not _is_tcp_connected(peer):
			print("Godoty: TCP connection closed during handshake/wait")
			# Cleanup pending handshake if exists
			if pending_handshakes.has(peer):
				pending_handshakes.erase(peer)
			peers.remove_at(i)
			continue

		# Try to upgrade or continue handshake
		if _try_upgrade_to_websocket(peer, i):
			# If returns true, the peer was removed from 'peers' list and moved to 'websocket_peers'
			# So we don't increment i, as the array shifted
			continue

		i += 1

func _process_websocket_peers() -> void:
	var i = 0
	while i < websocket_peers.size():
		var ws = websocket_peers[i]
		ws.poll()

		var state = ws.get_ready_state()

		if state == WebSocketPeer.STATE_OPEN:
			_handle_websocket_open(ws)
			_process_websocket_messages(ws)
		elif state == WebSocketPeer.STATE_CLOSED:
			_cleanup_websocket_peer(ws, i)
			continue

		i += 1

func _is_tcp_connected(peer: StreamPeerTCP) -> bool:
	return peer.get_status() == StreamPeerTCP.STATUS_CONNECTED

func _try_upgrade_to_websocket(peer: StreamPeerTCP, index: int) -> bool:
	var ws: WebSocketPeer
	
	# Check if we already have a pending handshake for this peer
	if pending_handshakes.has(peer):
		ws = pending_handshakes[peer]
	else:
		# Start new handshake
		ws = WebSocketPeer.new()
		pending_handshakes[peer] = ws
	
	# Attempt/Continue handshake
	# accept_stream needs to be called repeatedly until it returns OK (connected) or Error
	# It returns ERR_UNAVAILABLE if it needs more data/time
	var err = ws.accept_stream(peer)
	
	if err == OK:
		# Handshake complete!
		websocket_peers.append(ws)
		pending_handshakes.erase(peer)
		peers.remove_at(index)
		print("Godoty: WebSocket connection established")
		return true
		
	elif err == ERR_UNAVAILABLE:
		# Still negotiating, keep in pending
		return false
		
	else:
		# Handshake failed
		print("Godoty: WebSocket upgrade failed: ", error_string(err))
		pending_handshakes.erase(peer)
		peers.remove_at(index)
		return true

func _handle_websocket_open(ws: WebSocketPeer) -> void:
	var id := ws.get_instance_id()
	if not ws_open_emitted.has(id):
		ws_open_emitted[id] = true
		print("Godoty: WebSocket is OPEN, emitting client_connected")
		client_connected.emit(ws)

func _process_websocket_messages(ws: WebSocketPeer) -> void:
	while ws.get_available_packet_count() > 0:
		var packet = ws.get_packet()
		var message = packet.get_string_from_utf8()
		_handle_message(message, ws)

func _cleanup_websocket_peer(ws: WebSocketPeer, index: int) -> void:
	var id := ws.get_instance_id()
	if ws_open_emitted.has(id):
		ws_open_emitted.erase(id)
	print("Godoty: WebSocket connection closed")
	websocket_peers.remove_at(index)

func _handle_message(message: String, ws: WebSocketPeer) -> void:
	print("Godoty: Received message: ", message)

	var json = JSON.new()
	var parse_result = json.parse(message)

	if parse_result != OK:
		_send_error_response(ws, "Invalid JSON: %s" % json.get_error_message())
		return

	var command = json.data
	if typeof(command) != TYPE_DICTIONARY:
		_send_error_response(ws, "Command must be a JSON object")
		return

	command_received.emit(command)

func send_response(response: Dictionary) -> void:
	for ws in websocket_peers:
		_send_to_peer(ws, response)

func _send_to_peer(ws: WebSocketPeer, data: Dictionary) -> void:
	var json_string = JSON.stringify(data)
	var err = ws.send_text(json_string)
	if err != OK:
		push_error("Godoty: Failed to send response: %s" % error_string(err))

func _send_error_response(ws: WebSocketPeer, message: String) -> void:
	_send_to_peer(ws, {
		"status": "error",
		"message": message
	})
