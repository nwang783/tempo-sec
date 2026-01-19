"""
Browser Agent Definition.

A specialized agent for browser automation tasks that can be invoked
by parent agents to handle web interaction subtasks.
"""

import logging
import os
from typing import TYPE_CHECKING, Any

from tempo.agents.base import BaseAgentDefinition
from tempo.agents import register_agent
from tempo.infra.protocols import DEFAULT_SCOPE_PLACEHOLDERS

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.infra.container import ContainerManager
    from tempo.tools.registry import ToolRegistry
    from tempo.prompts.builder import PromptBuilder
    from tempo.infra.protocols import FindingsUpdater
    from tempo.tools.network_capture import NetworkRequestCapture


logger = logging.getLogger(__name__)


def _parse_env_int(env_var: str, default: int | None = None) -> int | None:
    """
    Parse an integer from an environment variable with validation.

    Args:
        env_var: Name of the environment variable
        default: Default value if not set

    Returns:
        Parsed integer value, or default if not set

    Logs a warning and returns default if the value is not a valid integer.
    """
    value = os.getenv(env_var)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning(
            f"Invalid value for {env_var}: '{value}' is not an integer. "
            f"Using default: {default}"
        )
        return default


@register_agent
class BrowserAgent(BaseAgentDefinition):
    """
    Browser automation agent for web interaction tasks.
    
    This agent is designed to be invoked as a sub-agent by parent agents
    (like Recon or TestCycle) to handle specific browser-based tasks.
    
    Features:
    - Browser-only tools (navigate, snapshot, click, type, fill_form)
    - Visual tools (screenshot, coordinate click, scroll, wait)
    - Task completion tool to signal done and return findings
    - Scope support for constrained browsing
    - Focused, single-purpose prompt
    - Fast model for quick browser tasks
    """
    
    _name = "browser"
    _model = "openai/gpt-5.1"  # Vision-capable model for visual browsing
    
    def __init__(
        self,
        task: str,
        url: str | None = None,
        scope: str | None = None,
        headless: bool = True,
        findings: "FindingsUpdater | None" = None,
        agent_email: str | None = None,
        imap_config: dict | None = None,
        use_browser_use_llm: bool = False,
        **kwargs: Any,
    ):
        """
        Initialize the browser agent.

        Args:
            task: Description of the browser task to accomplish
            url: Optional starting URL to navigate to
            scope: Optional scope constraints for the browser agent
            headless: Whether to run browser in headless mode
            findings: Optional FindingsDocument for accessing prior work
            agent_email: Optional email address for signups
            imap_config: Optional IMAP config dict {host, port, password}
            use_browser_use_llm: Use browser-use's ChatBrowserUse model (if True) or gpt-5.1 via OpenRouter (if False)
            **kwargs: Ignored additional args
        """
        self.task = task
        self.url = url
        self.scope = scope
        self.headless = headless
        self.findings = findings
        self.agent_email = agent_email
        self.imap_config = imap_config
        self.use_browser_use_llm = use_browser_use_llm
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return "Browser automation agent for web interaction tasks"

    def create_tools(
        self,
        context: "ContextStore",
        container: "ContainerManager | None" = None,
        **kwargs: Any,
    ) -> "ToolRegistry":
        """
        BrowserAgent should not be instantiated via create_tools().

        Use BrowserTaskTool instead, which calls create_browser_use_agent().
        This agent uses browser-use integration and doesn't follow the standard
        agent pattern.

        Raises:
            NotImplementedError: Always - this method should never be called
        """
        raise NotImplementedError(
            "BrowserAgent should not be used directly. "
            "Use BrowserTaskTool instead, which handles browser-use integration. "
            "Example: tools.register(BrowserTaskTool(container_manager=container))"
        )

    def create_browser_use_agent(
        self,
        container: "ContainerManager | None" = None,
        network_capture: "NetworkRequestCapture | None" = None,
    ):
        """
        Create a browser-use Agent with custom tempo-sec tools.

        This replaces the old create_tools() method and directly creates
        a browser-use Agent instance configured with custom tools.

        Args:
            container: Container manager for shell/file operations
            network_capture: Optional NetworkRequestCapture for network request visibility

        Returns:
            Tuple of (browser-use Agent instance, Browser instance, Tools instance, NetworkRequestCapture or None)
        """
        from browser_use import Agent, Browser
        from browser_use.tools.service import Tools
        from tempo.infra.browser_use_llm import create_browser_use_llm
        from tempo.tools.browser_use_adapter import BrowserUseToolsAdapter

        # Create browser-use Browser (BrowserSession) instance
        # Note: No allowed_domains restriction - agent can navigate freely.
        # Scope is provided as guidance in the prompt, not enforced at browser level.
        browser = Browser(
            headless=self.headless,
            use_cloud=False,  # Use local browser
            allowed_domains=None,
            # Reduce flakiness on JS-heavy pages (souschefhub is slow to become "ready")
            minimum_wait_page_load_time=1.0,
            wait_for_network_idle_page_load_time=3.0,
        )

        # Create a single shared Tools instance
        shared_tools = Tools()

        # Create custom tools adapter with shared Tools instance
        tools_adapter = BrowserUseToolsAdapter(
            container_manager=container,
            findings_updater=self.findings,
            imap_config=self.imap_config,
            agent_email=self.agent_email,
            tools_instance=shared_tools,  # Pass shared instance
            network_capture=network_capture,  # Pass network capture for tool registration
        )

        # Select LLM based on configuration
        llm = create_browser_use_llm(
            use_browser_use_llm=self.use_browser_use_llm,
            litellm_client=None,  # Not needed for OpenRouter approach
            model=os.getenv("TEMPO_BROWSER_MODEL") or "gpt-5-mini",
        )

        # Build task description with URL if provided
        task_description = self.task
        if self.url:
            task_description = f"{self.task}\n\nStarting URL: {self.url}"

        # Create browser-use Agent
        # Allow runtime overrides for stability testing (Debug Mode / ops tuning).
        # Defaults preserve browser-use behavior (model-derived llm_timeout, max_failures=3).
        llm_timeout_val = _parse_env_int("TEMPO_BROWSER_USE_LLM_TIMEOUT")
        max_failures_val = _parse_env_int("TEMPO_BROWSER_USE_MAX_FAILURES", default=3)
        max_history_items_val = _parse_env_int("TEMPO_BROWSER_USE_MAX_HISTORY_ITEMS")

        # Evidence-based default: gpt-5.* can exceed 60s when prompts get large
        # (we observed CancelledError + 60s timeout). Apply guardrails for gpt-5 models.
        model_name = str(getattr(llm, "model", "")).lower()
        if "gpt-5" in model_name:
            # Guardrail: enforce minimum timeout that avoids known cancellations.
            if llm_timeout_val is None or llm_timeout_val < 120:
                logger.info(
                    f"Applying GPT-5 guardrail: llm_timeout={120}s "
                    f"(was {llm_timeout_val or 'unset'})"
                )
                llm_timeout_val = 120
            # Guardrail: avoid overly-low failure caps which exacerbate intermittent provider issues.
            if max_failures_val < 3:
                logger.info(
                    f"Applying GPT-5 guardrail: max_failures={3} (was {max_failures_val})"
                )
                max_failures_val = 3

        agent = Agent(
            task=task_description,
            llm=llm,
            browser=browser,
            tools=shared_tools,  # Use the shared Tools instance
            llm_timeout=llm_timeout_val,
            max_failures=max_failures_val,
            max_history_items=max_history_items_val,
        )

        return agent, browser, shared_tools
    
    def build_system_prompt(
        self,
        prompts: "PromptBuilder",
        tool_schemas: list[dict],
        scope_description: str,
    ) -> str:
        """
        Build browser-specific system prompt.

        Uses a focused prompt without security testing context.
        Includes scope constraints and findings context if provided.
        """
        # Get findings context
        findings_context = self._get_findings_context()

        # Pass scope if it's not a placeholder value
        scope_content = None
        if scope_description and scope_description not in DEFAULT_SCOPE_PLACEHOLDERS:
            scope_content = scope_description

        # Also check self.scope which may be passed directly
        if self.scope and not scope_content:
            scope_content = self.scope

        return prompts.build_browser_prompt(
            tool_schemas=tool_schemas,
            scope_content=scope_content,
            findings_context=findings_context,
            agent_email=self.agent_email,
        )
    
    def build_objective(self, target: str | None = None, **kwargs: Any) -> str:
        """
        Build the browser task objective.
        
        Args:
            target: Ignored (uses url from init)
            **kwargs: Ignored
            
        Returns:
            Formatted objective with task and URL
        """
        objective_parts = [f"**Task**: {self.task}"]
        
        if self.url:
            objective_parts.append(f"\n**Starting URL**: {self.url}")
        else:
            objective_parts.append("\n**Starting URL**: Navigate as needed to accomplish the task")
        
        objective_parts.append("\nComplete the task and call `complete_browser_task` with your findings.")

        return "\n".join(objective_parts)

    def _get_findings_context(self) -> str:
        """Get findings context to avoid duplicating prior work."""
        if not self.findings:
            return "No prior findings available."

        try:
            summary = self.findings.get_summary()
            lines = [
                f"Target: {summary.get('target', 'Unknown')}",
                f"Attack Surfaces: {summary.get('total_surfaces', 0)} discovered, "
                f"{summary.get('tested_surfaces', 0)} tested",
                f"Findings: {summary.get('total_findings', 0)} total",
            ]

            # Include all attack surfaces
            all_surfaces = self.findings.get_all_surfaces()
            if all_surfaces:
                lines.append("\n### Attack Surfaces Discovered ###")
                for s in all_surfaces[:15]:  # Limit to first 15 for browser context
                    sid = getattr(s, 'id', 'unknown')
                    stype = getattr(s, 'surface_type', 'unknown')
                    url = getattr(s, 'url', 'unknown')
                    tested = getattr(s, 'tested', False)
                    status_str = "TESTED" if tested else "UNTESTED"
                    lines.append(f"- [{status_str}] {stype}: {url}")

                if len(all_surfaces) > 15:
                    lines.append(f"... and {len(all_surfaces) - 15} more")

            # Include findings summaries
            all_findings = self.findings.get_all_findings()
            if all_findings:
                lines.append("\n### Security Findings ###")
                for f in all_findings[:10]:  # Limit to first 10
                    title = getattr(f, 'title', 'No Title')
                    severity = getattr(f, 'severity', 'unknown')
                    status = getattr(f, 'status', 'unknown')
                    lines.append(f"- [{severity.upper()}] {title} ({status})")

                if len(all_findings) > 10:
                    lines.append(f"... and {len(all_findings) - 10} more")

            return "\n".join(lines)
        except Exception:
            return "No prior findings available."
