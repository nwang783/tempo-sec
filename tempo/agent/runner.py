"""
Agent runner - main loop and step execution.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from tempo.agent.config import AgentConfig
from tempo.agent.summarizer import OutputSummarizer

from tempo.agent.branch_coordinator import BranchCoordinator, SubtaskResult
from tempo.agent.step_handler import StepHandler, SpecialToolResult
from tempo.context.store import ContextStore
from tempo.context.frame import MessageRole, ToolCall
from tempo.infra.llm import LLMClient, LLMResponse
from tempo.infra.output_storage import TruncatedOutputStorage
from tempo.infra.tokenizer import count_tokens
from tempo.prompts.builder import PromptBuilder
from tempo.tools.registry import ToolRegistry
from tempo.tools.base import ToolResult

# Threshold for mandatory summarization of tool outputs
SUMMARIZATION_TOKEN_THRESHOLD = 100

# Marker prefix for summarization prompt messages (for easy identification/removal)
SUMMARIZATION_PROMPT_MARKER = "[SUMMARIZATION_REQUIRED]"

if TYPE_CHECKING:
    from tempo.visualization.prompt_manager import UserPromptManager

try:
    from tempo.visualization.collector import VisualizationCollector
except ImportError:
    VisualizationCollector = None



@dataclass
class StepResult:
    """Result of a single agent step."""
    step_number: int
    llm_response: LLMResponse
    tool_calls: list[ToolCall] = field(default_factory=list)
    should_continue: bool = True
    error: str | None = None


@dataclass
class AgentResult:
    """Final result of an agent run."""
    success: bool
    objective: str
    steps_taken: int
    findings: list[dict] = field(default_factory=list)
    hypotheses: list[dict] = field(default_factory=list)
    context_id: str = ""  # For resumption
    paused: bool = False
    error: str | None = None


class Agent:
    """
    Main agent class that orchestrates the security testing workflow.
    
    Manages the agent loop, tool execution, and context management.
    Note: Phase logic has been removed; phases are now soft guidance in prompts only.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        llm: LLMClient,
        tools: ToolRegistry,
        context: ContextStore | None = None,
        prompts: PromptBuilder | None = None,
        on_step: "Callable[[StepResult], None] | None" = None,
        on_tool_call: "Callable[[ToolCall], None] | None" = None,
        visualization_collector: "VisualizationCollector | None" = None,
        prompt_manager: "UserPromptManager | None" = None,
        stop_event: "asyncio.Event | None" = None,
        pause_event: "asyncio.Event | None" = None,
    ):
        """
        Initialize the agent.
        
        Args:
            config: Agent configuration
            llm: LLM client for completions
            tools: Tool registry
            context: Context store (created if not provided)
            prompts: Prompt builder (created if not provided)
            on_step: Callback invoked after each step completes
            on_tool_call: Callback invoked after each tool execution
            stop_event: Event to signal forced stop
        """
        self.config = config
        self.llm = llm
        self.tools = tools

        # Create output storage if enabled in config
        output_storage = None
        if getattr(config, 'save_truncated_outputs', True):
            session_id = context.session_id if context else None
            output_storage = TruncatedOutputStorage(
                output_dir=getattr(config, 'truncated_output_dir', None),
                session_id=session_id or "",
                ttl_hours=getattr(config, 'truncated_output_ttl_hours', 24),
                enabled=True,
            )

        # Create context store with output storage
        if context is None:
            self.context = ContextStore(output_storage=output_storage)
        else:
            self.context = context
            # Set output storage if not already set
            if not hasattr(self.context, '_output_storage') or self.context._output_storage is None:
                self.context._output_storage = output_storage

        self.prompts = prompts or PromptBuilder()
        
        # Logging callbacks
        self._on_step = on_step
        self._on_tool_call = on_tool_call
        self._viz_collector = visualization_collector
        self._prompt_manager = prompt_manager
        self.stop_event = stop_event
        self.pause_event = pause_event
        
        self.summarizer = OutputSummarizer(llm, self.prompts, config)

        self.branch_coordinator = BranchCoordinator(
            self.context,
            agent_factory=self._create_subagent_executor(),
        )
        

        
        self._objective: str = ""
        self._step_count: int = 0
        self._findings: list[dict] = []
        self._hypotheses: list[dict] = []
        
        # NOTE: Pending summarization tracking is now in self.context (ContextStore)
        # to ensure tools can access the same state. See context.add_pending_summarization()
        
        # Step handler for tool execution (delegates callback to us for context)
        self.step_handler = StepHandler(
            tools=tools,
            on_tool_call=self._handle_tool_call_complete,
            on_tool_call_start=self._handle_tool_call_start,
        )
    
    # Tools exempt from summarization requirement (meta tools and control tools)
    _SUMMARIZATION_EXEMPT_TOOLS: set[str] = {
        "summarize_previous_tool_output", "view_tool_output",
        "continue_analysis", "create_test_plan", "add_todo", "complete_todo",
        "branch_to_subtasks", "finish_subtask", "complete_recon",
        "complete_browser_task", "complete_subtask", "finalize_analysis",
        "dispatch_subagents", "read_findings", "browser_click",
    }
    
    def _requires_summarization(self, tool_call: ToolCall) -> bool:
        """
        Determine if a tool call output requires summarization.
        
        Non-meta tool outputs exceeding 100 tokens require summarization
        before the agent can access other tools.
        
        Args:
            tool_call: The completed tool call to check
            
        Returns:
            True if the output requires summarization
        """
        # Meta tools are exempt
        if tool_call.tool_name in self._SUMMARIZATION_EXEMPT_TOOLS:
            return False
        
        # Failed tool calls don't need summarization
        if not tool_call.success:
            return False
        
        # Check token count
        tokens = count_tokens(tool_call.raw_output)
        return tokens > SUMMARIZATION_TOKEN_THRESHOLD

    def _get_available_tools(self) -> list[dict]:
        """
        Get tool schemas filtered by summarization state.

        Summarization requirement takes priority:
        - If pending summarizations exist, ONLY summarize_previous_tool_output is available
        - Otherwise, return all tools except summarization tool
        """
        all_schemas = self.tools.get_schemas()

        # CRITICAL: If there are pending summarizations, ONLY allow summarize_previous_tool_output
        if self.context.has_pending_summarization():
            return [
                s for s in all_schemas
                if s.get("function", {}).get("name") == "summarize_previous_tool_output"
            ]
        
        # No pending summarizations - hide summarize_previous_tool_output entirely
        # This prevents premature/placeholder calls to the summarization tool
        return [
            s for s in all_schemas
            if s.get("function", {}).get("name") != "summarize_previous_tool_output"
        ]

    
    def _create_subagent_executor(self):
        """Create the executor function for subagents."""
        async def executor(context: ContextStore, objective: str) -> SubtaskResult:
            # Create a sub-agent with filtered tools
            sub_agent = Agent(
                config=self.config,
                llm=self.llm,
                tools=self.tools,  # Note: tools will be filtered in prompt
                context=context,
                prompts=self.prompts,
                visualization_collector=self._viz_collector,
            )
            
            # Run the subtask
            result = await sub_agent.run(
                objective=objective,
                max_steps=self.config.max_steps // 2 if self.config.max_steps else 10,
            )
            
            return SubtaskResult(
                subtask_id=context.current_frame.id,
                objective=objective,
                summary=result.findings[0].get("description", str(result.findings)) if result.findings else "No findings",
                findings=result.findings,
                success=result.success,
                error=result.error,
            )
        
        return executor
    
    async def run(
        self,
        objective: str,
        max_steps: int | None = None,
        start_step: int = 0,
    ) -> AgentResult:
        """
        Run the agent on an objective.
        
        Args:
            objective: What the agent should accomplish
            max_steps: Override max steps from config
            start_step: Starting step number (for resumed sessions)
            
        Returns:
            AgentResult with findings, final state, etc.
        """

        self._objective = objective
        self._step_count = start_step
        
        # Notify visualization that agent is starting
        if self._viz_collector:
            self._viz_collector.on_agent_start(objective, self.config.model)
        
        # If we are effectively starting from scratch (step_count == 0), add initial prompts
        # If resuming (step_count > 0), assume context is already primed
        is_resuming = start_step > 0

        
        if not is_resuming:
            # Add initial system message
            system_prompt = self.prompts.build_full_prompt(
                tool_schemas=self.tools.get_schemas(),
                scope_description=self.config.scope or "No specific scope defined.",
            )
            self.context.add_message(MessageRole.SYSTEM, system_prompt)
            
            # Add user objective (includes full task context, e.g. manifest info)
            self.context.add_message(MessageRole.USER, objective)
        
        max_steps = max_steps or self.config.max_steps or 50

        
        try:
            while self._step_count < max_steps:
                # Check for forced stop
                if self.stop_event and self.stop_event.is_set():
                    self.context.add_message(MessageRole.SYSTEM, "[System] Agent execution stopped by user request.")
                    return AgentResult(
                        success=False,
                        objective=objective,
                        steps_taken=self._step_count,
                        findings=self._findings,
                        hypotheses=self._hypotheses,
                        context_id=self.context.current_frame.id,
                        paused=False,
                        error="Stopped by user",
                    )
                
                # Check for pause request
                if self.pause_event and self.pause_event.is_set():
                    self.context.add_message(
                        MessageRole.SYSTEM,
                        "[System] Agent paused by user request. Resume from CLI when ready."
                    )
                    if self._viz_collector:
                        self._viz_collector.on_agent_paused(
                            reason="Agent paused. Resume from CLI when ready."
                        )
                    return AgentResult(
                        success=True,
                        objective=objective,
                        steps_taken=self._step_count,
                        findings=self._findings,
                        hypotheses=self._hypotheses,
                        context_id=self.context.current_frame.id,
                        paused=True,
                    )


                try:
                    step_result = await self.step()

                except Exception as e:

                    import traceback
                    traceback.print_exc()
                    raise
                
                # Checkpoint after step if enabled
                if self.config.auto_checkpoint:
                    self.checkpoint(
                        label=f"Step {self._step_count}"
                    )
                
                # Check for user prompts between steps
                await self._check_for_user_prompts()
                
                if not step_result.should_continue:
                    # If agent is finishing and prompt manager exists, offer pause opportunity
                    if self._prompt_manager:
                        paused = await self._handle_reflect_pause()
                        if paused:
                            # User sent a prompt during pause, continue execution
                            step_result.should_continue = True
                            continue
                    break
                
                if step_result.error:
                    return AgentResult(
                        success=False,
                        objective=objective,
                        steps_taken=self._step_count,
                        findings=self._findings,
                        hypotheses=self._hypotheses,
                        context_id=self.context.current_frame.id,
                        error=step_result.error,
                    )
            
            return AgentResult(
                success=True,
                objective=objective,
                steps_taken=self._step_count,
                findings=self._findings,
                hypotheses=self._hypotheses,
                context_id=self.context.current_frame.id,
            )
            
        except Exception as e:
            return AgentResult(
                success=False,
                objective=objective,
                steps_taken=self._step_count,
                findings=self._findings,
                hypotheses=self._hypotheses,
                context_id=self.context.current_frame.id,
                error=str(e),
            )
    
    async def step(self) -> StepResult:
        """
        Execute a single agent step.
        
        1. Build prompt from current context
        2. Call LLM
        3. If tool call: execute tool, update context
        4. Handle special tools (branching, finish)
        5. Return step result
        """
        self._step_count += 1

        # Check context size and optimize if needed
        if self.config.max_context_tokens and getattr(self.config, 'auto_summarize', True):
            await self.context.optimize(
                llm_client=self.llm,
                threshold=self.config.max_context_tokens,
                recent_protection_tokens=20000, # Per user request
            )
            
        # Get messages for LLM (with output truncation)
        messages = self.context.render_messages(
            max_output_chars=self.config.max_output_chars
        )
        
        # Get available tool schemas (respects summarization state)
        tool_schemas = self._get_available_tools()
        
        # Emit available tools to visualization
        if self._viz_collector:
            self._viz_collector.on_available_tools(tool_schemas)
        
        # Call LLM

        try:
            response = await self.llm.complete(
                messages=messages,
                tools=tool_schemas,
            )

        except Exception as e:

            import traceback
            traceback.print_exc()
            raise
        
        # Add assistant response to context
        if response.content:
            self.context.add_message(MessageRole.ASSISTANT, response.content)
        
        step_result = StepResult(
            step_number=self._step_count,
            llm_response=response,
        )
        
        # Process tool calls
        if response.tool_calls:
            for tc in response.tool_calls:
                # Execute via StepHandler
                tool_call = await self.step_handler.execute_tool_call(
                    tc,
                    max_output_chars=self.config.max_output_chars,
                )
                step_result.tool_calls.append(tool_call)
                
                # Add to context
                self.context.add_tool_call(tool_call)
                
                # Apply tool call delay if configured (for browser agents / rate limiting)
                if self.config.browser_tool_call_delay > 0:
                    import asyncio
                    await asyncio.sleep(self.config.browser_tool_call_delay)
                
                # Track tool calls that require summarization (>threshold tokens, non-meta)
                if self._requires_summarization(tool_call):
                    self.context.add_pending_summarization(tool_call.id)
                
                # Handle successful summarization - remove from pending
                if (
                    tool_call.tool_name == "summarize_previous_tool_output"
                    and tool_call.success
                ):
                    # Get the summarized ID from metadata (set by the tool)
                    summarized_id = tool_call.metadata.get("summarized_tool_id") if tool_call.metadata else None
                    if summarized_id:
                        self.context.remove_pending_summarization(summarized_id)

                # If summarization failed, inject error hint
                if (
                    tool_call.tool_name == "summarize_previous_tool_output"
                    and not tool_call.success
                ):
                    self.context.add_message(
                        MessageRole.SYSTEM,
                        f"[System] Summarization failed: {tool_call.error or 'Unknown error'}. "
                        "Please try calling summarize_previous_tool_output again."
                    )

                
                # Emit test plan updates for checklist tools
                if tool_call.tool_name in ("create_test_plan", "add_todo", "complete_todo"):
                    if self._viz_collector and tool_call.success:
                        self._viz_collector.on_test_plan_update(
                            self.context.get_test_plan()
                        )
                
                # Process special tools
                special_result = self.step_handler.process_special_tool(tool_call)
                if special_result:
                    step_result = self._apply_special_tool_result(
                        step_result, tool_call, special_result
                    )
        
        # After processing all tool calls, inject ONE system message if NEW pending summarizations were added
        # First, remove any old summarization prompts to avoid clutter
        self.context.remove_summarization_prompts()
        
        # Validate pending summarizations - remove stale IDs that reference non-existent tool calls
        self._validate_pending_summarizations()
        
        # Only add new prompt if there are still pending summarizations
        if self.context.has_pending_summarization():
            pending_ids = list(self.context.get_pending_summarization_ids())
            self.context.add_message(
                MessageRole.SYSTEM,
                f"{SUMMARIZATION_PROMPT_MARKER} {len(pending_ids)} tool output(s) exceed {SUMMARIZATION_TOKEN_THRESHOLD} tokens and require summarization. "
                f"Call summarize_previous_tool_output to continue."
            )

        # Invoke step callback if provided
        if self._on_step:
            self._on_step(step_result)

        # Notify visualization
        if self._viz_collector:
            self._viz_collector.on_step(step_result, self.context.current_frame.id)
        
        return step_result
    
    def _apply_special_tool_result(
        self,
        step_result: StepResult,
        tool_call: ToolCall,
        special: SpecialToolResult,
    ) -> StepResult:
        """
        Apply the effects of a special tool result to the step.
        
        Args:
            step_result: Current step result to update
            tool_call: The tool call that was executed
            special: The processed special tool result
            
        Returns:
            Updated step result
        """
        if special.tool_name == "continue_analysis":
            if special.should_continue:
                # Agent wants to continue - just keep going
                self.context.add_message(
                    MessageRole.SYSTEM,
                    f"[Continuing analysis] {tool_call.raw_output}"
                )
            else:
                # Agent is done
                step_result.should_continue = False
                if special.findings:
                    self._findings.append({
                        **special.findings,
                        "step": self._step_count,
                    })
        
        elif special.tool_name == "branch_to_subtasks":
            if special.branch_id:
                # Handle branching - wait for subagents (async)
                # Note: This schedules the branch but actual waiting happens in step()
                pass  # Branch handling is asynchronous
        
        elif special.tool_name == "create_test_plan":
            # Test plan created - just acknowledge, no phase transition needed
            if tool_call.success:
                self.context.add_message(
                    MessageRole.SYSTEM,
                    "[System] Test plan created. Work through your test plan items by priority."
                )
        
        elif special.tool_name == "complete_recon":
            # Recon is complete - stop the agent
            step_result.should_continue = False
            if special.findings:
                self._findings.append({
                    **special.findings,
                    "step": self._step_count,
                })
        
        elif special.tool_name == "complete_browser_task":
            # Browser task complete - stop the browser agent
            step_result.should_continue = False
            if special.findings:
                self._findings.append({
                    **special.findings,
                    "step": self._step_count,
                })

        elif special.tool_name == "complete_subtask":
            # Subtask complete - stop the subagent
            step_result.should_continue = False
            if special.findings:
                self._findings.append({
                    **special.findings,
                    "step": self._step_count,
                })

        elif special.tool_name == "finalize_analysis":
            # Analysis finalized - stop the orchestrator
            step_result.should_continue = False
            if special.findings:
                self._findings.append({
                    **special.findings,
                    "step": self._step_count,
                })

        return step_result
    
    def _handle_tool_call_complete(self, tool_call: ToolCall) -> None:
        """
        Callback invoked when a tool call completes.
        
        Handles external callbacks and visualization notifications.
        
        Args:
            tool_call: The completed tool call
        """
        # Invoke external tool call callback if provided
        if self._on_tool_call:
            self._on_tool_call(tool_call)
        
        # Notify visualization
        if self._viz_collector:
            self._viz_collector.on_tool_call(tool_call, self.context.current_frame.id)
    
    def _handle_tool_call_start(self, tool_call: ToolCall) -> None:
        """
        Callback invoked when a tool call starts (before execution completes).
        
        Used for long-running tools like dispatch_subagent to show the tool
        card in the UI immediately.
        
        Args:
            tool_call: The starting tool call (not yet executed)
        """
        # Notify visualization of tool start
        if self._viz_collector:
            self._viz_collector.on_tool_call_start(tool_call, self.context.current_frame.id)
    
    def _validate_pending_summarizations(self) -> None:
        """
        Validate that all pending summarization IDs still exist in context.
        
        Removes any stale IDs that reference tool calls no longer in the context tree.
        This can happen if context was optimized/summarized between tracking and summarization.
        """
        pending_ids = self.context.get_pending_summarization_ids()
        if pending_ids:
            logging.debug(f"Validating pending summarizations: {pending_ids}")
        
        stale_ids = set()
        for pending_id in pending_ids:
            tool_call = self.context.find_tool_call(pending_id)
            if not tool_call:
                logging.warning(
                    f"Removing stale pending summarization: {pending_id} "
                    f"(tool call not found in context tree)"
                )
                stale_ids.add(pending_id)
            else:
                logging.debug(
                    f"Pending summarization {pending_id} is valid "
                    f"(tool: {tool_call.tool_name})"
                )
        
        for stale_id in stale_ids:
            self.context.remove_pending_summarization(stale_id)

    
    def checkpoint(self, label: str = "") -> str:
        """Create a checkpoint, return frame ID."""
        return self.context.checkpoint(label)
    
    def revert(self, frame_id: str) -> None:
        """Revert to a checkpoint."""
        self.context.revert(frame_id)
    
    async def _check_for_user_prompts(self) -> None:
        """
        Check for and inject any pending user prompts into context.
        
        Called between agent steps to allow user intervention.
        """
        if not self._prompt_manager:
            return
        
        prompt = await self._prompt_manager.get_pending_prompt()
        if prompt:
            # Inject as USER message with clear marker
            self.context.add_message(
                MessageRole.USER,
                f"[User Intervention] {prompt.content}"
            )
            
            # Notify visualization
            if self._viz_collector:
                self._viz_collector.on_user_prompt_received(prompt.content)
    
    async def _handle_reflect_pause(self, timeout: float = 60.0) -> bool:
        """
        Handle pause opportunity when agent is about to finish.
        
        When the agent decides to stop (continue_analysis with continue=false),
        this method pauses execution and waits for user input. If the user
        sends a prompt within the timeout, execution continues.
        
        Args:
            timeout: Seconds to wait for user input before finishing
            
        Returns:
            True if user sent a prompt and execution should continue,
            False if timed out and agent should finish
        """
        if not self._prompt_manager:
            return False
        
        # Notify UI that agent is pausing
        if self._viz_collector:
            self._viz_collector.on_agent_paused(
                reason="Agent finished analysis. Send a prompt to continue or wait to finalize."
            )
        
        # Add system message so agent knows it's paused
        self.context.add_message(
            MessageRole.SYSTEM,
            f"[System] Agent paused. Waiting up to {timeout}s for user input. "
            "If you receive a user message, incorporate it and continue analysis."
        )
        
        # Pause and wait for user input
        self._prompt_manager.pause(reason="Awaiting user decision")
        resumed = await self._prompt_manager.wait_for_resume(timeout=timeout)
        
        if resumed and self._prompt_manager.has_pending:
            # User sent a prompt, inject it and continue
            await self._check_for_user_prompts()
            
            # Notify UI that agent is resuming
            if self._viz_collector:
                self._viz_collector.on_agent_resumed()
            
            self.context.add_message(
                MessageRole.SYSTEM,
                "[System] Resuming analysis based on user input."
            )
            
            return True
        
        # Timed out, agent will finish
        self._prompt_manager.resume()  # Clear pause state
        return False
