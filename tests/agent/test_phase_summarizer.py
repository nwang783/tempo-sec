"""
Tests for PhaseSummarizer component.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tempo.agent.phase_summarizer import PhaseSummarizer
from tempo.agent.config import AgentConfig
from tempo.prompts.phases import Phase
from tempo.context.frame import MessageRole, ToolCall, Message, AgentState


@pytest.fixture
def mock_config():
    """Create a test configuration."""
    return AgentConfig(
        phase_summarization_model="gemini/gemini-3-flash-preview",
        auto_phase_summary=True,
    )


@pytest.fixture
def mock_prompts():
    """Create a mock prompt builder."""
    prompts = MagicMock()
    prompts.build_phase_transition_prompt.return_value = "Test transition prompt"
    return prompts


@pytest.fixture
def mock_context():
    """Create a mock context store with sample data."""
    context = MagicMock()
    
    # Create a mock frame with tool calls and messages
    frame = MagicMock()
    frame.tool_calls = [
        MagicMock(
            tool_name="shell",
            input={"command": "nmap example.com"},
            output_for_context="Port 80 open",
            success=True,
        ),
    ]
    frame.messages = [
        MagicMock(role=MessageRole.SYSTEM, content="System prompt"),
        MagicMock(role=MessageRole.ASSISTANT, content="Found open port 80"),
    ]
    frame.state = MagicMock()
    frame.state.hypotheses = []
    frame.state.findings = []
    frame.state.notes = ["Initial recon complete"]
    
    context.current_frame = frame
    return context


@pytest.fixture
def phase_summarizer(mock_config, mock_prompts, mock_context):
    """Create a PhaseSummarizer with mocked dependencies."""
    with patch('tempo.agent.phase_summarizer.LiteLLMClient') as mock_llm_class:
        # Create mock LLM client
        mock_llm = AsyncMock()
        mock_llm.complete.return_value = MagicMock(content="Phase summary from LLM")
        mock_llm_class.return_value = mock_llm
        
        summarizer = PhaseSummarizer(mock_config, mock_prompts, mock_context)
        summarizer._summary_llm = mock_llm
        
        return summarizer


@pytest.mark.asyncio
async def test_summarize_phase_transition_basic(phase_summarizer, mock_prompts):
    """Test that phase transitions generate summaries."""
    summary = await phase_summarizer.summarize_phase_transition(
        from_phase=Phase.RECON,
        to_phase=Phase.HYPOTHESIZE,
        objective="Test the target for vulnerabilities",
    )
    
    assert summary == "Phase summary from LLM"
    phase_summarizer._summary_llm.complete.assert_called_once()
    
    # Verify the prompt was built correctly
    mock_prompts.build_phase_transition_prompt.assert_called_once()
    call_args = mock_prompts.build_phase_transition_prompt.call_args
    assert call_args.kwargs["from_phase"] == Phase.RECON
    assert call_args.kwargs["to_phase"] == Phase.HYPOTHESIZE
    assert call_args.kwargs["objective"] == "Test the target for vulnerabilities"


@pytest.mark.asyncio
async def test_summarize_extracts_tool_calls(phase_summarizer, mock_prompts, mock_context):
    """Test that tool calls are extracted for summarization."""
    await phase_summarizer.summarize_phase_transition(
        from_phase=Phase.RECON,
        to_phase=Phase.HYPOTHESIZE,
        objective="Test objective",
    )
    
    # Check that phase_context was passed with tool calls
    call_args = mock_prompts.build_phase_transition_prompt.call_args
    phase_context = call_args.kwargs["phase_context"]
    
    assert "tool_calls" in phase_context
    assert len(phase_context["tool_calls"]) == 1
    assert phase_context["tool_calls"][0]["tool"] == "shell"


def test_extract_phase_context(phase_summarizer):
    """Test context extraction from frame."""
    context = phase_summarizer._extract_phase_context(Phase.RECON)
    
    assert context["phase"] == "recon"
    assert "tool_calls" in context
    assert "assistant_reasoning" in context
    assert "state" in context


def test_extract_phase_context_truncates_long_outputs(phase_summarizer, mock_context):
    """Test that very long outputs are truncated for the summarizer."""
    # Add a tool call with very long output
    long_output = "A" * 2000
    mock_context.current_frame.tool_calls = [
        MagicMock(
            tool_name="shell",
            input={"command": "cat large_file.txt"},
            output_for_context=long_output,
            success=True,
        ),
    ]
    
    context = phase_summarizer._extract_phase_context(Phase.RECON)
    
    # Should be truncated
    tool_output = context["tool_calls"][0]["output"]
    assert len(tool_output) < len(long_output)
    assert "[truncated]" in tool_output
