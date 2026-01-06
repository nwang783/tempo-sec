"""Pytest configuration for tempo-sec tests."""

import os
import pytest

# Keep unit tests hermetic/offline: avoid importing litellm for token counting.
# (litellm import registers async atexit cleanup which can cause noisy failures.)
os.environ.setdefault("TEMPO_USE_LITELLM_TOKENIZER", "0")


@pytest.fixture
def sample_message_data():
    """Sample message data for testing."""
    return {
        "role": "user",
        "content": "Scan the target system",
        "timestamp": "2024-01-15T10:30:00",
        "metadata": {},
    }


@pytest.fixture
def sample_tool_call_data():
    """Sample tool call data for testing."""
    return {
        "id": "tc-123",
        "tool_name": "shell",
        "input": {"command": "nmap -sV target.com"},
        "raw_output": "PORT     STATE SERVICE\n22/tcp   open  ssh\n80/tcp   open  http",
        "summary": None,
        "timestamp": "2024-01-15T10:31:00",
        "duration_ms": 5000,
        "success": True,
        "error": None,
    }
