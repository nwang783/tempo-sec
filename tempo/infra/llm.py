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
    """Token usage statistics with caching and cost info."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    # Prompt caching fields (supported by Anthropic, OpenAI, DeepSeek, Bedrock)
    cached_tokens: int = 0          # Cache hit tokens (prompt_tokens_details.cached_tokens)
    cache_creation_tokens: int = 0  # Anthropic only: tokens written to cache
    # Cost tracking
    cost: float = 0.0               # USD cost for this call


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
    
    def __init__(
        self,
        model: str,
        *,
        litellm_module: Any | None = None,
        instructor_client: Any | None = None,
        **default_kwargs,
    ):
        """
        Initialize the LiteLLM client.
        
        Args:
            model: Model identifier (e.g., "anthropic/claude-sonnet-4-20250514", "openai/gpt-4o", "gemini/gemini-2.0-flash")
            litellm_module: Optional injected litellm module (useful for testing)
            instructor_client: Optional injected Instructor client (useful for testing)
            **default_kwargs: Default arguments for all completions
        """
        self.model = model
        self.default_kwargs = default_kwargs
        
        # Intentionally do not import litellm/instructor at __init__ time.
        # This keeps unit tests (and offline environments) from crashing on import.
        self._litellm = litellm_module
        self._instructor_client = instructor_client

    def _ensure_clients(self) -> None:
        """Lazy-initialize litellm + instructor bindings when first needed."""
        if self._litellm is not None and self._instructor_client is not None:
            return

        # Import only when needed to avoid import-time side effects in tests.
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
            self._ensure_clients()
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
        self._ensure_clients()
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
        
        # Extract caching info from usage
        usage = response.usage
        cached_tokens = 0
        cache_creation_tokens = 0
        
        # prompt_tokens_details contains cached_tokens for OpenAI/Anthropic/DeepSeek
        if hasattr(usage, 'prompt_tokens_details') and usage.prompt_tokens_details:
            details = usage.prompt_tokens_details
            if hasattr(details, 'cached_tokens'):
                cached_tokens = details.cached_tokens or 0
        
        # Anthropic-specific: cache_creation_input_tokens
        if hasattr(usage, 'cache_creation_input_tokens'):
            cache_creation_tokens = usage.cache_creation_input_tokens or 0
        
        # Calculate cost using LiteLLM's built-in function
        cost = 0.0
        try:
            cost = self._litellm.completion_cost(completion_response=response)
        except Exception:
            # Cost calculation may fail for some models, ignore
            pass
        
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                cached_tokens=cached_tokens,
                cache_creation_tokens=cache_creation_tokens,
                cost=cost,
            ),
            model=response.model,
            finish_reason=choice.finish_reason,
            raw_response=response,
        )

