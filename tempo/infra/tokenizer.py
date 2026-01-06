"""
Token counting utilities using LiteLLM.

Provides model-aware token counting for accurate context size estimation.
Falls back to a character-based heuristic if tokenization fails.
"""

from typing import TYPE_CHECKING
import os

if TYPE_CHECKING:
    pass

# Default model for tokenization when model is not specified.
# Uses cl100k_base encoding which is common for modern models.
DEFAULT_TOKENIZER_MODEL = "gpt-4o"


def count_tokens(text: str, model: str | None = None) -> int:
    """
    Count tokens in text using LiteLLM's model-aware tokenizer.
    
    Uses the appropriate tokenizer for the specified model when available,
    falling back to a character-based heuristic if tokenization fails.
    
    Args:
        text: The text to count tokens for
        model: Optional model name for accurate counting (e.g., "gpt-4o", 
               "anthropic/claude-sonnet-4-20250514"). Defaults to gpt-4o.
        
    Returns:
        Token count
    """
    if not text:
        return 0
    
    model_to_use = model or DEFAULT_TOKENIZER_MODEL
    
    # NOTE: Importing litellm has side effects (registers async atexit cleanup).
    # Tests can disable via TEMPO_USE_LITELLM_TOKENIZER=0.
    use_litellm = os.getenv("TEMPO_USE_LITELLM_TOKENIZER", "1").lower() not in ("0", "false", "no")
    if use_litellm:
        try:
            import litellm
            return litellm.token_counter(model=model_to_use, text=text)
        except Exception:
            # Fall through to heuristic if tokenizer fails (import error, unsupported model, etc.)
            pass

    # Heuristic fallback: ~4 chars/token is a common rough estimate for English text.
    return len(text) // 4
