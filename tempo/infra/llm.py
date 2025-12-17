"""
LLM client abstraction and implementation.

Provides a model-agnostic interface over LiteLLM with Instructor
for structured outputs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class TokenUsage:
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ToolCallRequest:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""
    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    finish_reason: str = ""
    raw_response: Any = None  # Original provider response for debugging


class LLMClient(ABC):
    """Model-agnostic LLM interface."""
    
    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """
        Send a completion request.
        
        Args:
            messages: List of {"role": str, "content": str} dicts
            tools: Optional list of tool schemas in OpenAI format
            
        Returns:
            Normalized LLMResponse
        """
        pass
    
    @abstractmethod
    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
    ) -> T:
        """
        Request a structured response matching a Pydantic model.
        
        Args:
            messages: List of {"role": str, "content": str} dicts
            response_model: Pydantic model class for the response
            
        Returns:
            Instance of response_model
        """
        pass


class LLMError(Exception):
    """Wrapper for LLM-related errors."""
    pass


class LiteLLMClient(LLMClient):
    """LiteLLM + Instructor implementation of LLMClient."""
    
    def __init__(self, model: str, **default_kwargs):
        """
        Initialize the LiteLLM client.
        
        Args:
            model: Model identifier (e.g., "anthropic/claude-sonnet-4-20250514", "openai/gpt-4o", "gemini/gemini-2.0-flash")
            **default_kwargs: Default arguments for all completions
        """
        self.model = model
        self.default_kwargs = default_kwargs
        
        # Lazy import to avoid import errors if litellm not installed
        import instructor
        import litellm
        self._litellm = litellm
        self._instructor_client = instructor.from_litellm(litellm.acompletion)
    
    async def complete(
        self,
        messages: list[dict[str, str]],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """Send a completion request."""
        import json
        
        try:
            kwargs = {**self.default_kwargs}
            if tools:
                kwargs["tools"] = tools
                
            response = await self._litellm.acompletion(
                model=self.model,
                messages=messages,
                **kwargs,
            )
            return self._normalize_response(response)
        except Exception as e:
            raise LLMError(f"Completion failed: {e}") from e
    
    async def complete_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
    ) -> T:
        """Request a structured response."""
        return await self._instructor_client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_model=response_model,
        )
    
    def _normalize_response(self, response) -> LLMResponse:
        """Convert LiteLLM response to our normalized format."""
        import json
        
        choice = response.choices[0]
        message = choice.message
        
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            usage=TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            ),
            model=response.model,
            finish_reason=choice.finish_reason,
            raw_response=response,
        )
