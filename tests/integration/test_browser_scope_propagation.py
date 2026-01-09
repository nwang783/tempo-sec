"""
Integration tests for browser agent scope propagation.

Tests cover:
- Scope parameter propagation from parent to browser agent
- Scope inclusion in browser agent system prompt
- BrowserTaskTool scope handling
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.tools.browser_task_tool import BrowserTaskTool
from tempo.prompts.builder import PromptBuilder


class TestScopePropagation:
    """Test that scope constraints are properly propagated to browser agent."""

    def test_browser_prompt_includes_scope(self):
        """Test that browser prompt includes scope section when provided."""
        builder = PromptBuilder()
        
        # Create some mock tool schemas
        schemas = [
            {
                "function": {
                    "name": "browser_navigate",
                    "description": "Navigate to URL",
                    "parameters": {"type": "object", "properties": {}},
                }
            },
            {
                "function": {
                    "name": "browser_snapshot",
                    "description": "Take snapshot",
                    "parameters": {"type": "object", "properties": {}},
                }
            },
        ]
        
        scope_content = """
## Allowed Domains
- example.com
- api.example.com

## Restricted Areas
- Do not access /admin
- Do not modify any data
"""
        
        prompt = builder.build_browser_prompt(
            tool_schemas=schemas,
            scope_content=scope_content,
        )
        
        # Verify scope is included
        assert "Scope Constraints" in prompt
        assert "example.com" in prompt
        assert "api.example.com" in prompt
        assert "/admin" in prompt
        assert "Do not modify" in prompt

    def test_browser_prompt_without_scope(self):
        """Test that browser prompt works without scope."""
        builder = PromptBuilder()
        
        schemas = [
            {
                "function": {
                    "name": "browser_navigate",
                    "description": "Navigate to URL",
                    "parameters": {"type": "object", "properties": {}},
                }
            },
        ]
        
        prompt = builder.build_browser_prompt(
            tool_schemas=schemas,
            scope_content=None,
        )
        
        # Should not have scope section
        assert "Scope Constraints" not in prompt
        # Should still have the rest of the prompt
        assert "Visual Browser Agent" in prompt

    def test_browser_prompt_with_state_instructions(self):
        """Test that browser prompt includes state loading/saving instructions."""
        builder = PromptBuilder()
        
        schemas = [
            {
                "function": {
                    "name": "browser_navigate",
                    "description": "Navigate to URL",
                    "parameters": {"type": "object", "properties": {}},
                }
            },
        ]
        
        prompt = builder.build_browser_prompt(
            tool_schemas=schemas,
            state_name="admin_session",
            save_state_as="updated_admin",
        )
        
        # Verify state instructions are included
        assert "Initial State" in prompt
        assert "admin_session" in prompt
        assert "Save State" in prompt
        assert "updated_admin" in prompt

    def test_browser_task_tool_schema_includes_scope(self):
        """Test that BrowserTaskTool schema includes scope parameter."""
        tool = BrowserTaskTool()
        schema = tool.get_schema()
        
        assert "scope" in schema.parameters["properties"]
        assert "constraints" in schema.parameters["properties"]["scope"]["description"].lower()

    def test_browser_task_tool_schema_includes_state_params(self):
        """Test that BrowserTaskTool schema includes state parameters."""
        tool = BrowserTaskTool()
        schema = tool.get_schema()
        
        # Check state_name parameter
        assert "state_name" in schema.parameters["properties"]
        state_name_desc = schema.parameters["properties"]["state_name"]["description"]
        assert "load" in state_name_desc.lower() or "saved" in state_name_desc.lower()
        
        # Check save_state_as parameter
        assert "save_state_as" in schema.parameters["properties"]
        save_state_desc = schema.parameters["properties"]["save_state_as"]["description"]
        assert "save" in save_state_desc.lower()


class TestBrowserTaskToolIntegration:
    """Integration tests for BrowserTaskTool scope and state handling."""

    @pytest.mark.asyncio
    async def test_browser_task_creates_agent_with_scope(self):
        """Test that BrowserTaskTool passes scope to browser agent."""
        tool = BrowserTaskTool(headless=True)
        
        # Patch at the location where BrowserAgent is imported inside execute()
        with patch("tempo.agents.browser.BrowserAgent") as mock_browser_agent:
            with patch("tempo.agent.runner.Agent") as mock_agent:
                with patch("tempo.infra.llm.LiteLLMClient"):
                    # Setup mock browser agent definition
                    mock_def = MagicMock()
                    mock_def.model = "openai/gpt-4o-mini"
                    mock_def.create_tools.return_value = MagicMock()
                    mock_def.create_tools.return_value.get_schemas.return_value = []
                    mock_def.build_system_prompt.return_value = "System prompt"
                    mock_def.build_objective.return_value = "Test objective"
                    mock_browser_agent.return_value = mock_def
                    
                    # Setup mock agent runner
                    mock_runner = MagicMock()
                    mock_runner.run = AsyncMock(return_value=MagicMock(
                        success=True,
                        steps_taken=3,
                        findings=[{"findings": "Test completed"}],
                        error=None,
                    ))
                    mock_agent.return_value = mock_runner
                    
                    # Execute with scope
                    await tool.execute(
                        task="Test the login page",
                        url="https://example.com",
                        scope="Only test example.com, do not access external links",
                    )
                    
                    # Verify BrowserAgent was created with scope
                    mock_browser_agent.assert_called_once()
                    call_kwargs = mock_browser_agent.call_args[1]
                    assert call_kwargs.get("scope") == "Only test example.com, do not access external links"

    @pytest.mark.asyncio
    async def test_browser_task_creates_agent_with_state_name(self):
        """Test that BrowserTaskTool passes state_name to browser agent."""
        tool = BrowserTaskTool(headless=True)
        
        with patch("tempo.agents.browser.BrowserAgent") as mock_browser_agent:
            with patch("tempo.agent.runner.Agent") as mock_agent:
                with patch("tempo.infra.llm.LiteLLMClient"):
                    mock_def = MagicMock()
                    mock_def.model = "openai/gpt-4o-mini"
                    mock_def.create_tools.return_value = MagicMock()
                    mock_def.create_tools.return_value.get_schemas.return_value = []
                    mock_def.build_system_prompt.return_value = "System prompt"
                    mock_def.build_objective.return_value = "Test objective"
                    mock_browser_agent.return_value = mock_def
                    
                    mock_runner = MagicMock()
                    mock_runner.run = AsyncMock(return_value=MagicMock(
                        success=True,
                        steps_taken=3,
                        findings=[{"findings": "Test completed"}],
                        error=None,
                    ))
                    mock_agent.return_value = mock_runner
                    
                    await tool.execute(
                        task="Access admin panel",
                        state_name="admin_session",
                    )
                    
                    call_kwargs = mock_browser_agent.call_args[1]
                    assert call_kwargs.get("state_name") == "admin_session"

    @pytest.mark.asyncio
    async def test_browser_task_creates_agent_with_save_state_as(self):
        """Test that BrowserTaskTool passes save_state_as to browser agent."""
        tool = BrowserTaskTool(headless=True)
        
        with patch("tempo.agents.browser.BrowserAgent") as mock_browser_agent:
            with patch("tempo.agent.runner.Agent") as mock_agent:
                with patch("tempo.infra.llm.LiteLLMClient"):
                    mock_def = MagicMock()
                    mock_def.model = "openai/gpt-4o-mini"
                    mock_def.create_tools.return_value = MagicMock()
                    mock_def.create_tools.return_value.get_schemas.return_value = []
                    mock_def.build_system_prompt.return_value = "System prompt"
                    mock_def.build_objective.return_value = "Test objective"
                    mock_browser_agent.return_value = mock_def
                    
                    mock_runner = MagicMock()
                    mock_runner.run = AsyncMock(return_value=MagicMock(
                        success=True,
                        steps_taken=3,
                        findings=[{"findings": "Logged in successfully"}],
                        error=None,
                    ))
                    mock_agent.return_value = mock_runner
                    
                    await tool.execute(
                        task="Log in as admin",
                        url="https://example.com/login",
                        save_state_as="new_admin_session",
                    )
                    
                    call_kwargs = mock_browser_agent.call_args[1]
                    assert call_kwargs.get("save_state_as") == "new_admin_session"

    @pytest.mark.asyncio
    async def test_browser_task_result_includes_state_metadata(self):
        """Test that BrowserTaskTool result includes state-related metadata."""
        tool = BrowserTaskTool(headless=True)
        
        with patch("tempo.agents.browser.BrowserAgent") as mock_browser_agent:
            with patch("tempo.agent.runner.Agent") as mock_agent:
                with patch("tempo.infra.llm.LiteLLMClient"):
                    mock_def = MagicMock()
                    mock_def.model = "openai/gpt-4o-mini"
                    mock_def.create_tools.return_value = MagicMock()
                    mock_def.create_tools.return_value.get_schemas.return_value = []
                    mock_def.build_system_prompt.return_value = "System prompt"
                    mock_def.build_objective.return_value = "Test objective"
                    mock_browser_agent.return_value = mock_def
                    
                    mock_runner = MagicMock()
                    mock_runner.run = AsyncMock(return_value=MagicMock(
                        success=True,
                        steps_taken=5,
                        findings=[{"findings": "Task completed"}],
                        error=None,
                    ))
                    mock_agent.return_value = mock_runner
                    
                    result = await tool.execute(
                        task="Test with state",
                        state_name="existing_session",
                        save_state_as="updated_session",
                    )
                    
                    assert result.success
                    assert result.metadata.get("state_loaded") == "existing_session"
                    assert result.metadata.get("state_saved") == "updated_session"


class TestPromptBuilderScopeSection:
    """Test PromptBuilder scope section generation."""

    def test_build_scope_section_with_content(self):
        """Test _build_scope_section with scope content."""
        builder = PromptBuilder()
        
        scope_content = "Only test example.com domain"
        section = builder._build_scope_section(scope_content)
        
        assert "## Scope Constraints" in section
        assert "Only test example.com domain" in section

    def test_build_scope_section_without_content(self):
        """Test _build_scope_section returns empty string when no content."""
        builder = PromptBuilder()
        
        section = builder._build_scope_section(None)
        assert section == ""
        
        section = builder._build_scope_section("")
        assert section == ""

    def test_recon_subagent_prompt_includes_scope(self):
        """Test that recon subagent prompt includes scope when provided."""
        builder = PromptBuilder()
        
        schemas = [
            {"function": {"name": "shell", "description": "Run commands"}},
        ]
        
        prompt = builder.build_recon_subagent_prompt(
            tool_schemas=schemas,
            objective="Find endpoints",
            findings_context="No findings yet",
            scope_content="Only scan example.com, port 80 and 443",
        )
        
        assert "Scope Constraints" in prompt
        assert "example.com" in prompt
        assert "80" in prompt

    def test_test_subagent_prompt_includes_scope(self):
        """Test that test subagent prompt includes scope when provided."""
        builder = PromptBuilder()
        
        schemas = [
            {"function": {"name": "shell", "description": "Run commands"}},
        ]
        
        prompt = builder.build_test_subagent_prompt(
            tool_schemas=schemas,
            objective="Test for XSS",
            attack_surfaces_context="1 form to test",
            scope_content="Do not test production data endpoints",
        )
        
        assert "Scope Constraints" in prompt
        assert "production data" in prompt


class TestBrowserAgentScopeIntegration:
    """Test BrowserAgent scope integration."""

    def test_browser_agent_accepts_scope_parameter(self):
        """Test that BrowserAgent accepts scope parameter."""
        from tempo.agents.browser import BrowserAgent
        
        agent = BrowserAgent(
            task="Test login",
            url="https://example.com",
            scope="Only test login form, do not submit real credentials",
        )
        
        assert agent.scope == "Only test login form, do not submit real credentials"

    def test_browser_agent_build_system_prompt_uses_scope(self):
        """Test that BrowserAgent.build_system_prompt includes scope."""
        from tempo.agents.browser import BrowserAgent
        
        agent = BrowserAgent(
            task="Test search",
            url="https://example.com",
            scope="Do not access external domains",
        )
        
        builder = PromptBuilder()
        prompt = agent.build_system_prompt(
            prompts=builder,
            tool_schemas=[],
            scope_description="Do not access external domains",
        )
        
        # The prompt should include the scope
        assert "Scope Constraints" in prompt or "external domains" in prompt

    def test_browser_agent_build_objective_mentions_state(self):
        """Test that BrowserAgent.build_objective mentions state when applicable."""
        from tempo.agents.browser import BrowserAgent
        
        # With state loading
        agent_load = BrowserAgent(
            task="Access admin panel",
            state_name="admin_session",
        )
        objective_load = agent_load.build_objective()
        assert "admin_session" in objective_load or "load" in objective_load.lower()
        
        # With state saving
        agent_save = BrowserAgent(
            task="Login and save",
            save_state_as="new_session",
        )
        objective_save = agent_save.build_objective()
        assert "new_session" in objective_save or "save" in objective_save.lower()

