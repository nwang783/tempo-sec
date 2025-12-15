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
