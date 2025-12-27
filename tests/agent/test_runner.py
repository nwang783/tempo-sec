"""Tests for tempo/agent/runner.py."""

import pytest

from tempo.agent.config import AgentConfig
from tempo.agent.runner import Agent, AgentResult, StepResult, SUMMARIZATION_TOKEN_THRESHOLD
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


class TestPhaseFilteredTools:
    """Tests for phase-gated tool filtering."""
    
    def test_continue_analysis_hidden_in_recon(self):
        """Test that continue_analysis is hidden during RECON phase."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        # Register the continue_analysis tool
        from tempo.tools.meta import ContinueAnalysisTool
        tools.register(ContinueAnalysisTool())
        tools.register(DummyTool())
        
        agent = Agent(config, llm, tools)
        agent.workflow.current_phase = Phase.RECON
        
        # Get filtered tools
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        
        assert "continue_analysis" not in tool_names
        assert "dummy" in tool_names
    
    def test_continue_analysis_hidden_in_hypothesize(self):
        """Test that continue_analysis is hidden during HYPOTHESIZE phase."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        from tempo.tools.meta import ContinueAnalysisTool
        tools.register(ContinueAnalysisTool())
        
        agent = Agent(config, llm, tools)
        agent.workflow.current_phase = Phase.HYPOTHESIZE
        
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        
        assert "continue_analysis" not in tool_names
    
    def test_continue_analysis_hidden_in_test(self):
        """Test that continue_analysis is hidden during TEST phase."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        from tempo.tools.meta import ContinueAnalysisTool
        tools.register(ContinueAnalysisTool())
        
        agent = Agent(config, llm, tools)
        agent.workflow.current_phase = Phase.TEST
        
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        
        assert "continue_analysis" not in tool_names
    
    def test_only_continue_analysis_visible_in_reflect(self):
        """Test that ONLY continue_analysis is visible during REFLECT phase."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        from tempo.tools.meta import ContinueAnalysisTool
        tools.register(ContinueAnalysisTool())
        tools.register(DummyTool())
        
        agent = Agent(config, llm, tools)
        agent.workflow.current_phase = Phase.REFLECT
        
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        
        # ONLY continue_analysis should be visible
        assert "continue_analysis" in tool_names
        assert "dummy" not in tool_names  # Other tools hidden in reflect
        assert len(tool_names) == 1
    
    def test_shared_workflow_updates_phase(self):
        """Test that a shared workflow manager updates the phase correctly."""
        from tempo.agent.workflow import WorkflowManager
        from tempo.tools.meta import TransitionPhaseTool, ContinueAnalysisTool
        
        config = AgentConfig()
        llm = MockLLMClient()
        
        # Create shared workflow manager
        workflow = WorkflowManager(config)
        
        # Create tools with shared workflow
        tools = ToolRegistry()
        tools.register(ContinueAnalysisTool())
        tools.register(TransitionPhaseTool(workflow_manager=workflow))
        
        # Create agent with shared workflow
        agent = Agent(config, llm, tools, workflow=workflow)
        
        # Initially in RECON
        assert agent.workflow.current_phase == Phase.RECON
        
        # continue_analysis should be hidden
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        assert "continue_analysis" not in tool_names
        
        # Transition through valid phases to REFLECT
        # RECON -> HYPOTHESIZE -> TEST -> REFLECT
        workflow.transition(Phase.HYPOTHESIZE)
        workflow.transition(Phase.TEST)
        workflow.transition(Phase.REFLECT)
        
        # Now ONLY continue_analysis should be visible
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        assert "continue_analysis" in tool_names
        assert len(tool_names) == 1  # Only continue_analysis


class LongOutputTool(Tool):
    """Tool that returns output exceeding the summarization threshold for testing."""
    
    name = "long_output"
    description = "Returns a long output for testing summarization"
    category = ToolCategory.EXECUTION
    
    async def execute(self, purpose: str = "") -> ToolResult:
        # Create output well over the threshold (~500 words)
        long_text = " ".join(["word"] * 500)
        return ToolResult(success=True, output=long_text)
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={"type": "object", "properties": {}},
        )


class TestSummarizationRequirement:
    """Tests for mandatory output summarization on large tool outputs."""
    
    def test_requires_summarization_over_threshold(self):
        """Test that _requires_summarization returns True for outputs exceeding threshold."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        tools.register(DummyTool())
        
        agent = Agent(config, llm, tools)
        
        # Create a tool call with >100 tokens of output (~500 words)
        from tempo.context.frame import ToolCall
        long_output = " ".join(["word"] * 500)
        
        tc = ToolCall(
            tool_name="dummy",
            raw_output=long_output,
            success=True,
        )
        
        assert agent._requires_summarization(tc) is True
    
    def test_requires_summarization_under_threshold(self):
        """Test that short outputs don't require summarization."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        tools.register(DummyTool())
        
        agent = Agent(config, llm, tools)
        
        from tempo.context.frame import ToolCall
        tc = ToolCall(
            tool_name="dummy",
            raw_output="Short output",
            success=True,
        )
        
        assert agent._requires_summarization(tc) is False
    
    def test_meta_tools_exempt_from_summarization(self):
        """Test that meta tools don't require summarization even with long output."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        
        from tempo.context.frame import ToolCall
        long_output = " ".join(["word"] * 500)
        
        # Create tool calls for exempt tools
        for tool_name in ["summarize_previous_tool_output", "transition_phase", "continue_analysis"]:
            tc = ToolCall(
                tool_name=tool_name,
                raw_output=long_output,
                success=True,
            )
            assert agent._requires_summarization(tc) is False, f"{tool_name} should be exempt"
    
    def test_failed_tools_dont_require_summarization(self):
        """Test that failed tool calls don't require summarization."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        
        from tempo.context.frame import ToolCall
        long_output = " ".join(["word"] * 500)
        
        tc = ToolCall(
            tool_name="dummy",
            raw_output=long_output,
            success=False,  # Failed
        )
        
        assert agent._requires_summarization(tc) is False
    
    def test_pending_summarization_restricts_tools(self):
        """Test that pending summarization restricts available tools to only summarize_previous_tool_output."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        # Register multiple tools including summarize_previous_tool_output
        from tempo.tools.meta import SummarizeOutputTool
        from tempo.context.store import ContextStore
        
        context = ContextStore()
        tools.register(DummyTool())
        tools.register(SummarizeOutputTool(context_store=context))
        
        agent = Agent(config, llm, tools, context=context)
        
        # Initially, both tools should be available (in RECON phase)
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        assert "dummy" in tool_names
        assert "summarize_previous_tool_output" in tool_names
        
        # Add a pending summarization
        agent.context.add_pending_summarization("test-id")
        
        # Now ONLY summarize_previous_tool_output should be available
        filtered = agent._get_phase_filtered_tools()
        tool_names = [t.get("function", {}).get("name") for t in filtered]
        assert tool_names == ["summarize_previous_tool_output"]
    
    def test_summarization_clears_pending(self):
        """Test that successful summarization clears the pending state."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        
        agent = Agent(config, llm, tools)
        
        # Add a pending summarization via context
        agent.context.add_pending_summarization("test-tool-call-id")
        assert agent.context.has_pending_summarization()
        
        # Simulate successful summarization by removing from context
        agent.context.remove_pending_summarization("test-tool-call-id")
        
        # Pending should now be empty
        assert not agent.context.has_pending_summarization()

