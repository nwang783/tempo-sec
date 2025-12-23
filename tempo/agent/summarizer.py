"""
Output summarizer for context token management.
"""

from tempo.agent.config import AgentConfig
from tempo.context.frame import ToolCall
from tempo.infra.llm import LLMClient
from tempo.prompts.builder import PromptBuilder
from tempo.tools.base import Tool


class OutputSummarizer:
    """
    Handles summarization of tool outputs to save context tokens.
    
    Can use either:
    1. Tool's default_summarizer method
    2. LLM-based summarization for complex outputs
    """
    
    def __init__(
        self,
        llm: LLMClient,
        prompts: PromptBuilder,
        config: AgentConfig,
    ):
        """
        Initialize the output summarizer.
        
        Args:
            llm: LLM client for summarization
            prompts: Prompt builder for summarization prompts
            config: Agent configuration
        """
        self.llm = llm
        self.prompts = prompts
        self.config = config
    
    async def summarize(
        self,
        tool_call: ToolCall,
        objective: str,
        tool: Tool | None = None,
    ) -> str:
        """
        Summarize a tool call's output.
        
        Strategy:
        1. If tool has a default_summarizer and output is short, use it
        2. Otherwise, use LLM summarization
        
        Args:
            tool_call: The tool call to summarize
            objective: Current agent objective (for relevance filtering)
            tool: Optional tool instance for custom summarization
            
        Returns:
            Summarized output
        """
        output = tool_call.raw_output
        
        # If output is very short, no need to summarize
        if len(output) < 200:
            return output
        
        # Try tool's default summarizer first
        if tool is not None:
            from tempo.tools.base import ToolResult
            
            # Create a ToolResult to pass to summarizer
            result = ToolResult(
                success=True,
                output=output,
            )
            
            summary = tool.default_summarizer(result)
            
            # If the tool's summarizer made it short enough, use it
            if len(summary) < len(output) * 0.5:  # At least 50% reduction
                return summary
        
        # Use LLM summarization for complex outputs
        return await self._llm_summarize(tool_call, objective)
    
    async def _llm_summarize(
        self,
        tool_call: ToolCall,
        objective: str,
    ) -> str:
        """
        Use LLM to generate summary.
        
        Args:
            tool_call: The tool call to summarize
            objective: Current agent objective
            
        Returns:
            LLM-generated summary
        """
        prompt = self.prompts.build_summarization_prompt(
            tool_name=tool_call.tool_name,
            tool_input=tool_call.input,
            tool_output=tool_call.raw_output,
            objective=objective,
        )
        
        response = await self.llm.complete(
            messages=[{"role": "user", "content": prompt}],
        )
        
        return response.content
    
    def should_summarize(self, tool_call: ToolCall, threshold: int = 500) -> bool:
        """
        Determine if a tool call output should be summarized.
        
        Note: The agent is now responsible for initiating summarization
        via the `summarize_tool_output` tool. This method can be used
        for auto-summarization hints.
        
        Args:
            tool_call: The tool call to check
            threshold: Character threshold (default: 500)
            
        Returns:
            True if output exceeds threshold
        """
        return len(tool_call.raw_output) > threshold
    
    def estimate_token_savings(self, original: str, summary: str) -> int:
        """
        Estimate token savings from summarization.
        
        Uses rough estimate of 4 chars per token.
        
        Args:
            original: Original output
            summary: Summarized output
            
        Returns:
            Estimated tokens saved
        """
        original_tokens = len(original) // 4
        summary_tokens = len(summary) // 4
        return max(0, original_tokens - summary_tokens)


from pydantic import BaseModel, Field

class PhaseSummary(BaseModel):
    """Structured summary of a phase."""
    phase_name: str = Field(..., description="Name of the phase (RECON, HYPOTHESIZE, etc)")
    actions: list[str] = Field(..., description="List of key actions taken")
    key_findings: list[str] = Field(..., description="Important discoveries or results")
    narrative_summary: str = Field(..., description="Concise narrative of progress and outcomes")

class PhaseSummarizer:
    """
    Summarizes entire workflow phases to save context.
    Using gemini/gemini-3-flash-preview for efficiency.
    """
    
    def __init__(self, llm: LLMClient):
        self.llm = llm
        
    async def summarize_phase(
        self, 
        phase_name: str,
        messages: list[dict[str, str]]
    ) -> PhaseSummary:
        """
        Summarize a block of messages representing a phase.
        
        Args:
            phase_name: Name of the phase
            messages: List of message dicts (role, content)
            
        Returns:
            Structured PhaseSummary
        """
        # Create a text representation of the history
        history_text = "\n".join([
            f"{m['role'].upper()}: {m['content'][:2000]}..." if len(m['content']) > 2000 else f"{m['role'].upper()}: {m['content']}"
            for m in messages
        ])
        
        prompt = [
            {
                "role": "system", 
                "content": (
                    f"You are summarizing the {phase_name} phase of a security testing agent. "
                    "Analyze the conversation history and extract key actions, findings, and a narrative summary. "
                    "Focus on what was discovered and what was accomplished."
                )
            },
            {
                "role": "user",
                "content": f"Conversation History:\n{history_text}"
            }
        ]
        
        # Instantiate a specific client for Gemini Flash 3
        from tempo.infra.llm import LiteLLMClient
        # Note: In a real app we might want to inject this or use a factory
        flash_client = LiteLLMClient(model="gemini/gemini-3-flash-preview")
        
        return await flash_client.complete_structured(
            messages=prompt,
            response_model=PhaseSummary
        )
