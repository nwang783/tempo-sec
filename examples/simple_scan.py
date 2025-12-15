#!/usr/bin/env python3
"""
Simple example demonstrating basic Tempo Sec usage.

This example shows how to:
1. Configure the agent
2. Set up tools and LLM
3. Run a basic security assessment
"""

import asyncio
import os
from pathlib import Path

from tempo.agent import Agent, AgentConfig
from tempo.context import ContextStore
from tempo.infra import LiteLLMClient, ContainerManager
from tempo.prompts import PromptBuilder, Phase
from tempo.tools import ToolRegistry


async def main():
    """Run a simple security scan."""
    
    # Load API key from environment
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable")
        return
    
    # Configuration
    config = AgentConfig(
        model="anthropic/claude-sonnet-4-20250514",  # or "openai/gpt-4o"
        max_total_steps=50,
        allowed_domains=["example.com"],  # Scope limitation
        verbose=True,
    )
    
    # Initialize components
    llm = LiteLLMClient(model=config.model)
    
    # Optional: Use container for sandboxed execution
    # container = ContainerManager()
    # await container.start()
    
    # Set up tools
    tools = ToolRegistry()
    
    # Register built-in tools (without container for this example)
    from tempo.tools import ShellTool, FileReadTool, FileWriteTool, BrowserTool
    from tempo.tools import FinishTaskTool, SummarizeOutputTool
    
    tools.register(ShellTool())
    tools.register(FileReadTool())
    tools.register(FileWriteTool())
    tools.register(BrowserTool())
    tools.register(FinishTaskTool())
    
    # Create context store
    context = ContextStore(persistence_dir="./contexts")
    
    # Create agent
    agent = Agent(
        config=config,
        llm=llm,
        tools=tools,
        context=context,
    )
    
    # Define objective
    objective = """
    Perform a reconnaissance scan on example.com:
    1. Identify publicly available information
    2. Map the site structure
    3. Note any potential security observations
    
    This is a demonstration - only use safe, non-intrusive methods.
    """
    
    print(f"Starting agent with objective:\n{objective}")
    print("-" * 50)
    
    # Run the agent
    result = await agent.run(objective=objective, max_steps=10)
    
    # Print results
    print("-" * 50)
    print(f"\nResult: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Steps taken: {result.steps_taken}")
    print(f"Final phase: {result.final_phase.value}")
    
    if result.findings:
        print("\nFindings:")
        for finding in result.findings:
            print(f"  - {finding}")
    
    if result.error:
        print(f"\nError: {result.error}")
    
    # Save context for later resumption
    context_path = context.save()
    print(f"\nContext saved to: {context_path}")
    
    # Optional: Clean up container
    # await container.stop()


if __name__ == "__main__":
    asyncio.run(main())
