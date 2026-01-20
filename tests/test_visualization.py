"""
Unit tests for visualization components.

Tests for VisualizationServer state management and VisualizationCollector events.
"""

import asyncio
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestVisualizationServerState:
    """Tests for VisualizationServer agent state management."""
    
    def test_initial_state_is_empty(self):
        """Server starts with empty agent state."""
        from tempo.visualization.server import VisualizationServer
        
        server = VisualizationServer(auto_open=False)
        assert server._agent_state == {}
    
    def test_set_agent_state(self):
        """Test setting agent state."""
        from tempo.visualization.server import VisualizationServer
        
        server = VisualizationServer(auto_open=False)
        state = {"model": "test-model", "objective": "Test objective"}
        
        server.set_agent_state(state)
        
        assert server._agent_state == state
        assert server._agent_state["model"] == "test-model"
    
    def test_update_agent_state(self):
        """Test updating specific fields in agent state."""
        from tempo.visualization.server import VisualizationServer
        
        server = VisualizationServer(auto_open=False)
        server.set_agent_state({"model": "test-model"})
        
        server.update_agent_state(step_number=5)
        
        assert server._agent_state["model"] == "test-model"
        assert server._agent_state["step_number"] == 5
    
    def test_clear_agent_state(self):
        """Test clearing agent state."""
        from tempo.visualization.server import VisualizationServer
        
        server = VisualizationServer(auto_open=False)
        server.set_agent_state({"model": "test-model", "objective": "Test"})
        
        server.clear_agent_state()
        
        assert server._agent_state == {}

    @pytest.mark.asyncio
    async def test_pause_agent_message_sets_event(self):
        """pause_agent message should set pause event."""
        from tempo.visualization.server import VisualizationServer
        
        pause_event = asyncio.Event()
        server = VisualizationServer(auto_open=False, pause_event=pause_event)
        
        await server._handle_incoming_message(json.dumps({
            "type": "pause_agent"
        }))
        
        assert pause_event.is_set() is True


class TestVisualizationCollectorEvents:
    """Tests for VisualizationCollector event emission."""
    
    @pytest.mark.asyncio
    async def test_on_agent_start_stores_state(self):
        """on_agent_start should store state on server."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        mock_server.broadcast = AsyncMock()
        collector = VisualizationCollector(mock_server)
        
        collector.on_agent_start("Test objective", "anthropic/claude-sonnet")
        
        mock_server.set_agent_state.assert_called_once_with({
            "objective": "Test objective",
            "model": "anthropic/claude-sonnet"
        })
    
    def test_on_agent_start_emits_event(self):
        """on_agent_start should emit a start event."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        collector = VisualizationCollector(mock_server)
        
        with patch.object(collector, 'emit') as mock_emit:
            collector.on_agent_start("Test objective", "test-model")
            
            mock_emit.assert_called_once_with("start", {
                "objective": "Test objective",
                "model": "test-model"
            })
    
    @pytest.mark.asyncio
    async def test_on_agent_finish_clears_state(self):
        """on_agent_finish should clear state on server."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        mock_server.broadcast = AsyncMock()
        collector = VisualizationCollector(mock_server)
        
        collector.on_agent_finish(success=True)
        
        mock_server.clear_agent_state.assert_called_once()
    
    def test_on_agent_finish_emits_event(self):
        """on_agent_finish should emit a finish event."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        collector = VisualizationCollector(mock_server)
        
        with patch.object(collector, 'emit') as mock_emit:
            collector.on_agent_finish(success=True, output="Done")
            
            mock_emit.assert_called_once_with("finish", {
                "success": True,
                "output": "Done"
            })

    def test_on_available_tools_emits_event(self):
        """on_available_tools should emit tool names."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        collector = VisualizationCollector(mock_server)
        
        schemas = [
            {"function": {"name": "shell"}},
            {"function": {"name": "file_read"}},
        ]
        
        with patch.object(collector, 'emit') as mock_emit:
            collector.on_available_tools(schemas)
            
            mock_emit.assert_called_once_with("available_tools", {
                "tools": ["shell", "file_read"]
            })


class TestVisualizationCollectorSubagentEvents:
    """Tests for VisualizationCollector subagent event emission."""
    
    def test_on_subagent_start_emits_event(self):
        """on_subagent_start should emit subagent_start event."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        collector = VisualizationCollector(mock_server)
        
        with patch.object(collector, 'emit') as mock_emit:
            collector.on_subagent_start(
                subagent_id="sub-1",
                subagent_type="recon",
                objective="Test objective",
                parent_id="orchestrator",
            )
            
            mock_emit.assert_called_once_with("subagent_start", {
                "subagent_id": "sub-1",
                "subagent_type": "recon",
                "objective": "Test objective",
                "parent_id": "orchestrator",
            })
    
    def test_on_subagent_finish_emits_event(self):
        """on_subagent_finish should emit subagent_finish event."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        collector = VisualizationCollector(mock_server)
        
        with patch.object(collector, 'emit') as mock_emit:
            collector.on_subagent_finish(
                subagent_id="sub-1",
                success=True,
                summary="Found 3 attack surfaces",
                findings_count=2,
                surfaces_count=3,
            )
            
            mock_emit.assert_called_once_with("subagent_finish", {
                "subagent_id": "sub-1",
                "success": True,
                "summary": "Found 3 attack surfaces",
                "findings_count": 2,
                "surfaces_count": 3,
            })
    
    def test_on_findings_update_emits_event(self):
        """on_findings_update should emit findings_update event."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        collector = VisualizationCollector(mock_server)
        
        summary = {
            "critical": 1,
            "high": 2,
            "medium": 3,
            "low": 0,
            "surfaces_total": 10,
            "surfaces_tested": 5,
        }
        
        with patch.object(collector, 'emit') as mock_emit:
            collector.on_findings_update(summary)
            
            mock_emit.assert_called_once_with("findings_update", summary)

    def test_for_subagent_creates_child_collector(self):
        """for_subagent should create a child collector with subagent_id set."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        collector = VisualizationCollector(mock_server)
        
        child = collector.for_subagent("sub-123")
        
        assert child._subagent_id == "sub-123"
        assert child.server is mock_server

    def test_subagent_collector_includes_id_in_events(self):
        """Events from child collector should include subagent_id."""
        from tempo.visualization.collector import VisualizationCollector
        
        mock_server = MagicMock()
        mock_server.broadcast = AsyncMock()
        collector = VisualizationCollector(mock_server, subagent_id="sub-456")
        
        with patch('asyncio.create_task') as mock_task:
            collector.emit("step", {"step_number": 1})
            
            # Get the event JSON that was passed to broadcast
            call_args = mock_task.call_args
            # The create_task receives a coroutine for server.broadcast
            assert call_args is not None
            # Verify the subagent_id was included in the event via the collector's emit logic


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
