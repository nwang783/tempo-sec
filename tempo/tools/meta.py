"""
Meta tools for agent control, phase transitions, and branching.
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema
from tempo.infra.protocols import (
    PhaseTransitioner,
    ContextSummarizer,
    BranchSpawner,
)


class TransitionPhaseTool(Tool):
    """Transition the agent to a new workflow phase."""
    
    name = "transition_phase"
    description = """Move to the next workflow phase (recon → hypothesize → test → reflect).
    
    Use this tool when you have completed work in the current phase and are ready to proceed.
    This does NOT end the analysis - it advances to the next phase of investigation.
    
    Call this BEFORE calling complete_analysis."""
    category = ToolCategory.META
    
    def __init__(self, workflow_manager: PhaseTransitioner):
        """
        Initialize the transition phase tool.
        
        Args:
            workflow_manager: Any component implementing PhaseTransitioner protocol
        """
        self.workflow = workflow_manager
        
    async def execute(
        self,
        phase: str,
        justification: str,
        purpose: str = "",
    ) -> ToolResult:
        """
        Transition to a new phase.
        
        Args:
            phase: Target phase (recon, hypothesize, test, reflect)
            justification: Why you are moving to this phase
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult indicating success/failure
        """
        from tempo.infra.phases import Phase
        from tempo.agent.workflow import WorkflowError
        
        try:
            target_phase = Phase(phase.lower())
            self.workflow.transition(target_phase)
            return ToolResult(
                success=True,
                output=f"Switched to {target_phase.value} phase.",
                metadata={"phase": target_phase.value},
            )
        except ValueError:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid phase: {phase}. Valid phases: recon, hypothesize, test, reflect",
            )
        except WorkflowError as e:
            return ToolResult(
                success=False,
                output="",
                error=str(e),
            )
            
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        from tempo.infra.phases import Phase
        
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "phase": {
                        "type": "string",
                        "enum": [p.value for p in Phase],
                        "description": "The target phase",
                    },
                    "justification": {
                        "type": "string",
                        "description": "Why you are moving to this phase",
                    },
                },
                "required": ["phase", "justification"],
            },
        )


class SummarizeOutputTool(Tool):
    """Summarize the output of a previous tool call."""
    
    name = "summarize_tool_output"
    description = "Summarize a previous tool output to save context tokens"
    category = ToolCategory.META
    
    def __init__(self, context_store: ContextSummarizer):
        """
        Initialize the summarize output tool.
        
        Args:
            context_store: Any component implementing ContextSummarizer protocol
        """
        self.context = context_store
        
    async def execute(
        self,
        tool_call_id: str,
        summary: str,
        purpose: str = "",
    ) -> ToolResult:
        """
        Summarize a tool call's output.
        
        Args:
            tool_call_id: ID of the tool call to summarize
            summary: Concise summary of the tool output
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult indicating success/failure
        """
        try:
            self.context.summarize_tool_call(tool_call_id, summary)
            return ToolResult(
                success=True,
                output=f"Summarized tool call {tool_call_id}",
                metadata={"summarized_tool_id": tool_call_id},
            )
        except KeyError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Tool call not found: {tool_call_id}",
            )

    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "tool_call_id": {
                        "type": "string",
                        "description": "ID of the tool call to summarize",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Concise summary of the tool output",
                    },
                },
                "required": ["tool_call_id", "summary"],
            },
        )


class ContinueAnalysisTool(Tool):
    """Decide whether to continue or finish the security analysis."""
    
    name = "continue_analysis"
    description = """Decide whether to continue or finish the security analysis.
    
    You MUST call this tool after entering the REFLECT phase.
    Analyze your findings, then decide:
    
    - should_continue=true: More investigation is needed → transitions back to RECON
    - should_continue=false: Analysis is complete → ends execution with findings
    
    This is the ONLY tool available in the REFLECT phase."""
    category = ToolCategory.META
    
    async def execute(
        self,
        should_continue: bool,
        reasoning: str,
        findings: str = "",
        purpose: str = "",
    ) -> ToolResult:
        """
        Decide whether to continue or finish analysis.
        
        Args:
            should_continue: True to continue with more investigation, False to finish
            reasoning: Explanation of why you are continuing or finishing
            findings: Summary of findings (required if finishing)
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult with continue or finish flag in metadata
        """
        if should_continue:
            return ToolResult(
                success=True,
                output="Continuing analysis.",
                metadata={"continue": True, "reasoning": reasoning},
            )
        else:
            if not findings:
                return ToolResult(
                    success=False,
                    output="",
                    error="When finishing analysis (should_continue=false), you must provide findings.",
                )
            return ToolResult(
                success=True,
                output="Analysis complete.",
                metadata={"finish": True, "findings": findings, "reasoning": reasoning},
            )
            
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "should_continue": {
                        "type": "boolean",
                        "description": "True to continue investigating, False to finish and report findings.",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "Explanation of why you are continuing or finishing.",
                    },
                    "findings": {
                        "type": "string",
                        "description": "Summary of findings. Required when should_continue is false.",
                    },
                },
                "required": ["should_continue", "reasoning"],
            },
        )


# Keep FinishTaskTool as an alias for backward compatibility
FinishTaskTool = ContinueAnalysisTool


class BranchToSubtasksTool(Tool):
    """Spawn parallel subagents to work on subtasks."""
    
    name = "branch_to_subtasks"
    description = """Spawn parallel subagents to investigate subtasks. Use this for:
    - Investigating multiple hypotheses in parallel
    - Research tasks that can be done independently
    - Any work that should result in a summary
    
    Each subtask will be handled by a clone of yourself. When all subtasks complete,
    their summaries will be merged and returned to you."""
    category = ToolCategory.META
    
    def __init__(self, branch_coordinator: BranchSpawner):
        """
        Initialize the branch tool.
        
        Args:
            branch_coordinator: Any component implementing BranchSpawner protocol
        """
        self.coordinator = branch_coordinator
        
    async def execute(
        self,
        subtasks: list[str],
        purpose: str = "",
    ) -> ToolResult:
        """
        Spawn subagents for each subtask.
        
        Args:
            subtasks: List of subtask objectives
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult with branch_id for tracking
        """
        if not subtasks:
            return ToolResult(
                success=False,
                output="",
                error="At least one subtask is required",
            )
        
        branch_id = await self.coordinator.spawn_subtasks(subtasks)
        return ToolResult(
            success=True,
            output=f"Spawned {len(subtasks)} subagents. Waiting for results...",
            metadata={"branch_id": branch_id, "pending": True, "subtask_count": len(subtasks)},
        )
        
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "subtasks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of subtask objectives for subagents to work on",
                    },
                },
                "required": ["subtasks"],
            },
        )


class FinishSubtaskTool(Tool):
    """Signal completion of a subtask (used by subagents)."""
    
    name = "finish_subtask"
    description = """Signal that your subtask is complete. Provide a summary of:
    - What you investigated
    - What actions you took  
    - Key findings or results
    
    Your summary will be merged with other subagent results and returned
    to the main agent."""
    category = ToolCategory.META
    
    async def execute(
        self,
        summary: str,
        findings: list[dict] | None = None,
        purpose: str = "",
    ) -> ToolResult:
        """
        Report subtask completion.
        
        Args:
            summary: Summary of what you did and found
            findings: Optional structured findings
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult with subtask_complete flag
        """
        return ToolResult(
            success=True,
            output="Subtask complete.",
            metadata={
                "subtask_complete": True,
                "summary": summary,
                "findings": findings or [],
            },
        )
        
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what you did and found",
                    },
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "description": {"type": "string"},
                                "severity": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high", "critical"],
                                },
                            },
                        },
                        "description": "Optional structured findings",
                    },
                },
                "required": ["summary"],
            },
        )


class CreateTestPlanTool(Tool):
    """Create a high-level test plan from recon findings."""
    
    name = "create_test_plan"
    description = """Create a high-level test plan from your recon findings.
    
    This is the ONLY tool available in the HYPOTHESIZE phase.
    After creating the plan, you will automatically transition to TEST phase.
    
    Items should be high-level guidance areas to investigate, NOT specific 
    vulnerability tests. The recon report provides an overview, so your plan
    should define investigation areas that will be refined during testing.
    
    Example items:
    - "Investigate authentication mechanisms for bypass vulnerabilities"
    - "Examine API endpoints for authorization flaws"
    - "Review input handling across forms and parameters"
    """
    category = ToolCategory.META
    
    def __init__(self, test_plan_manager: "TestPlanManager"):
        """
        Initialize the create test plan tool.
        
        Args:
            test_plan_manager: Component implementing TestPlanManager protocol
        """
        from tempo.infra.protocols import TestPlanManager
        self.plan_manager = test_plan_manager
    
    async def execute(
        self,
        items: list[dict],
        purpose: str = "",
    ) -> ToolResult:
        """
        Create the test plan.
        
        Args:
            items: List of items with "description" and "priority" keys
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult indicating success/failure
        """
        import uuid
        from datetime import datetime
        
        if not items:
            return ToolResult(
                success=False,
                output="",
                error="At least one item is required in the test plan.",
            )
        
        # Validate and normalize items
        valid_priorities = {"high", "medium", "low"}
        plan_items = []
        
        for i, item in enumerate(items):
            if not isinstance(item, dict) or "description" not in item:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Item {i} must be a dict with 'description' key.",
                )
            
            priority = item.get("priority", "medium").lower()
            if priority not in valid_priorities:
                priority = "medium"
            
            plan_items.append({
                "id": str(uuid.uuid4()),
                "description": item["description"],
                "priority": priority,
                "status": "pending",
                "reason": None,
                "created_at": datetime.utcnow().isoformat(),
                "completed_at": None,
            })
        
        # Set the test plan
        self.plan_manager.set_test_plan(plan_items)
        
        return ToolResult(
            success=True,
            output=f"Test plan created with {len(plan_items)} items. Transitioning to TEST phase.",
            metadata={"plan_created": True, "item_count": len(plan_items)},
        )
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {
                                    "type": "string",
                                    "description": "High-level area to investigate",
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                    "description": "Priority level",
                                },
                            },
                            "required": ["description"],
                        },
                        "description": "List of investigation areas for the test plan",
                    },
                },
                "required": ["items"],
            },
        )


class AddTodoTool(Tool):
    """Add a new item to the test plan."""
    
    name = "add_todo"
    description = """Add a new item to your test plan.
    
    Use this when testing reveals new attack vectors to investigate,
    or when you discover additional areas that need attention."""
    category = ToolCategory.META
    
    def __init__(self, test_plan_manager: "TestPlanManager"):
        """
        Initialize the add todo tool.
        
        Args:
            test_plan_manager: Component implementing TestPlanManager protocol
        """
        from tempo.infra.protocols import TestPlanManager
        self.plan_manager = test_plan_manager
    
    async def execute(
        self,
        description: str,
        priority: str = "medium",
        purpose: str = "",
    ) -> ToolResult:
        """
        Add a new item to the test plan.
        
        Args:
            description: What to investigate
            priority: high/medium/low
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult with the new item ID
        """
        valid_priorities = {"high", "medium", "low"}
        if priority.lower() not in valid_priorities:
            priority = "medium"
        
        item_id = self.plan_manager.add_test_plan_item(
            description=description,
            priority=priority.lower(),
        )
        
        return ToolResult(
            success=True,
            output=f"Added item (id: {item_id}, priority: {priority}).",
            metadata={"item_id": item_id},
        )
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "What to investigate",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Priority level (default: medium)",
                    },
                },
                "required": ["description"],
            },
        )


class CompleteTodoTool(Tool):
    """Mark a test plan item as completed or skipped."""
    
    name = "complete_todo"
    description = """Mark a test plan item as completed or skipped.
    
    Always provide a clear reason explaining:
    - If completed: What you found and whether it was vulnerable
    - If skipped: Why you couldn't or didn't need to test it"""
    category = ToolCategory.META
    
    def __init__(self, test_plan_manager: "TestPlanManager"):
        """
        Initialize the complete todo tool.
        
        Args:
            test_plan_manager: Component implementing TestPlanManager protocol
        """
        from tempo.infra.protocols import TestPlanManager
        self.plan_manager = test_plan_manager
    
    async def execute(
        self,
        item_id: str,
        status: str,
        reason: str,
        purpose: str = "",
    ) -> ToolResult:
        """
        Mark an item as completed or skipped.
        
        Args:
            item_id: ID of the item to complete
            status: "completed" or "skipped"
            reason: Explanation of findings or why skipped
            purpose: A one-sentence summary of why this tool is being called
            
        Returns:
            ToolResult indicating success/failure
        """
        valid_statuses = {"completed", "skipped"}
        if status.lower() not in valid_statuses:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid status: {status}. Must be 'completed' or 'skipped'.",
            )
        
        if not reason.strip():
            return ToolResult(
                success=False,
                output="",
                error="A reason is required when completing an item.",
            )
        
        success = self.plan_manager.complete_test_plan_item(
            item_id=item_id,
            status=status.lower(),
            reason=reason,
        )
        
        if not success:
            return ToolResult(
                success=False,
                output="",
                error=f"Item not found: {item_id}",
            )
        
        return ToolResult(
            success=True,
            output=f"Item {item_id} marked as {status}.",
            metadata={"item_id": item_id, "status": status},
        )
    
    def get_schema(self) -> ToolSchema:
        """Return the JSON schema for this tool's parameters."""
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "item_id": {
                        "type": "string",
                        "description": "ID of the test plan item",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["completed", "skipped"],
                        "description": "New status for the item",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Explanation of findings or why skipped",
                    },
                },
                "required": ["item_id", "status", "reason"],
            },
        )
