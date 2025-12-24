"""
Unit tests for visualization API endpoints.

Tests for the /api/context, /api/sessions, and /api/context/{session_id} endpoints.
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


class TestVisualizationAPI:
    """Tests for visualization server API endpoints."""
    
    @pytest.fixture
    def temp_persistence_dir(self):
        """Create a temporary directory for test context files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def server(self, temp_persistence_dir):
        """Create a VisualizationServer instance for testing."""
        from tempo.visualization.server import VisualizationServer
        
        return VisualizationServer(
            auto_open=False,
            persistence_dir=temp_persistence_dir,
        )
    
    @pytest.fixture
    def client(self, server):
        """Create a test client for the server."""
        return TestClient(server.app)
    
    def test_get_context_no_session_returns_404(self, client, server):
        """GET /api/context returns 404 when no session is active."""
        response = client.get("/api/context")
        assert response.status_code == 404
        assert "No active session" in response.json()["detail"]
    
    def test_get_context_with_session_id_but_no_file_returns_404(self, client, server):
        """GET /api/context returns 404 when session ID set but file doesn't exist."""
        server.set_session_id("nonexistent-session")
        response = client.get("/api/context")
        assert response.status_code == 404
    
    def test_get_context_with_live_store(self, client, server, temp_persistence_dir):
        """GET /api/context returns data from live context store."""
        from tempo.context.store import ContextStore
        from tempo.context.frame import MessageRole
        
        # Create a live context store with some data
        context = ContextStore(persistence_dir=temp_persistence_dir)
        context.add_message(MessageRole.SYSTEM, "Test system message")
        context.add_message(MessageRole.USER, "Test user message")
        
        server.set_context_store(context)
        
        response = client.get("/api/context")
        assert response.status_code == 200
        
        data = response.json()
        assert "session_id" in data
        assert "messages" in data
        assert "total_tokens" in data
        assert len(data["messages"]) == 2
    
    def test_list_sessions_empty(self, client, temp_persistence_dir):
        """GET /api/sessions returns empty list when no sessions exist."""
        response = client.get("/api/sessions")
        assert response.status_code == 200
        assert response.json() == []
    
    def test_list_sessions_returns_sessions(self, client, temp_persistence_dir):
        """GET /api/sessions returns list of available sessions."""
        # Create some test session files
        session1 = {"session_id": "session-1", "created_at": "2024-01-01", "updated_at": "2024-01-02", "frames": {}}
        session2 = {"session_id": "session-2", "created_at": "2024-01-02", "updated_at": "2024-01-03", "frames": {}}
        
        (Path(temp_persistence_dir) / "session-1.json").write_text(json.dumps(session1))
        (Path(temp_persistence_dir) / "session-2.json").write_text(json.dumps(session2))
        
        response = client.get("/api/sessions")
        assert response.status_code == 200
        
        sessions = response.json()
        assert len(sessions) == 2
        # Should be sorted by updated_at descending
        assert sessions[0]["session_id"] == "session-2"
    
    def test_get_context_by_id_valid(self, client, temp_persistence_dir):
        """GET /api/context/{session_id} returns valid session data."""
        session_data = {
            "session_id": "valid-session",
            "current_frame_id": "frame-1",
            "frames": {
                "frame-1": {
                    "id": "frame-1",
                    "parent_id": None,
                    "messages": [
                        {"role": "system", "content": "Hello", "timestamp": "2024-01-01"}
                    ],
                    "tool_calls": [],
                }
            }
        }
        (Path(temp_persistence_dir) / "valid-session.json").write_text(json.dumps(session_data))
        
        response = client.get("/api/context/valid-session")
        assert response.status_code == 200
        
        data = response.json()
        assert data["session_id"] == "valid-session"
        assert len(data["messages"]) == 1
    
    def test_get_context_by_id_not_found(self, client):
        """GET /api/context/{session_id} returns 404 for nonexistent session."""
        response = client.get("/api/context/nonexistent")
        assert response.status_code == 404
    
    def test_get_context_by_id_path_traversal_blocked(self, client):
        """GET /api/context/{session_id} blocks path traversal attempts."""
        # Basic path traversal - should return 400 (invalid) or 404 (file not found after resolution)
        response = client.get("/api/context/../../../etc/passwd")
        # Either response indicates the attack was blocked
        assert response.status_code in (400, 404)
        
    def test_get_context_by_id_encoded_traversal_blocked(self, client):
        """GET /api/context/{session_id} blocks URL-encoded path traversal."""
        # URL-encoded path traversal (%2E = ., %2F = /)
        response = client.get("/api/context/%2E%2E%2F%2E%2E%2Fetc%2Fpasswd")
        # FastAPI/Starlette decodes the URL before passing to the handler
        # so our pathlib check should catch this
        assert response.status_code in (400, 404)  # Either invalid or not found is acceptable


class TestProcessContextForUI:
    """Tests for _process_context_for_ui method."""
    
    @pytest.fixture
    def server(self):
        """Create a VisualizationServer instance."""
        from tempo.visualization.server import VisualizationServer
        
        return VisualizationServer(auto_open=False)
    
    def test_token_estimation(self, server):
        """Token estimation uses 4 chars per token."""
        assert server._estimate_tokens("") == 0
        assert server._estimate_tokens("1234") == 1
        assert server._estimate_tokens("12345678") == 2
    
    def test_process_context_empty(self, server):
        """Processing empty context returns proper structure."""
        context_data = {
            "session_id": "test",
            "current_frame_id": None,
            "frames": {},
        }
        
        result = server._process_context_for_ui(context_data)
        
        assert result["session_id"] == "test"
        assert result["messages"] == []
        assert result["total_tokens"] == 0
    
    def test_process_context_with_messages(self, server):
        """Processing context with messages computes tokens."""
        context_data = {
            "session_id": "test",
            "current_frame_id": "frame-1",
            "frames": {
                "frame-1": {
                    "id": "frame-1",
                    "parent_id": None,
                    "messages": [
                        {"role": "system", "content": "A" * 100, "timestamp": "2024-01-01"},
                    ],
                    "tool_calls": [],
                }
            },
        }
        
        result = server._process_context_for_ui(context_data)
        
        assert len(result["messages"]) == 1
        assert result["messages"][0]["tokens"] == 25  # 100 chars / 4
        assert result["total_tokens"] == 25
    
    def test_process_context_summarized_tool_call(self, server):
        """Processing summarized tool calls shows tokens saved."""
        context_data = {
            "session_id": "test",
            "current_frame_id": "frame-1",
            "frames": {
                "frame-1": {
                    "id": "frame-1",
                    "parent_id": None,
                    "messages": [],
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "tool_name": "shell_execute",
                            "input": {"command": "ls"},
                            "raw_output": "A" * 1000,  # 250 tokens raw
                            "summary": "Listed files",  # ~3 tokens summary
                            "timestamp": "2024-01-01",
                        }
                    ],
                }
            },
        }
        
        result = server._process_context_for_ui(context_data)
        
        assert len(result["messages"]) == 1
        tc = result["messages"][0]
        assert tc["type"] == "tool_call"
        assert tc["is_summarized"] is True
        assert tc["tokens_saved"] > 0
        assert tc["display_output"] == "Listed files"


class TestExportForVisualization:
    """Tests for ContextStore.export_for_visualization method."""
    
    def test_export_returns_valid_structure(self):
        """export_for_visualization returns expected structure."""
        from tempo.context.store import ContextStore
        
        context = ContextStore()
        result = context.export_for_visualization()
        
        assert "session_id" in result
        assert "current_frame_id" in result
        assert "frames" in result
        assert isinstance(result["frames"], dict)
    
    def test_export_includes_current_frame_path(self):
        """export_for_visualization includes frames from root to current."""
        from tempo.context.store import ContextStore
        from tempo.context.frame import MessageRole
        
        context = ContextStore()
        context.add_message(MessageRole.SYSTEM, "Test message")
        
        result = context.export_for_visualization()
        
        # Should have at least the root frame
        assert len(result["frames"]) >= 1
        assert result["current_frame_id"] in result["frames"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
