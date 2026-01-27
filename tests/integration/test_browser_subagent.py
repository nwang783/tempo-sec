import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.agents.browser_subagent import BrowserSubagent
from tempo.context.store import ContextStore
from tempo.infra.playwright_mcp import PlaywrightMCPClient

@pytest.fixture
def mock_mcp_client():
    client = AsyncMock(spec=PlaywrightMCPClient)
    client._server_ready = True
    client.call_tool.return_value = {
        "success": True,
        "output": "Action completed",
        "raw_result": {"content": [{"type": "text", "text": "Action completed"}]}
    }
    return client

@pytest.fixture
def context():
    return ContextStore()

@pytest.mark.asyncio
async def test_browser_subagent_tool_registration(context):
    """Verify BrowserSubagent registers Playwright tools correctly."""
    agent = BrowserSubagent(objective="Test Objective")
    
    # Create tools
    tools = agent.create_tools(context)
    
    # Check that tools are registered
    assert "browser_navigate" in tools
    assert "browser_click" in tools
    assert "complete_browser_task" in tools
    
@pytest.mark.asyncio
async def test_subagent_tool_execution(context, mock_mcp_client):
    """Verify subagent tools delegate to MCP client."""
    
    # Mock PlaywrightMCPClient where it is imported/used
    # Since it is imported locally inside create_tools, we can patch the source module
    with patch("tempo.infra.playwright_mcp.PlaywrightMCPClient") as MockClientClass:
        MockClientClass.return_value = mock_mcp_client
        
        agent = BrowserSubagent(objective="Test Objective")
        tools = agent.create_tools(context)
        
        # Verify client initialized
        MockClientClass.assert_called_once()
        
        # Execute navigate tool
        navigate_tool = tools.get("browser_navigate")
        assert navigate_tool is not None
        await navigate_tool.execute(url="https://example.com")
        
        # Verify MCP call
        mock_mcp_client.call_tool.assert_called_with(
            "browser_navigate", 
            {"url": "https://example.com"}
        )

@pytest.mark.asyncio
async def test_subagent_complete_tool():
    """Verify complete tool works."""
    from tempo.tools.complete_browser_task import CompleteBrowserTaskTool
    
    tool = CompleteBrowserTaskTool()
    result = await tool.execute(summary="Done", success=True)
    
    assert result.success
    assert result.metadata["task_complete"]
    assert result.metadata["summary"] == "Done"
