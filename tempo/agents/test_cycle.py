"""
Test Cycle Agent Definition.

Agent for running the hypothesis/test/reflect cycle based on a target manifest.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tempo.agents.base import BaseAgentDefinition
from tempo.agents import register_agent
from tempo.prompts.phases import Phase

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.agent.workflow import WorkflowManager
    from tempo.tools.registry import ToolRegistry
    from tempo.prompts.builder import PromptBuilder
    from tempo.schema.manifest import TargetManifest


@register_agent
class TestCycleAgent(BaseAgentDefinition):
    """
    Test cycle agent that executes security testing workflows.
    
    Consumes a target manifest from the recon phase and executes
    iterative hypothesis testing:
    - HYPOTHESIZE: Formulate security hypotheses
    - TEST: Verify hypotheses with tools
    - REFLECT: Analyze results and plan next steps
    """
    
    _name = "test_cycle"
    _model = "openai/gpt-5-mini"
    _initial_phase = Phase.HYPOTHESIZE
    
    def __init__(
        self,
        manifest_path: str,
        **kwargs: Any,
    ):
        """
        Initialize the test cycle agent.
        
        Args:
            manifest_path: Path to the target manifest JSON file
            **kwargs: Ignored additional args
        """
        self.manifest_path = manifest_path
        self._manifest: "TargetManifest | None" = None
        
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return "Security testing agent that executes hypothesis/test/reflect cycles"
    
    def _load_manifest(self) -> "TargetManifest":
        """Load and validate the target manifest."""
        if self._manifest:
            return self._manifest
            
        from tempo.schema.manifest import TargetManifest
        
        path = Path(self.manifest_path)
        if not path.exists():
            raise FileNotFoundError(f"Manifest file not found: {self.manifest_path}")
            
        try:
            self._manifest = TargetManifest.load(str(path))
            return self._manifest
        except Exception as e:
            raise ValueError(f"Error loading manifest: {e}")

    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        workflow: "WorkflowManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """Create testing-specific tools."""
        from tempo.tools.registry import ToolRegistry
        from tempo.tools.shell import ShellTool
        from tempo.tools.filesystem import FileReadTool, FileWriteTool
        from tempo.tools.browser_tools import (
            BrowserSession,
            BrowserNavigateTool,
            BrowserSnapshotTool,
            BrowserClickTool,
            BrowserTypeTool,
            BrowserFillFormTool,
        )
        from tempo.tools.meta import (
            TransitionPhaseTool,
            SummarizeOutputTool,
            ContinueAnalysisTool,
            BranchToSubtasksTool,
            FinishSubtaskTool,
        )
        from tempo.tools.testplan_tools import (
            CreateTestPlanTool,
            AddTodoTool,
            CompleteTodoTool,
        )
        from tempo.tools.view_output import ViewToolOutputTool
        
        tools = ToolRegistry()
        
        # Core tools
        tools.register(ShellTool(container_manager=container))
        tools.register(FileReadTool(container_manager=container))
        tools.register(FileWriteTool(container_manager=container))
        
        # Browser tools
        browser_session = BrowserSession(container_manager=container)
        tools.register(BrowserNavigateTool(browser_session))
        tools.register(BrowserSnapshotTool(browser_session))
        tools.register(BrowserClickTool(browser_session))
        tools.register(BrowserTypeTool(browser_session))
        tools.register(BrowserFillFormTool(browser_session))
        
        # Meta tools for testing workflow
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(ViewToolOutputTool(context_store=context))
        tools.register(ContinueAnalysisTool())
        
        # Hypothesis checklist tools
        tools.register(CreateTestPlanTool(test_plan_manager=context))
        tools.register(AddTodoTool(test_plan_manager=context))
        tools.register(CompleteTodoTool(test_plan_manager=context))
        
        if workflow:
            tools.register(TransitionPhaseTool(workflow_manager=workflow))
            
        return tools
    
    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """Build full system prompt with phase transitions."""
        # Use default full prompt which includes phase transitions
        return prompts.build_full_prompt(
            current_phase=self.initial_phase,
            tool_schemas=tool_schemas,
            scope_description=scope_description,
        )
    
    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """
        Build the testing objective based on the manifest.
        
        Args:
            target: Ignored (uses manifest target)
            **kwargs: Ignored
            
        Returns:
            Formatted objective string
        """
        manifest = self._load_manifest()
        manifest_summary = manifest.to_summary()
        
        return f"""Perform security testing on {manifest.metadata.target_domain}

## Reconnaissance Summary (from manifest)

{manifest_summary}

---

## Your Task

Based on the reconnaissance data above:

1. **HYPOTHESIZE**: Form specific, testable security hypotheses based on the identified attack surfaces
2. **TEST**: Execute tests to validate or refute each hypothesis
3. **REFLECT**: Analyze results and decide whether to continue with more testing

Focus on the attack surfaces identified during recon. Prioritize by risk level.

After reflecting, use `continue_analysis` to either:
- Continue with more testing (should_continue=true) → loops back to HYPOTHESIZE
- Complete the analysis (should_continue=false) → provide final findings"""
