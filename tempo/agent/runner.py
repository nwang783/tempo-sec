"""
Agent runner - main loop and step execution.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from tempo.agent.config import AgentConfig
from tempo.agent.workflow import WorkflowManager, WorkflowError
from tempo.agent.summarizer import OutputSummarizer
from tempo.agent.phase_summarizer import PhaseSummarizer
from tempo.agent.branch_coordinator import BranchCoordinator, SubtaskResult
from tempo.agent.step_handler import StepHandler, SpecialToolResult
from tempo.context.store import ContextStore
from tempo.context.frame import MessageRole, ToolCall
from tempo.infra.llm import LLMClient, LLMResponse
from tempo.prompts.builder import PromptBuilder
from tempo.prompts.phases import Phase
from tempo.tools.registry import ToolRegistry
from tempo.tools.base import ToolResult

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
        
        # Use provided workflow manager or create one (share with TransitionPhaseTool!)
        self.workflow = workflow or WorkflowManager(config)
        self.summarizer = OutputSummarizer(llm, self.prompts, config)
        self.phase_summarizer = PhaseSummarizer(config, self.prompts, self.context)
        self.branch_coordinator = BranchCoordinator(
            self.context,
            agent_factory=self._create_subagent_executor(),
        )
        
        # Register phase transition callback for summarization
        self._pending_transition: tuple[Phase, Phase] | None = None
        self._pending_cycle_replacement: bool = False
        self._cycle_start_message_index: int = 0  # Track where current cycle started
        self.workflow.on_transition(self._on_phase_transition)
        
        self._objective: str = ""
        self._step_count: int = 0
        self._findings: list[dict] = []
        self._hypotheses: list[dict] = []
        
        # Step handler for tool execution (delegates callback to us for context)
        self.step_handler = StepHandler(
            tools=tools,
            on_tool_call=self._handle_tool_call_complete,
        )
    def _get_phase_filtered_tools(self) -> list[dict]:
        """
        Get tool schemas filtered by current phase.
        
        In REFLECT phase: only continue_analysis is available
        In other phases: continue_analysis is hidden
        """
        from tempo.prompts.phases import Phase
        
        all_schemas = self.tools.get_schemas()
        
        if self.workflow.current_phase == Phase.REFLECT:
            # REFLECT: Only continue_analysis tool to force decision
            return [
                s for s in all_schemas 
                if s.get("function", {}).get("name") == "continue_analysis"
            ]
        else:
            # Other phases: Hide continue_analysis
            return [
                s for s in all_schemas 
                if s.get("function", {}).get("name") != "continue_analysis"
            ]
    
    def _on_phase_transition(self, from_phase: Phase, to_phase: Phase) -> None:
        """
        Handle phase transition - mark that we need to generate a summary.
        
        The summary will be generated asynchronously in the next step.
        If transitioning FROM reflect, also mark for context replacement.
        """
        self._pending_transition = (from_phase, to_phase)
        
        # If transitioning FROM reflect, this completes a cycle - mark for replacement
        if from_phase == Phase.REFLECT and self.config.replace_context_after_reflect:
            self._pending_cycle_replacement = True
    
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
    ) -> AgentResult:
        """
        Run the agent on an objective.
        
        Args:
            objective: What the agent should accomplish
            initial_phase: Starting phase (default: RECON)
            max_steps: Override max steps from config
            
        Returns:
            AgentResult with findings, final state, etc.
        """
        self._objective = objective
        self._step_count = 0
        self.workflow.reset(initial_phase)
        
        # Add initial system message
        system_prompt = self.prompts.build_full_prompt(
            objective=objective,
            current_phase=initial_phase,
            tool_schemas=self.tools.get_schemas(),
            scope_description=self.config.scope or "No specific scope defined.",
        )
        self.context.add_message(MessageRole.SYSTEM, system_prompt)
        
        # Add user objective
        self.context.add_message(MessageRole.USER, f"Objective: {objective}")
        
        max_steps = max_steps or self.config.max_steps or 50
        
        try:
            while self._step_count < max_steps:
                step_result = await self.step()
                
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
        
        # Generate phase summary if we have a pending transition
        if self._pending_transition and self.config.auto_phase_summary:
            from_phase, to_phase = self._pending_transition
            self._pending_transition = None
            
            try:
                summary = await self.phase_summarizer.summarize_phase_transition(
                    from_phase=from_phase,
                    to_phase=to_phase,
                    objective=self._objective,
                )
                
                # If this is a cycle replacement (from REFLECT), replace previous messages
                if self._pending_cycle_replacement:
                    self._pending_cycle_replacement = False
                    
                    # Get current message count before adding summary
                    current_msg_count = len(self.context.current_frame.messages)
                    
                    # Replace messages from cycle start to now with summary
                    # Keep at least the system prompt (index 0) and user objective (index 1)
                    start_idx = max(2, self._cycle_start_message_index)
                    if start_idx < current_msg_count:
                        self.context.replace_messages_with_summary(
                            start_index=start_idx,
                            end_index=current_msg_count,
                            summary=summary,
                        )
                    
                    # Mark new cycle start
                    self._cycle_start_message_index = len(self.context.current_frame.messages)
                else:
                    # Normal phase summary - just inject as message
                    self.context.add_message(
                        MessageRole.SYSTEM,
                        f"[Phase Summary: {from_phase.value} → {to_phase.value}]\n{summary}"
                    )
                
                # Notify visualization
                if self._viz_collector:
                    self._viz_collector.on_phase_summary(
                        from_phase=from_phase.value,
                        to_phase=to_phase.value,
                        summary=summary,
                    )
            except Exception as e:
                # Log but don't fail if summarization fails
                self.context.add_message(
                    MessageRole.SYSTEM,
                    f"[Phase transition: {from_phase.value} → {to_phase.value}] (summary unavailable: {e})"
                )
        
        # Check for forced transitions
        forced_phase = self.workflow.should_force_transition()
        if forced_phase:
            self.workflow.transition(forced_phase)
            self.context.add_message(
                MessageRole.SYSTEM,
                f"[System] Automatically transitioned to {forced_phase.value} due to step limit."
            )
        
        # Get messages for LLM (with output truncation)
        messages = self.context.render_messages(
            max_output_chars=self.config.max_output_chars
        )
        
        # Get phase-filtered tool schemas (REFLECT: only continue_analysis)
        tool_schemas = self._get_phase_filtered_tools()
        
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
                
                # Process special tools
                special_result = self.step_handler.process_special_tool(tool_call)
                if special_result:
                    step_result = self._apply_special_tool_result(
                        step_result, tool_call, special_result
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
                self.context.add_message(
                    MessageRole.SYSTEM,
                    f"[Continuing analysis] {tool_call.raw_output}\nYou are now back in the {special.phase_transition.value.upper()} phase."
                )
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
        
        elif special.tool_name == "branch_to_subtasks":
            if special.branch_id:
                # Handle branching - wait for subagents (async)
                # Note: This schedules the branch but actual waiting happens in step()
                pass  # Branch handling is asynchronous
        
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
