"""
Prompt builder for assembling prompts from templates.
"""

from pathlib import Path
from typing import Any

from tempo.prompts.phases import Phase, PHASE_CONFIGS


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
        
        return template.format(
            current_phase=current_phase.value,
            tool_descriptions=tool_descriptions,
            scope_description=scope_description,
            hypotheses_count=hypotheses_count,
            findings_count=findings_count,
        )
    
    def build_phase_prompt(self, phase: Phase) -> str:
        """
        Build the phase-specific prompt.
        
        Args:
            phase: The workflow phase
            
        Returns:
            Formatted phase prompt
        """
        template_name = f"phase_{phase.value}"
        return self._load_template(template_name)
    
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
        
        return template.format(
            subtask_objective=subtask_objective,
            tool_descriptions=tool_descriptions,
        )
    
    def format_tool_descriptions(self, schemas: list[dict]) -> str:
        """
        Format tool schemas into a readable description for prompts.
        
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
    
    def build_recon_prompt(
        self,
        objective: str,
        tool_schemas: list[dict],
        scope_description: str = "No specific scope defined.",
    ) -> str:
        """
        Build the system prompt for standalone recon agent.
        
        This prompt does NOT include phase transition instructions.
        
        Args:
            objective: The target/objective for recon
            tool_schemas: List of tool schemas
            scope_description: Scope/limits for testing
            
        Returns:
            Formatted recon system prompt
        """
        tool_descriptions = self.format_tool_descriptions(tool_schemas)
        template = self._load_template("recon_system")
        
        return template.format(
            objective=objective,
            tool_descriptions=tool_descriptions,
            scope_description=scope_description,
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
    
    def build_phase_transition_prompt(
        self,
        from_phase: Phase,
        to_phase: Phase,
        objective: str,
        phase_context: dict,
    ) -> str:
        """
        Build a prompt for summarizing a phase transition.
        
        Includes the prompts for both the source and target phases so the
        summarizer understands what was expected and what comes next.
        
        Args:
            from_phase: The phase we're leaving
            to_phase: The phase we're entering
            objective: Current agent objective
            phase_context: Extracted context from the phase (tool calls, messages, state)
            
        Returns:
            Formatted transition summarization prompt
        """
        template = self._load_template("phase_transition_summary")
        
        # Load the phase prompts for context
        from_phase_prompt = self.build_phase_prompt(from_phase)
        to_phase_prompt = self.build_phase_prompt(to_phase)
        
        import json
        context_str = json.dumps(phase_context, indent=2, default=str)
        
        return template.format(
            from_phase=from_phase.value,
            to_phase=to_phase.value,
            objective=objective,
            from_phase_prompt=from_phase_prompt,
            to_phase_prompt=to_phase_prompt,
            phase_context=context_str,
        )
