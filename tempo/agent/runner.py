"""
Agent runner - main loop and step execution.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from tempo.agent.config import AgentConfig
from tempo.agent.workflow import WorkflowManager, WorkflowError
from tempo.agent.summarizer import OutputSummarizer
from tempo.agent.phase_summarizer import PhaseSummarizer
from tempo.agent.branch_coordinator import BranchCoordinator, SubtaskResult
from tempo.context.store import ContextStore
from tempo.context.frame import MessageRole, ToolCall
from tempo.infra.llm import LLMClient, LLMResponse
from tempo.prompts.builder import PromptBuilder
from tempo.prompts.phases import Phase
from tempo.tools.registry import ToolRegistry
from tempo.tools.registry import ToolRegistry
from tempo.tools.base import ToolResult

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
        self.workflow.on_transition(self._on_phase_transition)
        
        self._objective: str = ""
        self._step_count: int = 0
        self._findings: list[dict] = []
        self._hypotheses: list[dict] = []
    
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
        """
        self._pending_transition = (from_phase, to_phase)
    
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
                
                if not step_result.should_continue:
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
                
                # Inject summary into context
                self.context.add_message(
                    MessageRole.SYSTEM,
                    f"[Phase Summary: {from_phase.value} → {to_phase.value}]\n{summary}"
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
                tool_result = await self._execute_tool_call(tc)
                step_result.tool_calls.append(tool_result)
                
                # Handle special tools
                if tc.name == "continue_analysis":
                    if tool_result.metadata.get("continue"):
                        # Agent wants to continue - transition back to RECON
                        self.workflow.transition(Phase.RECON)
                        self.context.add_message(
                            MessageRole.SYSTEM,
                            f"[Continuing analysis] {tool_result.raw_output}\nYou are now back in the RECON phase."
                        )
                    elif tool_result.metadata.get("finish"):
                        # Agent is done
                        step_result.should_continue = False
                        self._findings.append({
                            "description": tool_result.metadata.get("findings", ""),
                            "reasoning": tool_result.metadata.get("reasoning", ""),
                            "step": self._step_count,
                        })
                
                elif tc.name == "transition_phase":
                    phase_str = tc.arguments.get("phase", "")
                    try:
                        step_result.phase_transition = Phase(phase_str)
                    except ValueError:
                        pass
                
                elif tc.name == "branch_to_subtasks":
                    # Handle branching - wait for subagents
                    branch_id = tool_result.metadata.get("branch_id")
                    if branch_id:
                        results = await self.branch_coordinator.await_completion(branch_id)
                        merged = self.branch_coordinator.finalize_branch(branch_id)
                        self.context.add_message(
                            MessageRole.SYSTEM,
                            f"[Branching Complete]\n{merged}"
                        )
        
        # Invoke step callback if provided
        if self._on_step:
            self._on_step(step_result)

        # Notify visualization
        if self._viz_collector:
            self._viz_collector.on_step(step_result, self.context.current_frame.id)
        
        return step_result
    
    async def _execute_tool_call(self, tc: Any) -> ToolCall:
        """
        Execute a single tool call.
        
        Args:
            tc: Tool call from LLM response
            
        Returns:
            ToolCall with results
        """
        tool = self.tools.get(tc.name)
        
        tool_call = ToolCall(
            id=tc.id,
            tool_name=tc.name,
            input=tc.arguments,
        )
        
        if tool is None:
            tool_call.raw_output = f"Error: Tool '{tc.name}' not found"
            self.context.add_tool_call(tool_call)
            return tool_call
        
        try:
            # Execute the tool
            result = await tool.execute(**tc.arguments)
            
            tool_call.raw_output = result.output
            tool_call.metadata = result.metadata
            
            # Add reminder to summarize if output is long
            if len(result.output) > 500:
                tool_call.raw_output += (
                    f"\n\n[System: Output captured ({len(result.output)} chars). "
                    f"You MUST call `summarize_tool_output` with tool_call_id='{tool_call.id}' "
                    f"to compress this data and save context tokens before proceeding.]"
                )
            
        except Exception as e:
            tool_call.raw_output = f"Error executing tool: {str(e)}"
        
        self.context.add_tool_call(tool_call)
        
        # Invoke tool call callback if provided
        if self._on_tool_call:
            self._on_tool_call(tool_call)
        
        # Notify visualization
        if self._viz_collector:
            self._viz_collector.on_tool_call(tool_call, self.context.current_frame.id)

        
        return tool_call
    
    def checkpoint(self, label: str = "") -> str:
        """Create a checkpoint, return frame ID."""
        return self.context.checkpoint(label)
    
    def revert(self, frame_id: str) -> None:
        """Revert to a checkpoint."""
        self.context.revert(frame_id)
