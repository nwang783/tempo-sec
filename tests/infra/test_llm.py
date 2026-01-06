"""
Tests for the LLM infrastructure module.

Tests token usage with caching fields, cost calculation, and response normalization.
"""

import pytest
from dataclasses import asdict
from unittest.mock import MagicMock, patch

from tempo.infra.llm import TokenUsage, LLMResponse, LiteLLMClient, ToolCallRequest


class TestTokenUsage:
    """Tests for the TokenUsage dataclass."""
    
    def test_default_values(self):
        """Verify default values are zero."""
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.cached_tokens == 0
        assert usage.cache_creation_tokens == 0
        assert usage.cost == 0.0
    
    def test_with_caching_info(self):
        """Verify caching fields can be set."""
        usage = TokenUsage(
            prompt_tokens=1000,
            completion_tokens=200,
            total_tokens=1200,
            cached_tokens=800,
            cache_creation_tokens=100,
            cost=0.0025
        )
        assert usage.prompt_tokens == 1000
        assert usage.completion_tokens == 200
        assert usage.total_tokens == 1200
        assert usage.cached_tokens == 800
        assert usage.cache_creation_tokens == 100
        assert usage.cost == 0.0025
    
    def test_asdict_serialization(self):
        """Verify TokenUsage can be serialized to dict."""
        usage = TokenUsage(
            prompt_tokens=500,
            completion_tokens=100,
            total_tokens=600,
            cached_tokens=400,
            cost=0.001
        )
        data = asdict(usage)
        assert data["prompt_tokens"] == 500
        assert data["cached_tokens"] == 400
        assert data["cost"] == 0.001


class TestLLMResponse:
    """Tests for the LLMResponse dataclass."""
    
    def test_response_with_usage(self):
        """Verify LLMResponse includes usage with caching."""
        usage = TokenUsage(
            prompt_tokens=1000,
            cached_tokens=500,
            cost=0.005
        )
        response = LLMResponse(
            content="Test response",
            usage=usage,
            model="gpt-4o"
        )
        assert response.usage.cached_tokens == 500
        assert response.usage.cost == 0.005


class TestLiteLLMClientNormalization:
    """Tests for response normalization with caching info."""
    
    @pytest.fixture
    def mock_client(self):
        """Create a mocked LiteLLM client."""
        # Inject mocks so we don't import litellm/instructor at all during unit tests.
        client = LiteLLMClient(
            model="gpt-5-mini",
            litellm_module=MagicMock(),
            instructor_client=MagicMock(),
        )
        return client
    
    def test_normalize_response_with_cache_info(self, mock_client):
        """Test _normalize_response extracts caching info."""
        # Mock a response with prompt_tokens_details
        mock_response = MagicMock()
        mock_response.model = "gpt-4o"
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        
        # Mock usage with caching details
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 1000
        mock_response.usage.completion_tokens = 200
        mock_response.usage.total_tokens = 1200
        
        # Simulate prompt_tokens_details with cached_tokens
        mock_response.usage.prompt_tokens_details = MagicMock()
        mock_response.usage.prompt_tokens_details.cached_tokens = 800
        
        # Mock completion_cost to return a value
        mock_client._litellm.completion_cost = MagicMock(return_value=0.0025)
        
        # Normalize
        result = mock_client._normalize_response(mock_response)
        
        assert result.usage.prompt_tokens == 1000
        assert result.usage.cached_tokens == 800
        assert result.usage.cost == 0.0025
    
    def test_normalize_response_without_cache_details(self, mock_client):
        """Test _normalize_response handles missing cache details gracefully."""
        mock_response = MagicMock()
        mock_response.model = "gpt-4o"
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 500
        mock_response.usage.completion_tokens = 100
        mock_response.usage.total_tokens = 600
        mock_response.usage.prompt_tokens_details = None  # No cache info
        
        # Delete the attribute to simulate not having it
        del mock_response.usage.cache_creation_input_tokens
        
        mock_client._litellm.completion_cost = MagicMock(return_value=0.001)
        
        result = mock_client._normalize_response(mock_response)
        
        assert result.usage.cached_tokens == 0  # Should default to 0
        assert result.usage.cache_creation_tokens == 0
        assert result.usage.cost == 0.001
    
    def test_normalize_response_with_anthropic_cache_creation(self, mock_client):
        """Test extraction of Anthropic's cache_creation_input_tokens."""
        mock_response = MagicMock()
        mock_response.model = "claude-3-sonnet"
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from Claude"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "end_turn"
        
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 2000
        mock_response.usage.completion_tokens = 300
        mock_response.usage.total_tokens = 2300
        mock_response.usage.prompt_tokens_details = MagicMock()
        mock_response.usage.prompt_tokens_details.cached_tokens = 1500
        mock_response.usage.cache_creation_input_tokens = 500  # Anthropic-specific
        
        mock_client._litellm.completion_cost = MagicMock(return_value=0.008)
        
        result = mock_client._normalize_response(mock_response)
        
        assert result.usage.cached_tokens == 1500
        assert result.usage.cache_creation_tokens == 500
        assert result.usage.cost == 0.008
    
    def test_normalize_response_cost_calculation_failure(self, mock_client):
        """Test graceful handling when cost calculation fails."""
        mock_response = MagicMock()
        mock_response.model = "unknown-model"
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150
        mock_response.usage.prompt_tokens_details = None
        
        # Simulate cost calculation failure
        mock_client._litellm.completion_cost = MagicMock(
            side_effect=Exception("Unknown model pricing")
        )
        
        result = mock_client._normalize_response(mock_response)
        
        # Cost should default to 0.0 on failure
        assert result.usage.cost == 0.0
