"""
Test plan management tools.

Provides tools for creating and managing the test plan checklist:
- CreateTestPlanTool: Create initial test plan from recon findings
- AddTodoTool: Add new items during testing
- CompleteTodoTool: Mark items as completed/skipped
"""

from typing import TYPE_CHECKING

from tempo.tools.base import Tool, ToolCategory, ToolResult, ToolSchema

if TYPE_CHECKING:
    from tempo.infra.protocols import TestPlanManager


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
