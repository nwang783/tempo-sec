"""
Tests for browser subagent email tool integration.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from tempo.agents.browser_subagent import BrowserSubagent
from tempo.context.store import ContextStore


class TestBrowserSubagentEmailTools:
    """Tests for email tool registration in BrowserSubagent."""
    
    def test_email_tools_registered_when_credentials_provided(self):
        """Email tools are registered when IMAP credentials are available."""
        with patch.dict(os.environ, {
            "TEMPO_AGENT_EMAIL": "test@example.com",
            "TEMPO_IMAP_HOST": "imap.gmail.com",
            "TEMPO_IMAP_PASSWORD": "test-password",
        }):
            # Patch PlaywrightMCPClient to avoid starting actual browser
            with patch("tempo.infra.playwright_mcp.PlaywrightMCPClient") as MockClient:
                MockClient.return_value = MagicMock()
                
                agent = BrowserSubagent(objective="Test")
                context = ContextStore()
                tools = agent.create_tools(context)
                
                # Verify email tools are registered
                assert "check_inbox" in tools
                assert "get_email_content" in tools
    
    def test_email_tools_not_registered_when_credentials_missing(self):
        """Email tools are NOT registered when credentials are missing."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear specific env vars that might be set
            env_to_clear = ["TEMPO_AGENT_EMAIL", "TEMPO_IMAP_PASSWORD", "TEMPO_IMAP_HOST"]
            cleared_env = {k: "" for k in env_to_clear}
            
            with patch.dict(os.environ, cleared_env):
                with patch("tempo.infra.playwright_mcp.PlaywrightMCPClient") as MockClient:
                    MockClient.return_value = MagicMock()
                    
                    agent = BrowserSubagent(objective="Test")
                    context = ContextStore()
                    tools = agent.create_tools(context)
                    
                    # Verify email tools are NOT registered
                    assert "check_inbox" not in tools
                    assert "get_email_content" not in tools
    
    def test_email_tools_use_kwarg_credentials(self):
        """Email tools use credentials passed via kwargs over env vars."""
        with patch.dict(os.environ, {
            "TEMPO_AGENT_EMAIL": "env@example.com",
            "TEMPO_IMAP_PASSWORD": "env-password",
        }):
            with patch("tempo.infra.playwright_mcp.PlaywrightMCPClient") as MockClient:
                MockClient.return_value = MagicMock()
                
                agent = BrowserSubagent(objective="Test")
                context = ContextStore()
                
                # Pass credentials via kwargs
                tools = agent.create_tools(
                    context,
                    agent_email="kwarg@example.com",
                    imap_password="kwarg-password",
                )
                
                # Verify email tools are registered
                assert "check_inbox" in tools
                check_inbox = tools.get("check_inbox")
                # The kwarg email should be used
                assert check_inbox.agent_email == "kwarg@example.com"
    
    def test_agent_email_passed_to_init(self):
        """BrowserSubagent stores agent_email from constructor."""
        agent = BrowserSubagent(
            objective="Test",
            agent_email="init@example.com",
        )
        assert agent.agent_email == "init@example.com"


class TestDispatchBrowserSessionPersistence:
    """Tests for session persistence in dispatch_browser (keep_alive was removed)."""
    
    def test_schema_does_not_include_keep_alive(self):
        """Dispatch browser schema should NOT include keep_alive (session manager handles persistence)."""
        from tempo.tools.dispatch_browser import DispatchBrowserTool
        
        tool = DispatchBrowserTool()
        schema = tool.get_schema()
        
        # keep_alive was removed - session manager now handles persistence automatically
        assert "keep_alive" not in schema.parameters["properties"]


class TestSessionStateFormatting:
    """Tests for session state formatting in dispatch_browser."""
    
    def test_format_session_state_with_cookies(self):
        """Session state formatting includes cookies with values."""
        from tempo.tools.dispatch_browser import DispatchBrowserTool
        
        tool = DispatchBrowserTool()
        state = {
            "url": "https://example.com",
            "cookies": [
                {"name": "session", "value": "abc123"},
                {"name": "token", "value": "xyz789"},
            ],
            "local_storage": {},
            "session_storage": {},
        }
        
        result = tool._format_session_state(state)
        
        assert "## Session State Captured" in result
        assert "https://example.com" in result
        assert "`session`" in result
        assert "`abc123`" in result
        assert "`token`" in result
    
    def test_format_session_state_truncates_long_values(self):
        """Long cookie/storage values are truncated."""
        from tempo.tools.dispatch_browser import DispatchBrowserTool
        
        tool = DispatchBrowserTool()
        long_value = "a" * 150
        state = {
            "url": "https://example.com",
            "cookies": [{"name": "long_cookie", "value": long_value}],
            "local_storage": {},
            "session_storage": {},
        }
        
        result = tool._format_session_state(state)
        
        # Should truncate and add ...
        assert "..." in result
        assert long_value not in result  # Full value should not appear
