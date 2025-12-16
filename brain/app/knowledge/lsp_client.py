"""GDScript LSP Client for Godot Editor integration.

Connects to Godot's GDScript Language Server (port 6005) for real-time
code intelligence: hover docs, completions, and symbol definitions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Global LSP client instance (singleton)
_lsp_client: GDScriptLSPClient | None = None


class GDScriptLSPClient:
    """Client for Godot's GDScript Language Server.
    
    Connects to the LSP server running inside the Godot editor (default port 6005)
    and provides methods for hover documentation, completions, and definitions.
    
    The client uses JSON-RPC 2.0 over TCP socket as per the LSP specification.
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 6005):
        """Initialize the LSP client.
        
        Args:
            host: LSP server host (default: localhost)
            port: LSP server port (default: 6005, Godot's default)
        """
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future] = {}
        self._initialized = False
        self._connected = False
        self._read_task: asyncio.Task | None = None
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to the LSP server."""
        return self._connected and self._writer is not None
    
    async def connect(self, timeout: float = 5.0) -> bool:
        """Connect to the GDScript language server.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            True if connected successfully, False otherwise
        """
        if self._connected:
            return True
        
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=timeout
            )
            self._connected = True
            
            # Start background reader task
            self._read_task = asyncio.create_task(self._read_loop())
            
            # Send initialize request
            await self._initialize()
            
            logger.info(f"Connected to GDScript LSP at {self.host}:{self.port}")
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout connecting to GDScript LSP at {self.host}:{self.port}")
            return False
        except ConnectionRefusedError:
            logger.warning(f"Connection refused to GDScript LSP at {self.host}:{self.port}")
            return False
        except Exception as e:
            logger.error(f"Error connecting to GDScript LSP: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the LSP server."""
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        
        self._reader = None
        self._writer = None
        self._connected = False
        self._initialized = False
        logger.info("Disconnected from GDScript LSP")
    
    async def _initialize(self) -> dict:
        """Send LSP initialize request."""
        result = await self._send_request("initialize", {
            "processId": None,
            "capabilities": {
                "textDocument": {
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "completion": {"completionItem": {"snippetSupport": False}},
                    "definition": {},
                }
            },
            "rootUri": None,
            "initializationOptions": {},
        })
        
        # Send initialized notification
        await self._send_notification("initialized", {})
        self._initialized = True
        
        return result
    
    async def _send_request(self, method: str, params: dict) -> Any:
        """Send a JSON-RPC request and await response.
        
        Args:
            method: LSP method name
            params: Method parameters
            
        Returns:
            Response result or error
        """
        if not self._connected or not self._writer:
            raise ConnectionError("Not connected to LSP server")
        
        self._request_id += 1
        request_id = self._request_id
        
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        
        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._pending_requests[request_id] = future
        
        try:
            # Encode and send message with LSP content-length header
            content = json.dumps(message)
            header = f"Content-Length: {len(content)}\r\n\r\n"
            self._writer.write(header.encode() + content.encode())
            await self._writer.drain()
            
            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=10.0)
            return result
            
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise TimeoutError(f"LSP request '{method}' timed out")
        except Exception as e:
            self._pending_requests.pop(request_id, None)
            raise
    
    async def _send_notification(self, method: str, params: dict) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._connected or not self._writer:
            return
        
        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        
        content = json.dumps(message)
        header = f"Content-Length: {len(content)}\r\n\r\n"
        self._writer.write(header.encode() + content.encode())
        await self._writer.drain()
    
    async def _read_loop(self) -> None:
        """Background task to read LSP responses."""
        if not self._reader:
            return
        
        try:
            while self._connected:
                # Read headers
                headers = {}
                while True:
                    line = await self._reader.readline()
                    if not line:
                        self._connected = False
                        return
                    
                    line_str = line.decode().strip()
                    if not line_str:
                        break
                    
                    if ":" in line_str:
                        key, value = line_str.split(":", 1)
                        headers[key.strip().lower()] = value.strip()
                
                # Read content
                content_length = int(headers.get("content-length", 0))
                if content_length > 0:
                    content = await self._reader.read(content_length)
                    message = json.loads(content.decode())
                    
                    # Handle response
                    if "id" in message and message["id"] in self._pending_requests:
                        future = self._pending_requests.pop(message["id"])
                        if "error" in message:
                            future.set_exception(Exception(message["error"].get("message", "LSP Error")))
                        else:
                            future.set_result(message.get("result"))
                    
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"LSP read loop error: {e}")
            self._connected = False
    
    # =========================================================================
    # Public LSP Methods
    # =========================================================================
    
    def _file_uri(self, file_path: str) -> str:
        """Convert a file path to a file:// URI."""
        path = Path(file_path).resolve()
        return f"file://{path}"
    
    async def get_hover(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> dict | None:
        """Get hover documentation for a position in a GDScript file.
        
        Args:
            file_path: Absolute path to the .gd file
            line: 0-indexed line number
            character: 0-indexed character position
            
        Returns:
            Hover information with 'contents' field, or None if not available
        """
        if not self.is_connected:
            if not await self.connect():
                return None
        
        try:
            result = await self._send_request("textDocument/hover", {
                "textDocument": {"uri": self._file_uri(file_path)},
                "position": {"line": line, "character": character},
            })
            return result
        except Exception as e:
            logger.debug(f"Hover request failed: {e}")
            return None
    
    async def get_completions(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[dict]:
        """Get completion items for a position in a GDScript file.
        
        Args:
            file_path: Absolute path to the .gd file
            line: 0-indexed line number
            character: 0-indexed character position
            
        Returns:
            List of completion items
        """
        if not self.is_connected:
            if not await self.connect():
                return []
        
        try:
            result = await self._send_request("textDocument/completion", {
                "textDocument": {"uri": self._file_uri(file_path)},
                "position": {"line": line, "character": character},
            })
            
            if result is None:
                return []
            
            # Handle both list and CompletionList responses
            if isinstance(result, dict):
                return result.get("items", [])
            return result
            
        except Exception as e:
            logger.debug(f"Completion request failed: {e}")
            return []
    
    async def get_definition(
        self,
        file_path: str,
        line: int,
        character: int,
    ) -> list[dict]:
        """Get definition location(s) for a symbol.
        
        Args:
            file_path: Absolute path to the .gd file
            line: 0-indexed line number
            character: 0-indexed character position
            
        Returns:
            List of location objects with 'uri' and 'range'
        """
        if not self.is_connected:
            if not await self.connect():
                return []
        
        try:
            result = await self._send_request("textDocument/definition", {
                "textDocument": {"uri": self._file_uri(file_path)},
                "position": {"line": line, "character": character},
            })
            
            if result is None:
                return []
            
            # Normalize to list
            if isinstance(result, dict):
                return [result]
            return result
            
        except Exception as e:
            logger.debug(f"Definition request failed: {e}")
            return []
    
    async def notify_did_open(self, file_path: str, content: str) -> None:
        """Notify the server that a document was opened.
        
        Args:
            file_path: Absolute path to the file
            content: Current content of the file
        """
        await self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": self._file_uri(file_path),
                "languageId": "gdscript",
                "version": 1,
                "text": content,
            }
        })
    
    async def notify_did_close(self, file_path: str) -> None:
        """Notify the server that a document was closed."""
        await self._send_notification("textDocument/didClose", {
            "textDocument": {"uri": self._file_uri(file_path)},
        })


def get_lsp_client(host: str = "127.0.0.1", port: int = 6005) -> GDScriptLSPClient:
    """Get the singleton LSP client instance.
    
    Args:
        host: LSP server host
        port: LSP server port (default: 6005)
        
    Returns:
        GDScriptLSPClient instance
    """
    global _lsp_client
    
    if _lsp_client is None:
        _lsp_client = GDScriptLSPClient(host=host, port=port)
    
    return _lsp_client
