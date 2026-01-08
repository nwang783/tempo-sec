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
    # temperature and max_tokens are managed by the model/provider defaults or per-request logic
    
    # Context management
    max_context_tokens: int = 100000        # Trigger summarization near this limit
    auto_summarize: bool = True             # Automatically summarize tool outputs
    summarization_model: str | None = None  # Use cheaper model for summaries (None = same model)
    max_output_chars: int = 10000           # Chars to show per tool output (LLM can request more)
    
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
    
    # Manifest settings (for recon/testing split workflow)
    manifest_path: str | None = None        # Path to load manifest (for test_cycle.py)
    manifest_output_dir: str = "./manifests" # Directory to save manifests (for recon.py)

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

    # Orchestrator settings
    max_concurrent_subagents: int = 3  # Max parallel subagent dispatches

    # Browser settings
    browser_state_dir: str = "~/.tempo-sec/browser_states"
    browser_state_ttl_days: int = 7
    browser_headless: bool = True
    browser_default_timeout: int = 30000  # milliseconds
    browser_viewport_width: int = 1280
    browser_viewport_height: int = 720

    # Legacy/convenience aliases
    scope: str | None = None  # Optional scope description
    scope_file: str | None = None  # Path to scope file (set via CLI)
    
    @property
    def max_steps(self) -> int:
        """Alias for max_total_steps."""
        return self.max_total_steps

    @classmethod
    def from_toml(cls, path: str) -> "AgentConfig":
        """
        Load configuration from a TOML file.
        
        The TOML file sections are mapped to AgentConfig fields:
        - [model].provider → model
        - [context].* → max_context_tokens, auto_summarize, persistence_dir, etc.
        - [workflow].* → enforce_phases, max_steps_per_phase, max_total_steps
        - [branching].* → max_branches, max_branch_depth, branch_step_limit
        - [container].* → container_image, container_timeout
        - [scope].* → allowed_domains, excluded_domains, allow_subdomains
        - [visualization].* → enable_visualization, visualization_port, auto_open_browser
        - [logging].* → log_level, verbose
        
        Args:
            path: Path to the TOML configuration file
            
        Returns:
            AgentConfig with values loaded from the file
            
        Raises:
            FileNotFoundError: If the TOML file doesn't exist
        """
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        
        from pathlib import Path
        
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentConfig":
        """
        Create AgentConfig from a dictionary (typically loaded from TOML).
        
        Args:
            data: Configuration dictionary with section keys
            
        Returns:
            AgentConfig with mapped values
        """
        kwargs = {}
        
        # [model] section
        if "model" in data:
            model_data = data["model"]
            if "provider" in model_data:
                kwargs["model"] = model_data["provider"]
        
        # [context] section
        if "context" in data:
            ctx = data["context"]
            if "max_tokens" in ctx:
                kwargs["max_context_tokens"] = ctx["max_tokens"]
            if "auto_summarize" in ctx:
                kwargs["auto_summarize"] = ctx["auto_summarize"]
            if "persistence_dir" in ctx:
                kwargs["persistence_dir"] = ctx["persistence_dir"]
            if "max_output_chars" in ctx:
                kwargs["max_output_chars"] = ctx["max_output_chars"]
        
        # [workflow] section
        if "workflow" in data:
            wf = data["workflow"]
            if "enforce_phases" in wf:
                kwargs["enforce_phases"] = wf["enforce_phases"]
            if "max_steps_per_phase" in wf:
                kwargs["max_steps_per_phase"] = wf["max_steps_per_phase"]
            if "max_total_steps" in wf:
                kwargs["max_total_steps"] = wf["max_total_steps"]
        
        # [branching] section
        if "branching" in data:
            br = data["branching"]
            if "max_branches" in br:
                kwargs["max_branches"] = br["max_branches"]
            if "max_branch_depth" in br:
                kwargs["max_branch_depth"] = br["max_branch_depth"]
            if "branch_step_limit" in br:
                kwargs["branch_step_limit"] = br["branch_step_limit"]
        
        # [container] section
        if "container" in data:
            cont = data["container"]
            if "image" in cont:
                kwargs["container_image"] = cont["image"]
            if "timeout" in cont:
                kwargs["container_timeout"] = cont["timeout"]
        
        # [scope] section
        if "scope" in data:
            sc = data["scope"]
            if "allowed_domains" in sc:
                kwargs["allowed_domains"] = sc["allowed_domains"]
            if "excluded_domains" in sc:
                kwargs["excluded_domains"] = sc["excluded_domains"]
            if "allow_subdomains" in sc:
                kwargs["allow_subdomains"] = sc["allow_subdomains"]
        
        # [visualization] section
        if "visualization" in data:
            vis = data["visualization"]
            if "enabled" in vis:
                kwargs["enable_visualization"] = vis["enabled"]
            if "port" in vis:
                kwargs["visualization_port"] = vis["port"]
            if "auto_open_browser" in vis:
                kwargs["auto_open_browser"] = vis["auto_open_browser"]
        
        # [logging] section
        if "logging" in data:
            log = data["logging"]
            if "level" in log:
                kwargs["log_level"] = log["level"]
            if "verbose" in log:
                kwargs["verbose"] = log["verbose"]
        
        # [manifest] section
        if "manifest" in data:
            m = data["manifest"]
            if "path" in m:
                kwargs["manifest_path"] = m["path"]
            if "output_dir" in m:
                kwargs["manifest_output_dir"] = m["output_dir"]

        # [orchestrator] section
        if "orchestrator" in data:
            orch = data["orchestrator"]
            if "max_concurrent" in orch:
                kwargs["max_concurrent_subagents"] = orch["max_concurrent"]

        # [browser] section
        if "browser" in data:
            br = data["browser"]
            if "state_dir" in br:
                kwargs["browser_state_dir"] = br["state_dir"]
            if "state_ttl_days" in br:
                kwargs["browser_state_ttl_days"] = br["state_ttl_days"]
            if "headless" in br:
                kwargs["browser_headless"] = br["headless"]
            if "default_timeout" in br:
                kwargs["browser_default_timeout"] = br["default_timeout"]
            if "viewport_width" in br:
                kwargs["browser_viewport_width"] = br["viewport_width"]
            if "viewport_height" in br:
                kwargs["browser_viewport_height"] = br["viewport_height"]

        return cls(**kwargs)

