"""
Agent configuration dataclass.

Contains all settings for the agent runtime including model settings,
context management, workflow, branching, container, scope, and debugging.
"""

from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """Configuration for the agent runtime."""
    
    # Model settings
    model: str = "anthropic/claude-sonnet-4-20250514"
    phase_summarization_model: str = "gemini/gemini-3-flash-preview"  # Fast model for phase summaries
    # temperature and max_tokens are managed by the model/provider defaults or per-request logic
    
    # Context management
    max_context_tokens: int = 100000        # Trigger summarization near this limit
    auto_summarize: bool = True             # Automatically summarize tool outputs
    summarization_model: str | None = None  # Use cheaper model for summaries (None = same model)
    max_output_chars: int = 10000           # Chars to show per tool output (LLM can request more)
    auto_phase_summary: bool = True         # Generate summaries on phase transitions
    
    # Workflow settings
    enforce_phases: bool = True             # Require explicit phase transitions
    max_steps_per_phase: int = 20           # Prevent runaway phases
    max_total_steps: int = 100              # Hard limit on agent steps
    
    # Branching settings
    max_branches: int = 5                   # Maximum parallel branches
    max_branch_depth: int = 3               # Maximum nested branching
    branch_step_limit: int = 10             # Max steps per branch
    
    # Container settings
    container_image: str = "tempo-sec-base:latest"
    container_timeout: int = 300            # Seconds
    
    # Persistence
    persistence_dir: str = "./contexts"
    auto_checkpoint: bool = True            # Checkpoint after each tool call

    # Scope
    allowed_domains: list[str] = field(default_factory=list)
    excluded_domains: list[str] = field(default_factory=list)
    allow_subdomains: bool = True
    
    # Debugging
    verbose: bool = False
    log_level: str = "INFO"
    
    # Visualization
    enable_visualization: bool = True
    visualization_port: int = 8080
    visualization_host: str = "127.0.0.1"
    auto_open_browser: bool = True
    
    # Legacy/convenience aliases
    scope: str | None = None  # Optional scope description
    
    @property
    def max_steps(self) -> int:
        """Alias for max_total_steps."""
        return self.max_total_steps

