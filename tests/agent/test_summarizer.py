"""Tests for tempo/agent/summarizer.py."""

import pytest

from tempo.agent.config import AgentConfig
from tempo.agent.summarizer import OutputSummarizer
from tempo.context.frame import ToolCall
from tempo.prompts.builder import PromptBuilder
from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema


class MockLLMClient:
    """Mock LLM client for testing."""
    
    async def complete(self, messages, tools=None):
        from tempo.infra.llm import LLMResponse
        
        return LLMResponse(
            content="Summarized: key findings extracted",
            tool_calls=[],
        )


class MockTool(Tool):
    """Mock tool for testing."""
    
    name = "mock"
    description = "Mock tool"
    category = ToolCategory.EXECUTION
    
    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="mock output")
    
    def get_schema(self) -> ToolSchema:
        return ToolSchema(name=self.name, description=self.description, parameters={})
    
    def default_summarizer(self, result: ToolResult) -> str:
        return "Mock summary"


class TestOutputSummarizer:
    """Tests for OutputSummarizer class."""
    
    def test_init(self):
        """Test initialization."""
        llm = MockLLMClient()
        prompts = PromptBuilder()
        config = AgentConfig()
        
        summarizer = OutputSummarizer(llm, prompts, config)
        
        assert summarizer.llm is llm
    
    @pytest.mark.asyncio
    async def test_summarize_short_output(self):
        """Test that short outputs are not summarized."""
        llm = MockLLMClient()
        prompts = PromptBuilder()
        config = AgentConfig()
        summarizer = OutputSummarizer(llm, prompts, config)
        
        tool_call = ToolCall(tool_name="test", raw_output="Short output")
        
        result = await summarizer.summarize(tool_call, "test objective")
        
        # Should return original since it's short
        assert result == "Short output"
    
    @pytest.mark.asyncio
    async def test_summarize_with_tool_summarizer(self):
        """Test using tool's default summarizer."""
        llm = MockLLMClient()
        prompts = PromptBuilder()
        config = AgentConfig()
        summarizer = OutputSummarizer(llm, prompts, config)
        
        # Long output that would normally need summarization
        long_output = "A" * 500
        tool_call = ToolCall(tool_name="mock", raw_output=long_output)
        tool = MockTool()
        
        result = await summarizer.summarize(tool_call, "test objective", tool)
        
        # Should use tool's summarizer since it's much shorter
        assert result == "Mock summary"
    
    @pytest.mark.asyncio
    async def test_summarize_with_llm(self):
        """Test LLM summarization for long outputs."""
        llm = MockLLMClient()
        prompts = PromptBuilder()
        config = AgentConfig()
        summarizer = OutputSummarizer(llm, prompts, config)
        
        # Long output without a good tool summarizer
        long_output = "A" * 1000
        tool_call = ToolCall(tool_name="unknown", raw_output=long_output)
        
        result = await summarizer.summarize(tool_call, "test objective")
        
        # Should use LLM
        assert "Summarized" in result
    
    def test_should_summarize(self):
        """Test should_summarize detection."""
        llm = MockLLMClient()
        prompts = PromptBuilder()
        config = AgentConfig()
        summarizer = OutputSummarizer(llm, prompts, config)
        
        short_call = ToolCall(tool_name="test", raw_output="Short")
        long_call = ToolCall(tool_name="test", raw_output="A" * 600)
        
        assert summarizer.should_summarize(short_call) is False
        assert summarizer.should_summarize(long_call) is True
    
    def test_estimate_token_savings(self):
        """Test token savings estimation."""
        llm = MockLLMClient()
        prompts = PromptBuilder()
        config = AgentConfig()
        summarizer = OutputSummarizer(llm, prompts, config)
        
        original = "A" * 400  # ~100 tokens
        summary = "B" * 100   # ~25 tokens
        
        savings = summarizer.estimate_token_savings(original, summary)
        
        assert savings == 75  # 100 - 25
