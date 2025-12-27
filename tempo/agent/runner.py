"""
Agent runner - main loop and step execution.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from tempo.agent.config import AgentConfig
from tempo.agent.workflow import WorkflowManager, WorkflowError
from tempo.agent.summarizer import OutputSummarizer

from tempo.agent.branch_coordinator import BranchCoordinator, SubtaskResult
from tempo.agent.step_handler import StepHandler, SpecialToolResult
from tempo.context.store import ContextStore
from tempo.context.frame import MessageRole, ToolCall
from tempo.infra.llm import LLMClient, LLMResponse
from tempo.infra.tokenizer import count_tokens
from tempo.prompts.builder import PromptBuilder
from tempo.prompts.phases import Phase
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
    phase_transition: Phase | None = None
    should_continue: bool = True
    error: str | None = None


@dataclass
class AgentResult:
    """Final result of an agent run."""
    success: bool
    objective: str
    steps_taken: int
    final_phase: Phase
    findings: list[dict] = field(default_factory=list)
    hypotheses: list[dict] = field(default_factory=list)
    context_id: str = ""  # For resumption
    error: str | None = None


class Agent:
    """
    Main agent class that orchestrates the security testing workflow.
    
    Manages the agent loop, tool execution, phase transitions,
    and context management.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        llm: LLMClient,
        tools: ToolRegistry,
        context: ContextStore | None = None,
        prompts: PromptBuilder | None = None,
        workflow: "WorkflowManager | None" = None,
        on_step: "Callable[[StepResult], None] | None" = None,
        on_tool_call: "Callable[[ToolCall], None] | None" = None,
        visualization_collector: "VisualizationCollector | None" = None,
        prompt_manager: "UserPromptManager | None" = None,
        stop_event: "asyncio.Event | None" = None,
    ):
        """
        Initialize the agent.
        
        Args:
            config: Agent configuration
            llm: LLM client for completions
            tools: Tool registry
            context: Context store (created if not provided)
            prompts: Prompt builder (created if not provided)
            workflow: Workflow manager (created if not provided, pass to share with tools)
            on_step: Callback invoked after each step completes
            on_tool_call: Callback invoked after each tool execution
            stop_event: Event to signal forced stop
        """
        self.config = config
        self.llm = llm
        self.tools = tools
        self.context = context or ContextStore()
        self.prompts = prompts or PromptBuilder()
        
        # Logging callbacks
        self._on_step = on_step
        self._on_tool_call = on_tool_call
        self._viz_collector = visualization_collector
        self._prompt_manager = prompt_manager
        self.stop_event = stop_event
        
        # Use provided workflow manager or create one (share with TransitionPhaseTool!)
        self.workflow = workflow or WorkflowManager(config)
        self.summarizer = OutputSummarizer(llm, self.prompts, config)

        self.branch_coordinator = BranchCoordinator(
            self.context,
            agent_factory=self._create_subagent_executor(),
        )
        

        
        self._objective: str = ""
        self._step_count: int = 0
        self._findings: list[dict] = []
        self._hypotheses: list[dict] = []
        
        # Pending summarization tracking - tool call IDs that require summarization
        # before other tools become available again
        self._pending_summarization: set[str] = set()
        
        # Step handler for tool execution (delegates callback to us for context)
        self.step_handler = StepHandler(
            tools=tools,
            on_tool_call=self._handle_tool_call_complete,
        )
    
    # Tools exempt from summarization requirement (meta tools and control tools)
    _SUMMARIZATION_EXEMPT_TOOLS: set[str] = {
        "summarize_tool_output", "view_tool_output", "transition_phase",
        "continue_analysis", "create_test_plan", "add_todo", "complete_todo",
        "branch_to_subtasks", "finish_subtask", "complete_recon",
        "complete_browser_task",
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

    def _get_phase_filtered_tools(self) -> list[dict]:
        """
        Get tool schemas filtered by current phase and summarization state.

        Summarization requirement takes priority:
        - If pending summarizations exist, ONLY summarize_tool_output is available

        Phase tool restrictions:
        - RECON: Standard tools, hide meta tools
        - HYPOTHESIZE:
            * If NO plan exists: Only create_test_plan (forces structured output)
            * If plan EXISTS: Only add_todo, complete_todo, transition_phase (manage existing plan)
        - TEST: All tools + add_todo/complete_todo, hide continue_analysis
        - REFLECT: Only continue_analysis + add_todo + complete_todo
        """
        from tempo.prompts.phases import Phase

        all_schemas = self.tools.get_schemas()

        # CRITICAL: If there are pending summarizations, ONLY allow summarize_tool_output
        if self._pending_summarization:
            return [
                s for s in all_schemas
                if s.get("function", {}).get("name") == "summarize_tool_output"
            ]

        phase = self.workflow.current_phase

        if phase == Phase.REFLECT:
            # REFLECT: continue_analysis, add_todo, complete_todo, and summarize_tool_output
            allowed = {"continue_analysis", "add_todo", "complete_todo", "summarize_tool_output"}
            return [
                s for s in all_schemas
                if s.get("function", {}).get("name") in allowed
            ]

        elif phase == Phase.HYPOTHESIZE:
            # Check if a test plan already exists
            has_plan = (
                self.context.current_frame.state.test_plan is not None
                and len(self.context.current_frame.state.test_plan) > 0
            )

            if has_plan:
                # Plan exists - allow todo management and phase transition
                allowed = {"add_todo", "complete_todo", "transition_phase", "summarize_tool_output"}
                return [
                    s for s in all_schemas
                    if s.get("function", {}).get("name") in allowed
                ]
            else:
                # No plan - force plan creation
                return [
                    s for s in all_schemas
                    if s.get("function", {}).get("name") == "create_test_plan"
                ]

        elif phase == Phase.TEST:
            # TEST: All tools except continue_analysis and create_test_plan
            hidden = {"continue_analysis", "create_test_plan"}
            return [
                s for s in all_schemas
                if s.get("function", {}).get("name") not in hidden
            ]

        else:
            # RECON: Hide checklist tools and continue_analysis
            hidden = {"continue_analysis", "create_test_plan", "add_todo", "complete_todo"}
            return [
                s for s in all_schemas
                if s.get("function", {}).get("name") not in hidden
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
        initial_phase: Phase = Phase.RECON,
        max_steps: int | None = None,
        start_step: int = 0,
    ) -> AgentResult:
        """
        Run the agent on an objective.
        
        Args:
            objective: What the agent should accomplish
            initial_phase: Starting phase (default: RECON)
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
        
        # Only reset workflow if starting fresh
        if start_step == 0:
            self.workflow.reset(initial_phase)
        
        # If we are effectively starting from scratch (step_count == 0), add initial prompts
        # If resuming (step_count > 0), assume context is already primed
        is_resuming = start_step > 0
        
        if not is_resuming:
            # Add initial system message
            system_prompt = self.prompts.build_full_prompt(
                current_phase=initial_phase,
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
                        final_phase=self.workflow.current_phase,
                        findings=self._findings,
                        hypotheses=self._hypotheses,
                        context_id=self.context.current_frame.id,
                        error="Stopped by user",
                    )

                step_result = await self.step()
                
                # Checkpoint after step if enabled
                if self.config.auto_checkpoint:
                    self.checkpoint(
                        label=f"Step {self._step_count}: {self.workflow.current_phase.value}"
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
                        final_phase=self.workflow.current_phase,
                        findings=self._findings,
                        hypotheses=self._hypotheses,
                        context_id=self.context.current_frame.id,
                        error=step_result.error,
                    )
            
            return AgentResult(
                success=True,
                objective=objective,
                steps_taken=self._step_count,
                final_phase=self.workflow.current_phase,
                findings=self._findings,
                hypotheses=self._hypotheses,
                context_id=self.context.current_frame.id,
            )
            
        except Exception as e:
            return AgentResult(
                success=False,
                objective=objective,
                steps_taken=self._step_count,
                final_phase=self.workflow.current_phase,
                findings=self._findings,
                hypotheses=self._hypotheses,
                context_id=self.context.current_frame.id,
                error=str(e),
            )
    
    async def step(self) -> StepResult:
        """
        Execute a single agent step.
        
        1. Build prompt from current context and phase
        2. Call LLM
        3. If tool call: execute tool, update context
        4. Handle special tools (phase transition, branching, finish)
        5. Return step result
        """
        self._step_count += 1
        self.workflow.record_step()
        

        # Check for forced transitions
        forced_phase = self.workflow.should_force_transition()
        if forced_phase:
            self.workflow.transition(forced_phase)
            self.context.add_message(
                MessageRole.SYSTEM,
                f"[System] Automatically transitioned to {forced_phase.value} due to step limit."
            )
        
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
        
        # Get phase-filtered tool schemas (REFLECT: only continue_analysis)
        tool_schemas = self._get_phase_filtered_tools()
        
        # Emit available tools to visualization
        if self._viz_collector:
            self._viz_collector.on_available_tools(tool_schemas)
        
        # Call LLM
        response = await self.llm.complete(
            messages=messages,
            tools=tool_schemas,
        )
        
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
                
                # Track tool calls that require summarization (>threshold tokens, non-meta)
                if self._requires_summarization(tool_call):
                    self._pending_summarization.add(tool_call.id)
                
                # Handle successful summarization - remove from pending
                if (
                    tool_call.tool_name == "summarize_tool_output"
                    and tool_call.success
                ):
                    summarized_id = tool_call.input.get("tool_call_id")
                    if summarized_id and summarized_id in self._pending_summarization:
                        self._pending_summarization.discard(summarized_id)

                # If summarization was mis-targeted, inject a short system hint listing
                # the currently truncated IDs so the model can recover in the next step.
                if (
                    tool_call.tool_name == "summarize_tool_output"
                    and not tool_call.success
                    and isinstance(tool_call.metadata, dict)
                    and tool_call.metadata.get("truncated_tool_call_ids")
                ):
                    truncated_ids = tool_call.metadata.get("truncated_tool_call_ids") or []
                    self.context.add_message(
                        MessageRole.SYSTEM,
                        "[System] summarize_tool_output was called with a non-truncated tool_call_id. "
                        f"Summarize one of these tool_call_id(s) instead: {truncated_ids}"
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
        
        # Only add new prompt if there are still pending summarizations
        if self._pending_summarization:
            pending_ids = list(self._pending_summarization)
            self.context.add_message(
                MessageRole.SYSTEM,
                f"{SUMMARIZATION_PROMPT_MARKER} {len(pending_ids)} tool output(s) exceed {SUMMARIZATION_TOKEN_THRESHOLD} tokens and require summarization. "
                f"Call summarize_tool_output for each of these tool_call_id(s): {pending_ids}"
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
        Apply the effects of a special tool result to the step and workflow.
        
        Args:
            step_result: Current step result to update
            tool_call: The tool call that was executed
            special: The processed special tool result
            
        Returns:
            Updated step result
        """
        if special.tool_name == "continue_analysis":
            if special.should_continue and special.phase_transition:
                # Agent wants to continue - transition to the specified phase
                self.workflow.transition(special.phase_transition)

                # Build phase-specific message
                phase_msg = f"[Continuing analysis] {tool_call.raw_output}\nYou are now back in the {special.phase_transition.value.upper()} phase."

                # For HYPOTHESIZE phase, inject phase-specific instructions based on plan existence
                if special.phase_transition == Phase.HYPOTHESIZE:
                    has_plan = (
                        self.context.current_frame.state.test_plan is not None
                        and len(self.context.current_frame.state.test_plan) > 0
                    )
                    phase_instructions = self.prompts.build_phase_prompt(
                        special.phase_transition,
                        has_test_plan=has_plan
                    )
                    phase_msg += f"\n\n{phase_instructions}"

                self.context.add_message(MessageRole.SYSTEM, phase_msg)
            elif not special.should_continue:
                # Agent is done
                step_result.should_continue = False
                if special.findings:
                    self._findings.append({
                        **special.findings,
                        "step": self._step_count,
                    })
        
        elif special.tool_name == "transition_phase":
            if special.phase_transition:
                step_result.phase_transition = special.phase_transition

                # Keep persisted context state in sync with workflow for resume/debugging.
                # Only do this when the tool actually succeeded; otherwise we'd lie in history.
                if tool_call.success:
                    self.context.update_state(current_phase=special.phase_transition.value)

                    # Build phase-specific message with appropriate guidance
                    phase_msg = f"[System] Transitioned to {special.phase_transition.value.upper()} phase."

                    # For HYPOTHESIZE phase, inject phase-specific instructions based on plan existence
                    if special.phase_transition == Phase.HYPOTHESIZE:
                        has_plan = (
                            self.context.current_frame.state.test_plan is not None
                            and len(self.context.current_frame.state.test_plan) > 0
                        )
                        phase_instructions = self.prompts.build_phase_prompt(
                            special.phase_transition,
                            has_test_plan=has_plan
                        )
                        phase_msg += f"\n\n{phase_instructions}"

                    self.context.add_message(MessageRole.SYSTEM, phase_msg)
        
        elif special.tool_name == "branch_to_subtasks":
            if special.branch_id:
                # Handle branching - wait for subagents (async)
                # Note: This schedules the branch but actual waiting happens in step()
                pass  # Branch handling is asynchronous
        
        elif special.tool_name == "create_test_plan":
            # Auto-transition to TEST phase
            if special.phase_transition:
                step_result.phase_transition = special.phase_transition
                self.workflow.transition(special.phase_transition)
                self.context.add_message(
                    MessageRole.SYSTEM,
                    f"[System] Test plan created. Transitioned to {special.phase_transition.value.upper()} phase. "
                    "Work through your test plan items by priority."
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
            
            # Transition back to RECON to continue work
            self.workflow.transition(Phase.RECON)
            self.context.add_message(
                MessageRole.SYSTEM,
                "[System] Resuming analysis based on user input. You are now in RECON phase."
            )
            
            return True
        
        # Timed out, agent will finish
        self._prompt_manager.resume()  # Clear pause state
        return False
