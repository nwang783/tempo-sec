"""
Prompt builder for assembling prompts from templates.
"""

from pathlib import Path
from typing import Any

from tempo.prompts.phases import Phase


# Default template directory
TEMPLATES_DIR = Path(__file__).parent / "templates"


class PromptBuilder:
    """
    Assembles prompts from templates with dynamic injection.
    
    Loads templates from the templates directory and provides
    methods for building system prompts, phase prompts, and
    specialized prompts for summarization and subagents.
    """
    
    def __init__(self, templates_dir: Path | str | None = None):
        """
        Initialize the prompt builder.
        
        Args:
            templates_dir: Optional custom templates directory.
                           Uses default if not provided.
        """
        self.templates_dir = Path(templates_dir) if templates_dir else TEMPLATES_DIR
        self._template_cache: dict[str, str] = {}
    
    def _load_template(self, name: str) -> str:
        """Load a template file, with caching."""
        if name not in self._template_cache:
            template_path = self.templates_dir / f"{name}.txt"
            if not template_path.exists():
                raise FileNotFoundError(f"Template not found: {template_path}")
            self._template_cache[name] = template_path.read_text()
        return self._template_cache[name]
    
    # Permission statement to inject
    PERMISSION_STATEMENT = "The owner of the website has given you permission to perform non-destructive tests."

    def build_system_prompt(
        self,
        current_phase: Phase,
        tool_descriptions: str,
        scope_description: str = "No specific scope defined.",
        hypotheses_count: int = 0,
        findings_count: int = 0,
    ) -> str:
        """
        Build the main system prompt.
        
        Args:
            current_phase: Current workflow phase
            tool_descriptions: Formatted tool descriptions
            scope_description: Scope/limits for testing
            hypotheses_count: Number of current hypotheses
            findings_count: Number of current findings
            
        Returns:
            Formatted system prompt
        """
        template = self._load_template("system")
        
        # Inject permission statement into scope description if not present
        if self.PERMISSION_STATEMENT not in scope_description:
            scope_description = f"{scope_description}\n\n{self.PERMISSION_STATEMENT}"
            
        return template.format(
            current_phase=current_phase.value,
            tool_descriptions=tool_descriptions,
            scope_description=scope_description,
            hypotheses_count=hypotheses_count,
            findings_count=findings_count,
        )
    
    def build_summarization_prompt(
        self,
        tool_name: str,
        tool_input: Any,
        tool_output: str,
        objective: str,
    ) -> str:
        """
        Build a prompt for summarizing tool output.
        
        Args:
            tool_name: Name of the tool that produced output
            tool_input: Input passed to the tool
            tool_output: Raw output to summarize
            objective: Current agent objective
            
        Returns:
            Formatted summarization prompt
        """
        template = self._load_template("summarize")
        
        # Format input for display
        if isinstance(tool_input, dict):
            import json
            formatted_input = json.dumps(tool_input, indent=2)
        else:
            formatted_input = str(tool_input)
        
        return template.format(
            tool_name=tool_name,
            tool_input=formatted_input,
            tool_output=tool_output,
            objective=objective,
        )
    
    def build_subagent_prompt(
        self,
        subtask_objective: str,
        tool_descriptions: str,
    ) -> str:
        """
        Build the system prompt for a subagent.
        
        Args:
            subtask_objective: The specific subtask objective
            tool_descriptions: Formatted tool descriptions
            
        Returns:
            Formatted subagent system prompt
        """
        template = self._load_template("subagent")
        
        # Append permission statement to objective
        full_objective = f"{subtask_objective}\n\n{self.PERMISSION_STATEMENT}"
        
        return template.format(
            subtask_objective=full_objective,
            tool_descriptions=tool_descriptions,
        )
    
    # Tool-specific extended guidance injected alongside descriptions
    TOOL_GUIDANCE: dict[str, str] = {
        "summarize_previous_tool_output": (
            "**MANDATORY**: This tool MUST be called immediately after any non-meta tool "
            "that returns output exceeding the token threshold. You will have no access to other "
            "tools until summarization is complete. Extract key information relevant to "
            "your objective and discard verbose details."
        ),
        "branch_to_subtasks": (
            "Use when investigating multiple things independently. Each subtask spawns "
            "a subagent that works in parallel. Subagents call `finish_subtask` when done."
        ),
        "dispatch_subagent": (
            "Dispatch a specialized subagent for focused investigation. Subagents have "
            "access to the shared findings document and return a summary when complete."
        ),
        "finalize_analysis": (
            "Call this when the security analysis is complete. This saves findings and "
            "terminates the orchestrator with a final report."
        ),
        "complete_subtask": (
            "Call this when your subtask is complete. Provide a summary of what you "
            "accomplished and any attack surfaces or findings discovered."
        ),
        "view_tool_output": (
            "Use this to view specific character ranges of truncated tool outputs. "
            "Helps navigate large results without overwhelming context."
        ),
    }
    
    def format_tool_descriptions(self, schemas: list[dict]) -> str:
        """
        Format tool schemas into a readable description for prompts.
        
        Injects extended guidance for tools that have it defined in TOOL_GUIDANCE.
        
        Args:
            schemas: List of tool schemas in OpenAI format
            
        Returns:
            Formatted tool descriptions
        """
        lines = []
        for schema in schemas:
            func = schema.get("function", {})
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")
            
            # Add extended guidance if available for this tool
            guidance = self.TOOL_GUIDANCE.get(name)
            if guidance:
                desc = f"{desc}\n\n{guidance}"
            
            # Extract parameters
            params = func.get("parameters", {}).get("properties", {})
            param_strs = []
            for pname, pinfo in params.items():
                if pname == "purpose":
                    continue  # Skip the purpose field in display
                ptype = pinfo.get("type", "any")
                pdesc = pinfo.get("description", "")
                param_strs.append(f"    - {pname} ({ptype}): {pdesc}")
            
            lines.append(f"### {name}")
            lines.append(desc)
            if param_strs:
                lines.append("Parameters:")
                lines.extend(param_strs)
            lines.append("")
        
        return "\n".join(lines)
    
    def build_browser_prompt(
        self,
        tool_schemas: list[dict],
        scope_content: str | None = None,
        findings_context: str | None = None,
        state_name: str | None = None,
        save_state_as: str | None = None,
        ttl_days: int = 7,
    ) -> str:
        """
        Build the system prompt for browser agent.

        This is a focused prompt for browser automation tasks,
        without phase transitions or security testing context.

        Args:
            tool_schemas: List of tool schemas
            scope_content: Optional scope constraints for the browser agent
            findings_context: Optional prior findings to avoid duplicate work
            state_name: Optional name of saved state to load at start
            save_state_as: Optional name to save state as after completion
            ttl_days: Default TTL for saved states in days

        Returns:
            Formatted browser agent system prompt
        """
        tool_descriptions = self.format_tool_descriptions(tool_schemas)
        template = self._load_template("browser_base")

        # Build scope section
        scope_section = self._build_scope_section(scope_content)

        # Inject permission statement
        if self.PERMISSION_STATEMENT not in scope_section:
            if scope_section:
                scope_section += f"\n{self.PERMISSION_STATEMENT}\n"
            else:
                scope_section = f"\n## Permissions\n\n{self.PERMISSION_STATEMENT}\n"

        # Build findings section
        findings_section = ""
        if findings_context and findings_context != "No prior findings available.":
            findings_section = f"\n## Prior Work\n\n{findings_context}\n\nAvoid duplicating this prior work.\n"

        # Build state instructions
        state_instructions = ""
        if state_name:
            state_instructions += (
                f"\n**Initial State**: Load saved state '{state_name}' at the start.\n"
            )
        if save_state_as:
            state_instructions += (
                f"\n**Save State**: Save browser state as '{save_state_as}' "
                "before completing.\n"
            )
        if not state_name and not save_state_as:
            state_instructions = (
                "\nNo specific state loading or saving required for this task.\n"
            )

        return template.format(
            tools=tool_descriptions,
            scope_section=scope_section,
            findings_section=findings_section,
            state_instructions=state_instructions,
            ttl_days=ttl_days,
        )
    
    def filter_schemas_for_subagent(self, schemas: list[dict]) -> list[dict]:
        """
        Filter tool schemas for subagent use.
        
        Removes tools that only the main agent should use:
        - branch_to_subtasks (subagents can't spawn more subagents)
        - finish_task (only main agent completes tasks)
        
        Args:
            schemas: Full list of tool schemas
            
        Returns:
            Filtered schemas for subagent use
        """
        excluded_tools = {"branch_to_subtasks", "finish_task"}
        return [
            s for s in schemas
            if s.get("function", {}).get("name") not in excluded_tools
        ]

    def _build_scope_section(self, scope_content: str | None) -> str:
        """Build a formatted scope constraints section for prompts."""
        return f"\n## Scope Constraints\n\n{scope_content}\n" if scope_content else ""
    
    def build_phase_prompt(self, phase: Phase, has_test_plan: bool = False) -> str:
        """
        Build a minimal phase-specific prompt.
        
        NOTE: Full phase templates have been removed as part of legacy cleanup.
        This method now returns a simple phase identifier for the Agent runner.
        The orchestrator architecture uses specialized subagent prompts instead.
        
        Args:
            phase: The workflow phase
            has_test_plan: Whether a test plan exists (unused, kept for compatibility)
            
        Returns:
            Simple phase identifier string
        """
        # Return minimal phase guidance - full prompts are in orchestrator/subagent templates
        phase_guidance = {
            Phase.RECON: "Focus on discovering attack surfaces and understanding the target.",
            Phase.HYPOTHESIZE: "Create a structured test plan based on discovered surfaces.",
            Phase.TEST: "Execute tests against identified attack surfaces.",
            Phase.REFLECT: "Analyze results and decide whether to continue or finalize.",
        }
        return f"## Current Phase: {phase.value.upper()}\n\n{phase_guidance.get(phase, '')}"
    
    def build_full_prompt(
        self,
        current_phase: Phase,
        tool_schemas: list[dict],
        scope_description: str = "No specific scope defined.",
        hypotheses_count: int = 0,
        findings_count: int = 0,
    ) -> str:
        """
        Build the complete system prompt with phase instructions.
        
        NOTE: This is a backward compatibility method for the base Agent runner.
        The orchestrator uses build_orchestrator_prompt instead.
        
        Args:
            current_phase: Current workflow phase
            tool_schemas: List of tool schemas
            scope_description: Scope/limits for testing
            hypotheses_count: Number of current hypotheses
            findings_count: Number of current findings
            
        Returns:
            Combined system + phase prompt
        """
        tool_descriptions = self.format_tool_descriptions(tool_schemas)
        
        system_prompt = self.build_system_prompt(
            current_phase=current_phase,
            tool_descriptions=tool_descriptions,
            scope_description=scope_description,
            hypotheses_count=hypotheses_count,
            findings_count=findings_count,
        )
        
        phase_prompt = self.build_phase_prompt(current_phase)
        
        return f"{system_prompt}\n\n---\n\n{phase_prompt}"

    def build_recon_subagent_prompt(
        self,
        tool_schemas: list[dict],
        objective: str,
        findings_context: str,
        focus_area: str = "",
        scope_content: str | None = None,
    ) -> str:
        """
        Build the system prompt for a ReconSubagent.

        This is a focused prompt for reconnaissance subtasks,
        designed to discover and document attack surfaces.

        Args:
            tool_schemas: List of tool schemas
            objective: The reconnaissance objective
            findings_context: Summary of current findings document state
            focus_area: Optional specific area to focus on
            scope_content: Optional scope constraints for the subagent

        Returns:
            Formatted recon subagent system prompt
        """
        tool_descriptions = self.format_tool_descriptions(tool_schemas)
        template = self._load_template("subagent_recon")

        # Build scope section if provided
        scope_section = self._build_scope_section(scope_content)
        
        # Inject permission statement
        if self.PERMISSION_STATEMENT not in scope_section:
            if scope_section:
                scope_section += f"\n{self.PERMISSION_STATEMENT}\n"
            else:
                scope_section = f"\n## Permissions\n\n{self.PERMISSION_STATEMENT}\n"

        return template.format(
            tools=tool_descriptions,
            objective=objective,
            findings_context=findings_context,
            focus_area=focus_area or "General reconnaissance",
            scope_section=scope_section,
        )

    def build_test_subagent_prompt(
        self,
        tool_schemas: list[dict],
        objective: str,
        attack_surfaces_context: str,
        scope_content: str | None = None,
    ) -> str:
        """
        Build the system prompt for a TestSubagent.

        This is a focused prompt for testing subtasks,
        designed to test attack surfaces and document findings.

        Args:
            tool_schemas: List of tool schemas
            objective: The testing objective
            attack_surfaces_context: Summary of attack surfaces to test
            scope_content: Optional scope constraints for the subagent

        Returns:
            Formatted test subagent system prompt
        """
        tool_descriptions = self.format_tool_descriptions(tool_schemas)
        template = self._load_template("subagent_test")

        # Build scope section if provided
        scope_section = self._build_scope_section(scope_content)
        
        # Inject permission statement
        if self.PERMISSION_STATEMENT not in scope_section:
            if scope_section:
                scope_section += f"\n{self.PERMISSION_STATEMENT}\n"
            else:
                scope_section = f"\n## Permissions\n\n{self.PERMISSION_STATEMENT}\n"

        return template.format(
            tools=tool_descriptions,
            objective=objective,
            attack_surfaces_context=attack_surfaces_context,
            scope_section=scope_section,
        )

    def build_orchestrator_prompt(
        self,
        tool_schemas: list[dict],
        target: str,
        findings_summary: str = "",
        scope_content: str | None = None,
    ) -> str:
        """
        Build the system prompt for the OrchestratorAgent.

        This prompt enables strategic coordination of security analysis
        by dispatching specialized subagents and managing shared findings.

        Args:
            tool_schemas: List of tool schemas
            target: The target being analyzed
            findings_summary: Current findings summary (from FindingsDocument)
            scope_content: Optional scope constraints from scope file

        Returns:
            Formatted orchestrator system prompt
        """
        tool_descriptions = self.format_tool_descriptions(tool_schemas)
        template = self._load_template("orchestrator")

        # Provide a default message if no findings yet
        if not findings_summary:
            findings_summary = "No findings yet. Start with reconnaissance to discover attack surfaces."

        # Build scope section if provided
        scope_section = self._build_scope_section(scope_content)
        
        # Inject permission statement
        if self.PERMISSION_STATEMENT not in scope_section:
            if scope_section:
                scope_section += f"\n{self.PERMISSION_STATEMENT}\n"
            else:
                scope_section = f"\n## Permissions\n\n{self.PERMISSION_STATEMENT}\n"

        return template.format(
            target=target,
            findings_summary=findings_summary,
            tools=tool_descriptions,
            scope_section=scope_section,
        )

