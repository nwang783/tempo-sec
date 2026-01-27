"""Integration tests for headless browser with Playwright MCP.

These tests require:
- npx (Node.js)
- Network access

To run:
    python -m pytest tests/integration/test_headless_browser_integration.py -v
"""

import pytest


# Mark all tests in this module as requiring the network
pytestmark = pytest.mark.integration


class TestHeadlessBrowserIntegration:
    """Integration tests for headless browser functionality.
    
    These tests are skipped by default since they require external dependencies.
    Run with: pytest -m integration
    """
    
    @pytest.mark.skip(reason="Requires Playwright MCP server and network access")
    @pytest.mark.asyncio
    async def test_navigate_and_get_snapshot(self):
        """Test full navigation flow with real browser."""
        from tempo.tools.headless_browser_tool import HeadlessBrowserTool
        
        tool = HeadlessBrowserTool()
        
        try:
            # Navigate to example.com
            result = await tool.execute(
                action="navigate",
                params={"url": "https://example.com"},
                purpose="Test navigation",
            )
            
            assert result.success, f"Navigate failed: {result.error}"
            assert result.metadata.get("session_id")
            
            session_id = result.metadata["session_id"]
            
            # Get page snapshot
            result = await tool.execute(
                action="snapshot",
                session_id=session_id,
                purpose="Get page content",
            )
            
            assert result.success, f"Snapshot failed: {result.error}"
            assert "example" in result.output.lower()
            
        finally:
            await tool.cleanup()
            
    @pytest.mark.skip(reason="Requires Playwright MCP server and network access")
    @pytest.mark.asyncio
    async def test_session_persistence_across_calls(self):
        """Test that session state persists across multiple calls."""
        from tempo.tools.headless_browser_tool import HeadlessBrowserTool
        
        tool = HeadlessBrowserTool()
        
        try:
            # First call - navigate
            result1 = await tool.execute(
                action="navigate",
                params={"url": "https://example.com"},
            )
            
            assert result1.success
            session_id = result1.metadata["session_id"]
            
            # Second call - should reuse same session
            result2 = await tool.execute(
                action="snapshot",
                session_id=session_id,
            )
            
            assert result2.success
            # Should have same session ID
            assert result2.metadata["session_id"] == session_id
            
        finally:
            await tool.cleanup()
            
    @pytest.mark.skip(reason="Requires Playwright MCP server and network access")
    @pytest.mark.asyncio
    async def test_network_request_capture(self):
        """Test network request capture for API discovery."""
        from tempo.tools.headless_browser_tool import HeadlessBrowserTool
        
        tool = HeadlessBrowserTool()
        
        try:
            # Navigate to a page with API calls
            result = await tool.execute(
                action="navigate",
                params={"url": "https://httpbin.org/get"},
            )
            
            assert result.success
            session_id = result.metadata["session_id"]
            
            # Get network requests
            result = await tool.execute(
                action="get_network_requests",
                session_id=session_id,
            )
            
            assert result.success
            # Should have captured at least the main request
            assert result.output  # Some network data should be present
            
        finally:
            await tool.cleanup()
            
    @pytest.mark.skip(reason="Requires Playwright MCP server and network access")
    @pytest.mark.asyncio
    async def test_javascript_execution(self):
        """Test JavaScript execution in page context."""
        from tempo.tools.headless_browser_tool import HeadlessBrowserTool
        
        tool = HeadlessBrowserTool()
        
        try:
            # Navigate first
            result = await tool.execute(
                action="navigate",
                params={"url": "https://example.com"},
            )
            
            assert result.success
            session_id = result.metadata["session_id"]
            
            # Execute JavaScript
            result = await tool.execute(
                action="evaluate_js",
                params={"script": "document.title"},
                session_id=session_id,
            )
            
            assert result.success
            assert "example" in result.output.lower()
            
        finally:
            await tool.cleanup()


class TestSubagentHasHeadlessBrowser:
    """Tests to verify subagents have access to headless_browser tool."""
    
    def test_recon_subagent_has_headless_browser(self):
        """Verify ReconSubagent includes headless_browser tool."""
        from tempo.agents.recon_subagent import ReconSubagent
        from tempo.context.store import ContextStore
        from unittest.mock import MagicMock
        
        # Create minimal findings mock
        findings = MagicMock()
        findings.get_summary.return_value = {"target": "test", "total_surfaces": 0}
        findings.get_all_surfaces.return_value = []
        findings.get_all_findings.return_value = []
        
        agent = ReconSubagent(objective="test", findings=findings)
        tools = agent.create_tools(context=ContextStore())
        
        tool_names = tools.list_tools()
        assert "headless_browser" in tool_names
        assert "visual_browser_task" in tool_names  # Should have both
        
    def test_test_subagent_has_headless_browser(self):
        """Verify TestSubagent includes headless_browser tool."""
        from tempo.agents.test_subagent import TestSubagent
        from tempo.context.store import ContextStore
        from unittest.mock import MagicMock
        
        # Create minimal findings mock
        findings = MagicMock()
        findings.get_summary.return_value = {"target": "test", "total_surfaces": 0}
        findings.get_all_surfaces.return_value = []
        findings.get_all_findings.return_value = []
        findings.get_untested_surfaces.return_value = []
        
        agent = TestSubagent(objective="test", findings=findings)
        tools = agent.create_tools(context=ContextStore())
        
        tool_names = tools.list_tools()
        assert "headless_browser" in tool_names
        assert "visual_browser_task" in tool_names  # Should have both
