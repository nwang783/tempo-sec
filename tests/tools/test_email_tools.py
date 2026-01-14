"""
Tests for email inbox tools.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tempo.tools.email_tools import CheckInboxTool, GetEmailContentTool
from tempo.tools.base import ToolCategory


class TestCheckInboxTool:
    """Tests for CheckInboxTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        tool = CheckInboxTool()
        
        assert tool.name == "check_inbox"
        assert tool.category == ToolCategory.NETWORK
        assert "inbox" in tool.description.lower()
    
    def test_schema_has_optional_params(self):
        """Schema has optional parameters."""
        tool = CheckInboxTool()
        schema = tool.get_schema()
        
        assert schema.name == "check_inbox"
        props = schema.parameters["properties"]
        assert "subject_pattern" in props
        assert "from_address" in props
        assert "timeout_seconds" in props
        assert "poll_interval" in props
        assert schema.parameters["required"] == []
    
    @pytest.mark.asyncio
    async def test_execute_fails_without_password(self):
        """Execute fails if IMAP password not configured."""
        tool = CheckInboxTool(
            imap_password=None,
            agent_email="test@example.com",
        )
        
        # Ensure env var is not set
        with patch.dict("os.environ", {}, clear=True):
            result = await tool.execute()
        
        assert not result.success
        assert "IMAP password not configured" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_fails_without_email(self):
        """Execute fails if agent email not configured."""
        tool = CheckInboxTool(
            imap_password="test-password",
            agent_email=None,
        )
        
        # Ensure env var is not set
        with patch.dict("os.environ", {}, clear=True):
            result = await tool.execute()
        
        assert not result.success
        assert "Agent email not configured" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_invalid_regex(self):
        """Execute fails with invalid regex pattern."""
        tool = CheckInboxTool(
            imap_password="test-password",
            agent_email="test@example.com",
        )
        
        result = await tool.execute(subject_pattern="[invalid")
        
        assert not result.success
        assert "Invalid subject pattern" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_returns_emails(self):
        """Execute returns matching emails."""
        tool = CheckInboxTool(
            imap_password="test-password",
            agent_email="test@example.com",
        )
        
        mock_emails = [
            {
                "id": "123",
                "subject": "Verify your account",
                "from": "noreply@example.com",
                "date": "Mon, 1 Jan 2024 12:00:00 +0000",
            }
        ]
        
        with patch.object(tool, "_fetch_emails", return_value=mock_emails):
            result = await tool.execute(subject_pattern="verify")
        
        assert result.success
        assert "Found 1 matching email" in result.output
        assert "Verify your account" in result.output
        assert result.metadata["count"] == 1
    
    @pytest.mark.asyncio
    async def test_execute_timeout_no_emails(self):
        """Execute returns timeout message when no emails found."""
        tool = CheckInboxTool(
            imap_password="test-password",
            agent_email="test@example.com",
        )
        
        with patch.object(tool, "_fetch_emails", return_value=[]):
            result = await tool.execute(timeout_seconds=0)
        
        assert result.success
        assert "No matching emails found" in result.output
        assert result.metadata["timeout"] is True
    
    @pytest.mark.asyncio
    async def test_execute_handles_imap_error(self):
        """Execute handles IMAP connection errors gracefully."""
        tool = CheckInboxTool(
            imap_password="test-password",
            agent_email="test@example.com",
        )
        
        with patch.object(tool, "_fetch_emails", side_effect=Exception("Connection refused")):
            result = await tool.execute()
        
        assert not result.success
        assert "IMAP error" in result.error


class TestGetEmailContentTool:
    """Tests for GetEmailContentTool."""
    
    def test_tool_metadata(self):
        """Tool has correct metadata."""
        tool = GetEmailContentTool()
        
        assert tool.name == "get_email_content"
        assert tool.category == ToolCategory.NETWORK
        assert "verification" in tool.description.lower()
    
    def test_schema_requires_message_id(self):
        """Schema requires message_id parameter."""
        tool = GetEmailContentTool()
        schema = tool.get_schema()
        
        assert schema.name == "get_email_content"
        assert "message_id" in schema.parameters["properties"]
        assert "message_id" in schema.parameters["required"]
    
    @pytest.mark.asyncio
    async def test_execute_fails_without_message_id(self):
        """Execute fails if message_id not provided."""
        tool = GetEmailContentTool(
            imap_password="test-password",
            agent_email="test@example.com",
        )
        
        result = await tool.execute(message_id="")
        
        assert not result.success
        assert "message_id is required" in result.error
    
    @pytest.mark.asyncio
    async def test_execute_fails_without_password(self):
        """Execute fails if IMAP password not configured."""
        tool = GetEmailContentTool(
            imap_password=None,
            agent_email="test@example.com",
        )
        
        with patch.dict("os.environ", {}, clear=True):
            result = await tool.execute(message_id="123")
        
        assert not result.success
        assert "IMAP password not configured" in result.error
    
    def test_extract_links(self):
        """Extract verification links from text."""
        tool = GetEmailContentTool()
        
        text = """
        Please click this link to verify your account:
        https://example.com/verify?token=abc123
        
        Or this one:
        https://example.com/activate/user/12345
        """
        
        links = tool._extract_links(text)
        
        assert len(links) >= 1
        assert any("verify" in link for link in links)
    
    def test_extract_codes(self):
        """Extract verification codes from text."""
        tool = GetEmailContentTool()
        
        text = """
        Thank you for signing up!
        
        Your verification code is: ABC123
        
        Please enter this code to confirm your email address.
        """
        
        codes = tool._extract_codes(text)
        
        assert len(codes) >= 1
        assert "ABC123" in codes
    
    def test_html_to_text(self):
        """Convert HTML to plain text."""
        tool = GetEmailContentTool()
        
        html = """
        <html>
        <body>
        <p>Hello World!</p>
        <br>
        <a href="https://example.com">Click here</a>
        </body>
        </html>
        """
        
        text = tool._html_to_text(html)
        
        assert "Hello World!" in text
        # Tags should be removed
        assert "<p>" not in text
        assert "<a" not in text
    
    @pytest.mark.asyncio
    async def test_execute_returns_content(self):
        """Execute returns email content with extracted data."""
        tool = GetEmailContentTool(
            imap_password="test-password",
            agent_email="test@example.com",
        )
        
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = "Email content here"
        mock_result.metadata = {
            "verification_links": ["https://example.com/verify"],
            "verification_codes": ["ABC123"],
        }
        
        with patch.object(tool, "_fetch_email_content", return_value=mock_result):
            result = await tool.execute(message_id="123")
        
        assert result.success


class TestEmailToolsIntegration:
    """Integration tests for email tools."""
    
    def test_tools_use_correct_category(self):
        """Both tools use NETWORK category."""
        check_tool = CheckInboxTool()
        get_tool = GetEmailContentTool()
        
        assert check_tool.category == ToolCategory.NETWORK
        assert get_tool.category == ToolCategory.NETWORK
    
    def test_tools_accept_env_fallbacks(self):
        """Tools fall back to environment variables."""
        with patch.dict("os.environ", {
            "TEMPO_AGENT_EMAIL": "env@example.com",
            "TEMPO_IMAP_PASSWORD": "env-password",
        }):
            check_tool = CheckInboxTool()
            get_tool = GetEmailContentTool()
            
            assert check_tool.agent_email == "env@example.com"
            assert check_tool.imap_password == "env-password"
            assert get_tool.agent_email == "env@example.com"
            assert get_tool.imap_password == "env-password"
    
    def test_explicit_params_override_env(self):
        """Explicit parameters override environment variables."""
        with patch.dict("os.environ", {
            "TEMPO_AGENT_EMAIL": "env@example.com",
            "TEMPO_IMAP_PASSWORD": "env-password",
        }):
            tool = CheckInboxTool(
                agent_email="explicit@example.com",
                imap_password="explicit-password",
            )
            
            assert tool.agent_email == "explicit@example.com"
            assert tool.imap_password == "explicit-password"
