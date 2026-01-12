"""Integration tests for Tempo Sec."""

import pytest

from tempo import (
    Agent,
    AgentConfig,
    ContextStore,
    ToolRegistry,
    PromptBuilder,
)
from tempo.infra.llm import LLMResponse


class MockLLMClient:
    """Mock LLM for integration testing."""
    
    def __init__(self):
        self.call_count = 0
        self.responses = [
            # Recon phase
            LLMResponse(
                content="Beginning reconnaissance of target.",
                tool_calls=[],
            ),
            # Continue analysis
            LLMResponse(
                content="Continuing analysis of target.",
                tool_calls=[],
            ),
            # Finish task
            LLMResponse(
                content="Completing task with findings.",
                tool_calls=[],
            ),
        ]
    
    async def complete(self, messages, tools=None):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return LLMResponse(content="Done", tool_calls=[])


class TestIntegration:
    """Integration tests for the full agent pipeline."""
    
    @pytest.mark.asyncio
    async def test_agent_full_pipeline(self):
        """Test agent can complete a full objective."""
        config = AgentConfig()
        llm = MockLLMClient()
        tools = ToolRegistry()
        context = ContextStore()
        
        agent = Agent(
            config=config,
            llm=llm,
            tools=tools,
            context=context,
        )
        
        result = await agent.run(
            objective="Test the security of example.com",
            max_steps=3,
        )
        
        assert result.objective == "Test the security of example.com"
        assert result.steps_taken == 3
    
    def test_context_persistence_roundtrip(self):
        """Test context can be saved and loaded."""
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and populate context
            store = ContextStore(persistence_dir=tmpdir)
            from tempo.context.frame import MessageRole
            store.add_message(MessageRole.USER, "Test message")
            
            # Save
            path = store.save()
            assert os.path.exists(path)
            
            # Load
            loaded = ContextStore.load(path)
            messages = loaded.render_messages()
            
            assert any("Test message" in m["content"] for m in messages)
    
    def test_tool_registry_schemas(self):
        """Test tool registry generates valid schemas."""
        from tempo.tools import ShellTool, FileReadTool
        
        registry = ToolRegistry()
        registry.register(ShellTool())
        registry.register(FileReadTool())
        
        schemas = registry.get_schemas()
        
        assert len(schemas) == 2
        assert all(s["type"] == "function" for s in schemas)
        
        names = [s["function"]["name"] for s in schemas]
        assert "shell" in names
        assert "file_read" in names
    
    def test_prompt_builder_orchestrator_prompt(self):
        """Test prompt builder generates orchestrator prompts."""
        builder = PromptBuilder()
        
        schemas = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "Test",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        
        prompt = builder.build_orchestrator_prompt(
            tool_schemas=schemas,
            target="https://example.com",
        )
        
        assert "example.com" in prompt
        assert "test_tool" in prompt


class TestModuleImports:
    """Test that all module imports work correctly."""
    
    def test_main_package_imports(self):
        """Test imports from main tempo package."""
        from tempo import Agent, AgentConfig, ContextStore
        from tempo import ToolRegistry, PromptBuilder
        
        assert Agent is not None
        assert AgentConfig is not None
    
    def test_subpackage_imports(self):
        """Test imports from subpackages."""
        from tempo.agent import Agent
        from tempo.context import ContextStore, BranchManager
        from tempo.infra import LiteLLMClient, ContainerManager
        from tempo.prompts import PromptBuilder
        from tempo.tools import ToolRegistry, ShellTool
        
        assert all([
            Agent,
            ContextStore, BranchManager,
            LiteLLMClient, ContainerManager,
            PromptBuilder,
            ToolRegistry, ShellTool,
        ])
