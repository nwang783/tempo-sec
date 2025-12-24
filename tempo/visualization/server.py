"""
Visualization Server.

Runs a FastAPI application to serve the visualization UI and handle WebSocket connections.
"""

import asyncio
import json
import logging
import os
import webbrowser
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from tempo.visualization.prompt_manager import UserPromptManager
    from tempo.context.store import ContextStore

import uvicorn
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from tempo.visualization.context_processor import (
    build_context_data_from_store,
    process_context_for_ui,
)

logger = logging.getLogger(__name__)

class VisualizationServer:
    """
    WebSocket and HTTP server for agent visualization.
    """
    
    def __init__(
        self, 
        host: str = "127.0.0.1", 
        port: int = 8080, 
        auto_open: bool = True,
        prompt_manager: "UserPromptManager | None" = None,
        stop_event: "asyncio.Event | None" = None,
        persistence_dir: str = "./contexts",
    ):
        self.host = host
        self.port = port
        self.auto_open = auto_open
        self.prompt_manager = prompt_manager
        self.stop_event = stop_event
        self.persistence_dir = persistence_dir
        self.app = FastAPI(title="Tempo Sec Visualization")
        self.active_connections: List[WebSocket] = []
        self._server_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Track current agent state to send to new connections
        self._agent_state: dict = {}
        
        # Track current session ID for context loading
        self._current_session_id: Optional[str] = None
        
        # Reference to the live context store (for real-time context viewing)
        self._context_store: Optional["ContextStore"] = None
        
        # Determine UI directory path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.ui_dir = os.path.join(current_dir, "ui")
        
        # Mount static files if directory exists
        if os.path.exists(self.ui_dir):
            self.app.mount("/static", StaticFiles(directory=self.ui_dir), name="static")
        else:
            logger.warning(f"UI directory not found at {self.ui_dir}")
        
        self._setup_routes()
    
    def set_agent_state(self, state: dict) -> None:
        """Set the current agent state (sent to new WebSocket connections)."""
        self._agent_state = state
    
    def update_agent_state(self, **kwargs) -> None:
        """Update specific fields in the agent state."""
        self._agent_state.update(kwargs)
    
    def clear_agent_state(self) -> None:
        """Clear the agent state (call when agent finishes)."""
        self._agent_state = {}
    
    def set_session_id(self, session_id: str) -> None:
        """Set the current session ID for context loading."""
        self._current_session_id = session_id
    
    def set_context_store(self, context_store: "ContextStore") -> None:
        """Set the live context store for real-time context viewing."""
        self._context_store = context_store
        self._current_session_id = context_store.session_id

    def _setup_routes(self):
        """Configure FastAPI routes."""
        
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.active_connections.append(websocket)
            
            # Send current agent state to new connection (so model shows even on refresh)
            if self._agent_state:
                try:
                    await websocket.send_text(json.dumps({
                        "type": "start",
                        "data": self._agent_state
                    }))
                except Exception as e:
                    logger.debug(f"Failed to send initial state to new connection: {e}")
            
            try:
                # Keep connection open and process incoming messages
                while True:
                    raw = await websocket.receive_text()
                    await self._handle_incoming_message(raw)
            except Exception as e:
                logger.debug(f"WebSocket connection closed: {e}")
            finally:
                if websocket in self.active_connections:
                    self.active_connections.remove(websocket)
        
        @self.app.get("/")
        async def get_root():
            index_path = os.path.join(self.ui_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return {"error": "UI not found. Please ensure tempo/visualization/ui/index.html exists."}
            
        @self.app.get("/health")
        async def health():
            return {"status": "ok", "connections": len(self.active_connections)}
        
        @self.app.get("/api/context")
        async def get_context():
            """Load and return the current session's context data with token estimates."""
            # Try to read from live context store first (real-time during agent run)
            if self._context_store:
                try:
                    context_data = build_context_data_from_store(self._context_store)
                    processed_data = process_context_for_ui(context_data)
                    return JSONResponse(content=processed_data)
                except Exception as e:
                    raise HTTPException(status_code=500, detail=str(e))
            
            # Fall back to reading from disk
            if not self._current_session_id:
                raise HTTPException(status_code=404, detail="No active session")
            
            context_path = Path(self.persistence_dir) / f"{self._current_session_id}.json"
            if not context_path.exists():
                raise HTTPException(status_code=404, detail="Context file not found")
            
            try:
                with open(context_path, "r") as f:
                    context_data = json.load(f)
                
                # Process frames to add token estimates
                processed_data = process_context_for_ui(context_data)
                return JSONResponse(content=processed_data)
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail="Invalid context file")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/sessions")
        async def list_sessions():
            """List all available context sessions."""
            sessions = []
            context_dir = Path(self.persistence_dir)
            if context_dir.exists():
                for file_path in context_dir.glob("*.json"):
                    try:
                        with open(file_path, "r") as f:
                            data = json.load(f)
                        sessions.append({
                            "session_id": data.get("session_id", file_path.stem),
                            "created_at": data.get("created_at"),
                            "updated_at": data.get("updated_at"),
                        })
                    except (json.JSONDecodeError, KeyError):
                        continue
            return JSONResponse(content=sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True))
        
        @self.app.get("/api/context/{session_id}")
        async def get_context_by_id(session_id: str):
            """Load a specific session's context data."""
            # Validate path stays within persistence directory
            try:
                context_path = (Path(self.persistence_dir) / f"{session_id}.json").resolve()
                if not context_path.is_relative_to(Path(self.persistence_dir).resolve()):
                    raise HTTPException(status_code=400, detail="Invalid session ID")
            except (ValueError, OSError):
                raise HTTPException(status_code=400, detail="Invalid session ID")
            if not context_path.exists():
                raise HTTPException(status_code=404, detail="Context file not found")
            
            try:
                with open(context_path, "r") as f:
                    context_data = json.load(f)
                processed_data = process_context_for_ui(context_data)
                return JSONResponse(content=processed_data)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    async def broadcast(self, message: str) -> None:
        """Send message to all connected clients."""
        if not self.active_connections:
            return
            
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
                
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

    async def _handle_incoming_message(self, raw: str) -> None:
        """
        Process incoming WebSocket messages from clients.
        
        Handles 'user_prompt' messages by enqueuing them for the agent.
        """
        try:
            msg = json.loads(raw)
            msg_type = msg.get("type")
            
            if msg_type == "user_prompt" and self.prompt_manager:
                content = msg.get("content", "")
                if content.strip():
                    await self.prompt_manager.enqueue(content)
                    logger.info(f"User prompt enqueued: {content[:50]}...")
            
            # Future: handle other message types (e.g., "pause", "resume")
            elif msg_type == "stop_agent":
                logger.warning("Received stop_agent signal from UI")
                if self.stop_event:
                    self.stop_event.set()
                    await self.broadcast(json.dumps({
                        "type": "finish",
                        "success": False,
                        "error": "Stopped by user"
                    }))
            
            elif msg_type == "ping":
                pass  # Keep-alive, no action needed
                
        except json.JSONDecodeError:
            logger.debug("Received non-JSON WebSocket message, ignoring")
        except Exception as e:
            logger.warning(f"Error handling WebSocket message: {e}")

    async def start(self) -> None:
        """Start the server in a background task."""
        config = uvicorn.Config(
            app=self.app, 
            host=self.host, 
            port=self.port, 
            log_level="warning",
            loop="asyncio"
        )
        server = uvicorn.Server(config)
        
        # Create task for server
        self._server_task = asyncio.create_task(server.serve())
        
        if self.auto_open:
            # wait a bit for server to start
            asyncio.create_task(self._open_browser())
            
        logger.info(f"Visualization server starting at http://{self.host}:{self.port}")

    async def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """
        Wait for at least one WebSocket client to connect.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if a connection was established, False if timeout
        """
        elapsed = 0.0
        interval = 0.1
        while elapsed < timeout:
            if self.active_connections:
                return True
            await asyncio.sleep(interval)
            elapsed += interval
        return False

    async def _open_browser(self):
        """Open browser after a short delay."""
        await asyncio.sleep(1.0)
        webbrowser.open(f"http://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the server."""
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
    

