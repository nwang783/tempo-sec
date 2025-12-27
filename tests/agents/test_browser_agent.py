"""Tests for browser agent and related tools."""

import pytest

from tempo.agents.browser import BrowserAgent
from tempo.context.store import ContextStore
from tempo.tools.complete_browser_task import CompleteBrowserTaskTool
from tempo.agent.step_handler import StepHandler, SpecialToolResult
from tempo.context.frame import ToolCall
from tempo.prompts.builder import PromptBuilder


class TestBrowserAgent:
    """Tests for BrowserAgent definition."""
    
    def test_init_with_task(self):
        """Test browser agent initialization."""
        agent = BrowserAgent(task="Find the login form", url="https://example.com")
        
        assert agent.task == "Find the login form"
        assert agent.url == "https://example.com"
        assert agent.name == "browser"
    
    def test_init_without_url(self):
        """Test browser agent initialization without URL."""
        agent = BrowserAgent(task="Navigate and find forms")
        
        assert agent.task == "Navigate and find forms"
        assert agent.url is None
    
    def test_model_is_fast(self):
        """Test that browser agent uses a fast model."""
        agent = BrowserAgent(task="test")
        
        # Should use a lightweight model for fast browser tasks
        assert "mini" in agent.model or "4o" in agent.model
    
    def test_create_tools_only_browser_tools(self):
        """Test that browser agent only has browser tools + completion."""
        agent = BrowserAgent(task="test")
        context = ContextStore()
        
        tools = agent.create_tools(context=context)
        tool_names = tools.list_tools()
        
        # Should have browser tools
        assert "browser_navigate" in tool_names
        assert "browser_snapshot" in tool_names
        assert "browser_click" in tool_names
        assert "browser_type" in tool_names
        assert "browser_fill_form" in tool_names
        
        # Should have completion tool
        assert "complete_browser_task" in tool_names
        
        # Should NOT have shell, file, or meta tools
        assert "shell" not in tool_names
        assert "file_read" not in tool_names
        assert "file_write" not in tool_names
        assert "summarize_previous_tool_output" not in tool_names
        assert "transition_phase" not in tool_names
    
    def test_build_objective_includes_task(self):
        """Test that objective includes the task description."""
        agent = BrowserAgent(task="Find all input fields", url="https://example.com")
        
        objective = agent.build_objective()
        
        assert "Find all input fields" in objective
        assert "https://example.com" in objective
    
    def test_build_objective_without_url(self):
        """Test objective when no URL is provided."""
        agent = BrowserAgent(task="Navigate and find sensitive data")
        
        objective = agent.build_objective()
        
        assert "Navigate and find sensitive data" in objective
        assert "Navigate as needed" in objective


class TestCompleteBrowserTaskTool:
    """Tests for CompleteBrowserTaskTool."""
    
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful browser task completion."""
        tool = CompleteBrowserTaskTool()
        
        result = await tool.execute(
            findings="Found login form with username and password fields",
            success=True,
            extracted_data="Fields: username, password",
        )
        
        assert result.success is True
        assert "Found login form" in result.output
        assert result.metadata.get("browser_task_complete") is True
        assert result.metadata.get("task_success") is True
    
    @pytest.mark.asyncio
    async def test_execute_failure(self):
        """Test failed browser task completion."""
        tool = CompleteBrowserTaskTool()
        
        result = await tool.execute(
            findings="Could not find the requested element",
            success=False,
        )
        
        assert result.success is True  # Tool execution succeeds
        assert result.metadata.get("task_success") is False  # Task failed
        assert "unsuccessful" in result.output.lower()
    
    def test_get_schema(self):
        """Test that schema is properly formatted."""
        tool = CompleteBrowserTaskTool()
        schema = tool.get_schema()
        
        assert schema.name == "complete_browser_task"
        assert "findings" in schema.parameters.get("required", [])


class TestStepHandlerBrowserTaskCompletion:
    """Tests for step handler processing of complete_browser_task."""
    
    def test_process_complete_browser_task(self):
        """Test that complete_browser_task is recognized as special tool."""
        from tempo.tools.registry import ToolRegistry
        
        tools = ToolRegistry()
        handler = StepHandler(tools)
        
        tool_call = ToolCall(
            id="test-123",
            tool_name="complete_browser_task",
            input={"findings": "Found forms"},
            metadata={
                "browser_task_complete": True,
                "findings": "Found login and search forms",
                "task_success": True,
                "extracted_data": "login_form, search_form",
            },
        )
        
        result = handler.process_special_tool(tool_call)
        
        assert result is not None
        assert isinstance(result, SpecialToolResult)
        assert result.tool_name == "complete_browser_task"
        assert result.should_continue is False  # Stops the agent
        assert result.findings is not None
        assert result.findings.get("success") is True


class TestPromptBuilderBrowserPrompt:
    """Tests for browser prompt building."""
    
    def test_build_browser_prompt(self):
        """Test that browser prompt is built correctly."""
        builder = PromptBuilder()
        
        mock_schemas = [
            {"function": {"name": "browser_navigate", "description": "Navigate to URL"}},
        ]
        
        prompt = builder.build_browser_prompt(tool_schemas=mock_schemas)
        
        assert "Browser" in prompt
        assert "browser_navigate" in prompt
        assert "complete_browser_task" in prompt.lower() or "complete" in prompt.lower()


class TestAgentRegistration:
    """Tests for browser agent registration."""
    
    def test_browser_agent_registered(self):
        """Test that browser agent is properly registered."""
        from tempo.agents import list_agents, get_agent_class
        
        agents = list_agents()
        
        assert "browser" in agents
        
        agent_class = get_agent_class("browser")
        assert agent_class == BrowserAgent
