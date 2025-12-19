"""
Phase summarizer for generating transition summaries between workflow phases.

Uses a fast, inexpensive model to summarize key steps, findings, and context
from the previous phase(s) when transitioning to a new phase.
"""

from typing import TYPE_CHECKING

from tempo.agent.config import AgentConfig
from tempo.context.frame import MessageRole
from tempo.infra.llm import LiteLLMClient
from tempo.prompts.phases import Phase

if TYPE_CHECKING:
    from tempo.context.store import ContextStore
    from tempo.prompts.builder import PromptBuilder


class PhaseSummarizer:
    """
    Generates summaries of phase work when transitioning between phases.
    
    Uses a fast, inexpensive model (gemini-3-flash-preview by default) to
    summarize the key steps, findings, and context from the previous phase(s).
    The summary is tailored to be useful for the next phase.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        prompts: "PromptBuilder",
        context: "ContextStore",
    ):
        """
        Initialize the phase summarizer.
        
        Args:
            config: Agent configuration
            prompts: Prompt builder for creating summarization prompts
            context: Context store for accessing phase history
        """
        self.config = config
        self.prompts = prompts
        self.context = context
        
        # Create dedicated LLM client for summarization
        self._summary_llm = LiteLLMClient(config.phase_summarization_model)
    
    async def summarize_phase_transition(
        self,
        from_phase: Phase,
        to_phase: Phase,
        objective: str,
    ) -> str:
        """
        Generate a summary for a phase transition.
        
        Args:
            from_phase: The phase we're transitioning from
            to_phase: The phase we're transitioning to
            objective: The agent's current objective
            
        Returns:
            A concise summary of the previous phase work, tailored for the next phase
        """
        # Get relevant context from the current frame
        phase_context = self._extract_phase_context(from_phase)
        
        # Build the summarization prompt (includes phase prompts for context)
        prompt = self.prompts.build_phase_transition_prompt(
            from_phase=from_phase,
            to_phase=to_phase,
            objective=objective,
            phase_context=phase_context,
        )
        
        # Call the fast summarization model
        response = await self._summary_llm.complete(
            messages=[{"role": "user", "content": prompt}],
        )
        
        return response.content or ""
    
    def _extract_phase_context(self, phase: Phase) -> dict:
        """
        Extract relevant context from the current phase.
        
        Gathers tool calls, messages, and state from the current frame
        to provide material for the summarizer.
        
        Args:
            phase: The phase to extract context from
            
        Returns:
            Dictionary with phase context including tool calls, messages, and state
        """
        frame = self.context.current_frame
        
        # Collect tool calls made in this phase (truncate long outputs)
        tool_calls = []
        for tc in frame.tool_calls:
            output = tc.output_for_context
            # Truncate very long outputs for the summarizer
            if len(output) > 1000:
                output = output[:500] + "\n... [truncated] ...\n" + output[-500:]
            
            tool_calls.append({
                "tool": tc.tool_name,
                "input": tc.input,
                "output": output,
                "success": tc.success,
            })
        
        # Collect assistant messages (reasoning/decisions)
        assistant_messages = [
            m.content for m in frame.messages 
            if m.role == MessageRole.ASSISTANT
        ]
        
        # Collect system messages (excluding the initial system prompt)
        system_messages = [
            m.content for m in frame.messages[1:]  # Skip initial system prompt
            if m.role == MessageRole.SYSTEM
        ]
        
        return {
            "phase": phase.value,
            "tool_calls": tool_calls,
            "assistant_reasoning": assistant_messages,
            "system_notes": system_messages,
            "state": {
                "hypotheses": frame.state.hypotheses,
                "findings": frame.state.findings,
                "notes": frame.state.notes,
            },
        }
