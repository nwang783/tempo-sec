"""Tests for tempo/agent/runner.py."""

import pytest

from tempo.agent.config import AgentConfig
from tempo.agent.runner import Agent, AgentResult, StepResult
from tempo.context.store import ContextStore
from tempo.prompts.phases import Phase
from tempo.tools.registry import ToolRegistry
from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.infra.llm import LLMResponse


class MockLLMClient:
    """Mock LLM client for testing."""
    
    def __init__(self, responses: list[LLMResponse] | None = None):
        self.responses = responses or []
        self.call_count = 0
    
    async def complete(self, messages, tools=None):
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        
        # Default: signal finish
        return LLMResponse(content="Done", tool_calls=[])


class DummyTool(Tool):
    """Dummy tool for testing."""
    
    name = "dummy"
    description = "A dummy tool"
    category = ToolCategory.EXECUTION
    
    async def execute(self, message: str = "test", purpose: str = "") -> ToolResult:
        return ToolResult(success=True, output=f"Echo: {message}")
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
            },
        )


class TestStepResult:
    """Tests for StepResult dataclass."""
    
    def test_create(self):
        """Test creating a step result."""
        result = StepResult(
            step_number=1,
            llm_response=LLMResponse(content="test", tool_calls=[]),
        )
        
        assert result.step_number == 1
        assert result.should_continue is True


class TestAgentResult:
    """Tests for AgentResult dataclass."""
    
    def test_create_success(self):
        """Test creating a successful result."""
        result = AgentResult(
            success=True,
            objective="Find vulnerabilities",
            steps_taken=5,
            final_phase=Phase.REFLECT,
        )
        
        assert result.success is True
        assert result.steps_taken == 5
    
    def test_create_failure(self):
        """Test creating a failed result."""
        result = AgentResult(
            success=False,
            objective="Find vulnerabilities",
            steps_taken=3,
            final_phase=Phase.TEST,
            error="Tool execution failed",
        )
        
        assert result.success is False
        assert result.error == "Tool execution failed"


class TestAgent:
    """Tests for Agent class."""
    
    def test_init(self):
        """Test agent initialization."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        
        assert agent.config is config
        assert agent.llm is llm
    
    def test_init_with_context(self):
        """Test initialization with existing context."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        context = ContextStore()
        
        agent = Agent(config, llm, tools, context=context)
        
        assert agent.context is context
    
    @pytest.mark.asyncio
    async def test_run_simple(self):
        """Test simple agent run."""
        config = AgentConfig()
        llm = MockLLMClient([
            LLMResponse(content="Starting analysis", tool_calls=[]),
            LLMResponse(content="Complete", tool_calls=[]),
        ])
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        result = await agent.run("Test objective", max_steps=2)
        
        assert result.objective == "Test objective"
        assert result.steps_taken <= 2
    
    @pytest.mark.asyncio
    async def test_run_with_max_steps(self):
        """Test that max_steps is respected."""
        config = AgentConfig()
        llm = MockLLMClient([
            LLMResponse(content="Step 1", tool_calls=[]),
            LLMResponse(content="Step 2", tool_calls=[]),
            LLMResponse(content="Step 3", tool_calls=[]),
        ])
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        result = await agent.run("Test", max_steps=2)
        
        assert result.steps_taken == 2
    
    def test_checkpoint(self):
        """Test checkpointing."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        cp_id = agent.checkpoint("test")
        
        assert cp_id is not None
    
    def test_revert(self):
        """Test reverting to checkpoint."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        
        # Add a message before checkpoint
        from tempo.context.frame import MessageRole
        agent.context.add_message(MessageRole.USER, "Before checkpoint")
        
        cp_id = agent.checkpoint("before")
        
        # Revert creates a new branch from checkpoint
        agent.revert(cp_id)
        
        # Should have created a new frame
        assert agent.context.current_frame.parent_id == cp_id
