"""
LLM configuration for browser-use integration.

Important:
- browser-use has its *own* LLM interface (`browser_use.llm.*`) that returns a
  `ChatInvokeCompletion` with a `.completion` field (structured output support).
- Do NOT pass LangChain chat models directly to browser-use's `Agent` — they
  won't satisfy the expected interface and the agent will "stall" with repeated
  step failures (e.g. `KeyError: 'items'` or similar parsing/formatting errors).
"""

import os
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from tempo.infra.llm_client import LiteLLMClient


def create_browser_use_llm(
    use_browser_use_llm: bool = False,
    litellm_client: "LiteLLMClient | None" = None,
    model: str | None = None,
):
    """
    Create an LLM instance for browser-use.

    Args:
        use_browser_use_llm: If True, use browser-use's ChatBrowserUse model.
                            If False, use OpenAI or OpenRouter.
        litellm_client: tempo-sec's LiteLLM client (not currently used)

    Returns:
        LLM instance compatible with browser-use

    Environment Variables:
        BROWSER_USE_API_KEY: For ChatBrowserUse (when use_browser_use_llm=True)
        OPENAI_API_KEY: For direct OpenAI usage (preferred)
        OPENROUTER_API_KEY: For OpenRouter usage (fallback)
    """
    # Allow overriding the browser-agent model via env var.
    # This intentionally defaults to a browser-use supported model family.
    model = model or os.getenv("TEMPO_BROWSER_MODEL") or "gpt-5-mini"

    if use_browser_use_llm:
        # Use browser-use's hosted/tuned model
        from browser_use.llm.browser_use.chat import ChatBrowserUse

        return ChatBrowserUse(model=model)

    # Prefer OpenAI direct if available; fallback to OpenRouter.
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if openai_key:
        from browser_use.llm.openai.chat import ChatOpenAI as BrowserUseChatOpenAI

        return BrowserUseChatOpenAI(
            model=model,
            api_key=openai_key,
            temperature=0.2,
        )

    if openrouter_key:
        from browser_use.llm.openrouter.chat import ChatOpenRouter

        # OpenRouter generally expects namespaced model IDs like "openai/gpt-5-mini".
        openrouter_model = model if "/" in model else f"openai/{model}"
        return ChatOpenRouter(
            model=openrouter_model,
            api_key=openrouter_key,
            temperature=0.2,
            default_headers={
                "HTTP-Referer": "https://github.com/your-repo/tempo-sec",
                "X-Title": "tempo-sec browser agent",
            },
        )

    raise ValueError(
        "No API key found. Set one of:\n"
        "  OPENAI_API_KEY (for direct OpenAI usage - recommended)\n"
        "  OPENROUTER_API_KEY (for OpenRouter usage)\n"
        "  OR set use_browser_use_llm=True and set BROWSER_USE_API_KEY"
    )


class LiteLLMAdapter:
    """
    Adapter to wrap LiteLLMClient for browser-use compatibility.

    This is an alternative approach that wraps tempo-sec's existing
    LiteLLMClient to work with browser-use. May be needed if direct
    OpenRouter integration doesn't work as expected.
    """

    def __init__(self, litellm_client: "LiteLLMClient"):
        """
        Initialize the adapter.

        Args:
            litellm_client: tempo-sec's LiteLLM client
        """
        self.client = litellm_client

    def invoke(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        """
        Invoke the LLM with messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional arguments for the LLM

        Returns:
            Response object compatible with langchain
        """
        # Convert langchain message format to LiteLLM format if needed
        litellm_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                litellm_messages.append(msg)
            elif hasattr(msg, "type") and hasattr(msg, "content"):
                # Convert langchain message objects to dict format
                role = msg.type if msg.type != "ai" else "assistant"
                litellm_messages.append({"role": role, "content": msg.content})
            else:
                # Fallback: assume it's already in the right format
                litellm_messages.append(msg)

        # Call LiteLLM client
        response = self.client.complete(
            messages=litellm_messages, temperature=kwargs.get("temperature", 0.7)
        )

        # Wrap response in langchain-compatible format
        class MockAIMessage:
            def __init__(self, content):
                self.content = content
                self.type = "ai"

        return MockAIMessage(response.content)

    async def ainvoke(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        """
        Async invoke the LLM with messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional arguments for the LLM

        Returns:
            Response object compatible with langchain
        """
        # For now, just call the sync version
        # Could be enhanced with proper async support
        return self.invoke(messages, **kwargs)

    @property
    def _llm_type(self) -> str:
        """Return LLM type identifier."""
        return "litellm"


def get_llm_config_info() -> str:
    """
    Get information about LLM configuration options.

    Returns:
        Formatted string with configuration options
    """
    return """
LLM Configuration for Browser-Use Integration:

Option 1: OpenAI Direct (Recommended)
  - Set environment variable: OPENAI_API_KEY
  - Uses gpt-5.1 model
  - Direct OpenAI API usage (no intermediary)

Option 2: OpenRouter
  - Set environment variable: OPENROUTER_API_KEY
  - Uses gpt-5.1 via OpenRouter
  - Useful if you prefer OpenRouter's routing

Option 3: ChatBrowserUse (browser-use's optimized model)
  - Set use_browser_use_llm=True in browser_task tool call
  - Set environment variable: BROWSER_USE_API_KEY
  - Pricing: $0.20/1M input tokens, $2.00/1M output tokens
  - Optimized for browser automation tasks (3-5x faster)

Configuration Examples:

# Use OpenAI directly (recommended):
export OPENAI_API_KEY=sk-...

# Or use OpenRouter:
export OPENROUTER_API_KEY=sk-or-v1-...

# Or use ChatBrowserUse:
export BROWSER_USE_API_KEY=...
# And pass use_browser_use_llm=True to browser_task
"""
