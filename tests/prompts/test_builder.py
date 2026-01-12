"""Tests for tempo/prompts/builder.py."""

import tempfile
from pathlib import Path

import pytest

from tempo.prompts.builder import PromptBuilder, TEMPLATES_DIR


class TestPromptBuilder:
    """Tests for PromptBuilder class."""
    
    def test_default_templates_dir(self):
        """Test that default templates directory exists."""
        assert TEMPLATES_DIR.exists()
    
    def test_init_default(self):
        """Test initialization with default templates."""
        builder = PromptBuilder()
        assert builder.templates_dir == TEMPLATES_DIR
    
    def test_init_custom_dir(self):
        """Test initialization with custom templates directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = PromptBuilder(tmpdir)
            assert builder.templates_dir == Path(tmpdir)
    
    def test_load_template(self):
        """Test loading a template file."""
        builder = PromptBuilder()
        template = builder._load_template("system")
        
        assert "cybersecurity" in template.lower()
    
    def test_load_template_caching(self):
        """Test that templates are cached."""
        builder = PromptBuilder()
        
        # Load twice
        t1 = builder._load_template("system")
        t2 = builder._load_template("system")
        
        assert t1 is t2  # Same object from cache
    
    def test_load_nonexistent_template(self):
        """Test loading nonexistent template raises error."""
        builder = PromptBuilder()
        
        with pytest.raises(FileNotFoundError):
            builder._load_template("nonexistent_template")
    
    def test_build_system_prompt(self):
        """Test building system prompt."""
        builder = PromptBuilder()
        
        prompt = builder.build_system_prompt(
            tool_descriptions="### shell\nExecute commands",
            scope_description="Only test example.com",
        )
        
        assert "shell" in prompt
        assert "example.com" in prompt
    
    def test_build_summarization_prompt(self):
        """Test building summarization prompt."""
        builder = PromptBuilder()
        
        prompt = builder.build_summarization_prompt(
            tool_name="shell",
            tool_input={"command": "nmap example.com"},
            tool_output="PORT STATE SERVICE\n22 open ssh\n80 open http",
            objective="Find open ports",
        )
        
        assert "shell" in prompt
        assert "nmap" in prompt
        assert "PORT" in prompt
        assert "Find open ports" in prompt
    
    def test_build_subagent_prompt(self):
        """Test building subagent prompt."""
        builder = PromptBuilder()
        
        prompt = builder.build_subagent_prompt(
            subtask_objective="Test SQL injection in login form",
            tool_descriptions="### shell\nExecute commands",
        )
        
        assert "SQL injection" in prompt
        assert "finish_subtask" in prompt
        assert "shell" in prompt
    
    def test_format_tool_descriptions(self):
        """Test formatting tool schemas."""
        builder = PromptBuilder()
        
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "shell",
                    "description": "Execute a command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The command to run",
                            },
                            "purpose": {
                                "type": "string",
                                "description": "Why calling this",
                            },
                        },
                    },
                },
            },
        ]
        
        formatted = builder.format_tool_descriptions(schemas)
        
        assert "### shell" in formatted
        assert "Execute a command" in formatted
        assert "command (string)" in formatted
        # Purpose should be filtered out
        assert "purpose" not in formatted.lower()
    
    def test_tool_guidance_injected_for_known_tools(self):
        """Test that tool-specific guidance is injected for known tools."""
        builder = PromptBuilder()
        
        schemas = [
            {"type": "function", "function": {"name": "summarize_previous_tool_output", "description": "Summarize output"}},
            {"type": "function", "function": {"name": "finalize_analysis", "description": "Finalize analysis"}},
        ]
        
        formatted = builder.format_tool_descriptions(schemas)
        
        # Guidance for summarize_previous_tool_output
        assert "MANDATORY" in formatted
        assert "token threshold" in formatted
        
        # Guidance for finalize_analysis
        assert "terminates the orchestrator" in formatted
    
    def test_tool_guidance_not_injected_for_unknown_tools(self):
        """Test that unknown tools don't get extra guidance."""
        builder = PromptBuilder()
        
        schemas = [
            {"type": "function", "function": {"name": "custom_unknown_tool", "description": "A custom tool"}},
        ]
        
        formatted = builder.format_tool_descriptions(schemas)
        
        # Should just have the description, no extra guidance
        assert "custom_unknown_tool" in formatted
        assert "A custom tool" in formatted
        assert "MANDATORY" not in formatted  # No guidance keywords

    def test_filter_schemas_for_subagent(self):
        """Test that subagent tool filtering excludes main-agent-only tools."""
        builder = PromptBuilder()
        
        schemas = [
            {"type": "function", "function": {"name": "shell"}},
            {"type": "function", "function": {"name": "branch_to_subtasks"}},
            {"type": "function", "function": {"name": "finish_task"}},
            {"type": "function", "function": {"name": "finish_subtask"}},
        ]
        
        filtered = builder.filter_schemas_for_subagent(schemas)
        
        names = [s["function"]["name"] for s in filtered]
        assert "shell" in names
        assert "finish_subtask" in names
        assert "branch_to_subtasks" not in names
        assert "finish_task" not in names

    def test_build_orchestrator_prompt(self):
        """Test building orchestrator prompt."""
        builder = PromptBuilder()
        
        prompt = builder.build_orchestrator_prompt(
            tool_schemas=[
                {"type": "function", "function": {"name": "dispatch_subagents", "description": "Dispatch a subagent"}},
            ],
            target="https://example.com",
            findings_summary="No findings yet",
        )
        
        assert "example.com" in prompt
        assert "dispatch_subagents" in prompt
