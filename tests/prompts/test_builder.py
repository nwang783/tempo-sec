"""Tests for tempo/prompts/builder.py."""

import tempfile
from pathlib import Path

import pytest

from tempo.prompts.builder import PromptBuilder, TEMPLATES_DIR
from tempo.prompts.phases import Phase


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
        assert "{objective}" in template
    
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
            objective="Find vulnerabilities in example.com",
            current_phase=Phase.RECON,
            tool_descriptions="### shell\nExecute commands",
            scope_description="Only test example.com",
            hypotheses_count=2,
            findings_count=1,
        )
        
        assert "Find vulnerabilities" in prompt
        assert "recon" in prompt.lower()
        assert "shell" in prompt
        assert "example.com" in prompt
    
    def test_build_phase_prompt(self):
        """Test building phase-specific prompts."""
        builder = PromptBuilder()
        
        for phase in Phase:
            prompt = builder.build_phase_prompt(phase)
            assert len(prompt) > 0
            assert phase.value.upper() in prompt.upper()
    
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
    
    def test_build_full_prompt(self):
        """Test building complete prompt."""
        builder = PromptBuilder()
        
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "browser",
                    "description": "Browse a URL",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        
        prompt = builder.build_full_prompt(
            objective="Test example.com",
            current_phase=Phase.RECON,
            tool_schemas=schemas,
        )
        
        # Should contain both system and phase content
        assert "Test example.com" in prompt
        assert "RECON" in prompt
        assert "browser" in prompt
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


class TestPhasePrompts:
    """Tests for individual phase prompts."""
    
    def test_recon_prompt_content(self):
        """Test recon prompt has key guidance."""
        builder = PromptBuilder()
        prompt = builder.build_phase_prompt(Phase.RECON)
        
        assert "surface" in prompt.lower() or "discovery" in prompt.lower()
        assert "transition_phase" in prompt
    
    def test_hypothesize_prompt_content(self):
        """Test hypothesize prompt has key guidance."""
        builder = PromptBuilder()
        prompt = builder.build_phase_prompt(Phase.HYPOTHESIZE)
        
        # Updated to use create_test_plan tool
        assert "create_test_plan" in prompt
        assert "investigation" in prompt.lower() or "test plan" in prompt.lower()
    
    def test_test_prompt_content(self):
        """Test test prompt has key guidance."""
        builder = PromptBuilder()
        prompt = builder.build_phase_prompt(Phase.TEST)
        
        assert "payload" in prompt.lower() or "testing" in prompt.lower()
    
    def test_reflect_prompt_content(self):
        """Test reflect prompt has key guidance."""
        builder = PromptBuilder()
        prompt = builder.build_phase_prompt(Phase.REFLECT)
        
        # Updated to use continue_analysis tool
        assert "continue_analysis" in prompt
        assert "findings" in prompt.lower()
