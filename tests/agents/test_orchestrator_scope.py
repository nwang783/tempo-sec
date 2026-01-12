"""Tests for scope injection in OrchestratorAgent."""

import tempfile
from pathlib import Path
import pytest

from tempo.agents.orchestrator import OrchestratorAgent
from tempo.prompts.builder import PromptBuilder


class TestScopeInjection:
    """Tests for --scope-file feature."""

    def test_orchestrator_accepts_scope_content(self):
        """Test OrchestratorAgent accepts scope_content parameter."""
        agent = OrchestratorAgent(
            target="https://example.com",
            scope_content="Only test /api/* endpoints.",
        )
        assert agent._scope_content == "Only test /api/* endpoints."

    def test_orchestrator_scope_content_default_is_none(self):
        """Test OrchestratorAgent defaults scope_content to None."""
        agent = OrchestratorAgent(target="https://example.com")
        assert agent._scope_content is None

    def test_scope_content_appears_in_system_prompt(self):
        """Test scope content is included in system prompt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            findings_path = Path(tmpdir) / "test.yaml"
            agent = OrchestratorAgent(
                target="https://example.com",
                findings_path=str(findings_path),
                scope_content="Exclude: admin panel, production databases",
            )
            prompts = PromptBuilder()
            mock_schemas = [{"function": {"name": "shell", "description": "test"}}]

            prompt = agent.build_system_prompt(
                prompts=prompts,
                tool_schemas=mock_schemas,
                scope_description="unused",
            )

            assert "Scope Constraints" in prompt
            assert "Exclude: admin panel, production databases" in prompt

    def test_no_scope_content_omits_section(self):
        """Test that no scope content means no scope section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            findings_path = Path(tmpdir) / "test.yaml"
            agent = OrchestratorAgent(
                target="https://example.com",
                findings_path=str(findings_path),
            )
            prompts = PromptBuilder()
            mock_schemas = [{"function": {"name": "shell", "description": "test"}}]

            prompt = agent.build_system_prompt(
                prompts=prompts,
                tool_schemas=mock_schemas,
                scope_description="unused",
            )

            assert "Scope Constraints" not in prompt


class TestPromptBuilderScopeSupport:
    """Tests for PromptBuilder scope support."""

    def test_build_orchestrator_prompt_with_scope(self):
        """Test prompt builder includes scope content."""
        prompts = PromptBuilder()
        mock_schemas = [{"function": {"name": "dispatch_subagents", "description": "test"}}]

        prompt = prompts.build_orchestrator_prompt(
            tool_schemas=mock_schemas,
            target="https://example.com",
            findings_summary="No findings yet.",
            scope_content="Focus on API endpoints only.",
        )

        assert "## Scope Constraints" in prompt
        assert "Focus on API endpoints only." in prompt

    def test_build_orchestrator_prompt_without_scope(self):
        """Test prompt builder works without scope content."""
        prompts = PromptBuilder()
        mock_schemas = [{"function": {"name": "dispatch_subagents", "description": "test"}}]

        prompt = prompts.build_orchestrator_prompt(
            tool_schemas=mock_schemas,
            target="https://example.com",
            findings_summary="No findings yet.",
        )

        assert "## Scope Constraints" not in prompt
        assert "https://example.com" in prompt

    def test_build_orchestrator_prompt_scope_none_explicit(self):
        """Test prompt builder handles explicit None scope."""
        prompts = PromptBuilder()
        mock_schemas = [{"function": {"name": "shell", "description": "test"}}]

        prompt = prompts.build_orchestrator_prompt(
            tool_schemas=mock_schemas,
            target="https://example.com",
            findings_summary="No findings yet.",
            scope_content=None,
        )

        assert "## Scope Constraints" not in prompt

    def test_scope_section_placement(self):
        """Test scope section appears after Mission and before Current State."""
        prompts = PromptBuilder()
        mock_schemas = [{"function": {"name": "shell", "description": "test"}}]

        prompt = prompts.build_orchestrator_prompt(
            tool_schemas=mock_schemas,
            target="https://example.com",
            findings_summary="Some findings here.",
            scope_content="Only test authenticated endpoints.",
        )

        # Check ordering: Mission should come before Scope Constraints
        mission_pos = prompt.find("## Your Mission")
        scope_pos = prompt.find("## Scope Constraints")
        current_state_pos = prompt.find("## Current State")

        assert mission_pos < scope_pos < current_state_pos
