
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tempo.tools.dispatch_browser import DispatchBrowserTool
from tempo.tools.base import ToolResult

@pytest.mark.asyncio
async def test_dispatch_browser_propagates_state():
    """Verify dispatch_browser tool correctly propagates browser_state from agent findings."""
    
    # Mock the Agent class where it is defined, as it is imported inside the function
    with patch("tempo.agent.runner.Agent") as MockAgentClass:
        # Setup the mock agent instance and its run return value
        mock_agent_instance = MockAgentClass.return_value
        
        # Create a mock AgentResult
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.steps_taken = 5
        mock_result.findings = [{
            "findings": "Task done",
            "browser_state": {"cookies": ["yum"], "url": "test.com"}
        }]
        
        mock_agent_instance.run = AsyncMock(return_value=mock_result)
        
        # Instantiate the tool
        tool = DispatchBrowserTool()
        
        # Execute
        result = await tool.execute(objective="Test")
        
        # Verification
        assert result.success
        assert "browser_state" in result.metadata
        assert result.metadata["browser_state"] == {"cookies": ["yum"], "url": "test.com"}
