#!/usr/bin/env python3
"""
Run Tempo Sec using config.toml settings.

This script loads all configuration from config.toml and runs
tools in a sandboxed Docker container.
"""

import asyncio
import os
from pathlib import Path

import tomli
from dotenv import load_dotenv

from tempo.agent import Agent, AgentConfig, WorkflowManager
from tempo.context import ContextStore
from tempo.context.frame import ToolCall
from tempo.infra import LiteLLMClient, ContainerManager
from tempo.infra.container import ContainerConfig
from tempo.tools.tool_factory import create_sandboxed_tools, create_local_tools


def load_config(config_path: str = "config.toml") -> dict:
    """Load configuration from TOML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path, "rb") as f:
        return tomli.load(f)


def create_agent_config(config: dict) -> AgentConfig:
    """Create AgentConfig from parsed TOML config."""
    return AgentConfig(
        # Model
        model=config.get("model", {}).get("provider", "anthropic/claude-sonnet-4-20250514"),
        
        # Context
        max_context_tokens=config.get("context", {}).get("max_tokens", 100000),
        auto_summarize=config.get("context", {}).get("auto_summarize", True),
        persistence_dir=config.get("context", {}).get("persistence_dir", "./contexts"),
        
        # Workflow
        enforce_phases=config.get("workflow", {}).get("enforce_phases", True),
        max_steps_per_phase=config.get("workflow", {}).get("max_steps_per_phase", 20),
        max_total_steps=config.get("workflow", {}).get("max_total_steps", 500),
        
        # Branching
        max_branches=config.get("branching", {}).get("max_branches", 5),
        max_branch_depth=config.get("branching", {}).get("max_branch_depth", 3),
        branch_step_limit=config.get("branching", {}).get("branch_step_limit", 100),
        
        # Container
        container_image=config.get("container", {}).get("image", "tempo-sec-base:latest"),
        container_timeout=config.get("container", {}).get("timeout", 300),
        
        # Scope
        allowed_domains=config.get("scope", {}).get("allowed_domains", []),
        excluded_domains=config.get("scope", {}).get("excluded_domains", []),
        allow_subdomains=config.get("scope", {}).get("allow_subdomains", True),
        
        # Logging
        verbose=config.get("logging", {}).get("verbose", False),
        log_level=config.get("logging", {}).get("level", "INFO"),
    )


# ============================================================================
# Logging Callbacks - Real-time output during agent execution
# ============================================================================

def log_tool_call(tool_call: ToolCall) -> None:
    """Log each tool call as it happens."""
    output_preview = tool_call.raw_output[:300] if tool_call.raw_output else "(no output)"
    if len(tool_call.raw_output or "") > 300:
        output_preview += "..."
    print(f"\n  [Tool: {tool_call.tool_name}]")
    print(f"    Input: {tool_call.input}")
    print(f"    Output: {output_preview}")


async def main():
    """Run agent using config.toml settings."""
    
    # Load environment variables from .env
    load_dotenv()
    
    # Load config
    config_path = Path(__file__).parent.parent / "config.toml"
    print(f"Loading config from: {config_path}")
    config = load_config(str(config_path))
    
    # Create agent config
    agent_config = create_agent_config(config)
    
    # Display loaded config
    print(f"\n{'='*50}")
    print("Loaded Configuration:")
    print(f"  Model: {agent_config.model}")
    print(f"  Max Steps: {agent_config.max_total_steps}")
    print(f"  Allowed Domains: {agent_config.allowed_domains}")
    print(f"  Container Image: {agent_config.container_image}")
    print(f"  Verbose: {agent_config.verbose}")
    print(f"{'='*50}\n")
    
    # Verify API key
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env file")
        return
    
    # Initialize LLM client
    llm = LiteLLMClient(model=agent_config.model)
    
    # Create context store
    context = ContextStore(persistence_dir=agent_config.persistence_dir)
    
    # Determine target from config
    domains = agent_config.allowed_domains
    if not domains:
        print("Warning: No allowed_domains specified in config. Using example.com as default.")
        target = "example.com"
    else:
        target = domains[0] if isinstance(domains[0], str) else str(domains[0])
    
    # Define objective
    objective = f"""
    Perform a reconnaissance scan on {target}:
    1. Identify publicly available information
    2. Map the site structure
    3. Note any potential security observations
    
    This is authorized security testing. Use safe, non-intrusive methods.
    Scope is limited to: {', '.join(str(d) for d in domains) if domains else 'example.com'}
    """
    
    # Check if we should use container
    use_container = os.getenv("TEMPO_LOCAL_MODE", "").lower() != "true"
    
    if use_container:
        print("Starting sandboxed container...")
        container_config = ContainerConfig(
            image=agent_config.container_image,
            timeout=agent_config.container_timeout,
        )
        container = ContainerManager(container_config)
        
        async with container:  # Auto start/stop
            print(f"Container started. Running agent...\n")
            
            # Create workflow manager and tools
            workflow = WorkflowManager(agent_config)
            
            # Create sandboxed tools with workflow manager for transition_phase
            tools = create_sandboxed_tools(
                container=container,
                context_store=context,
                workflow_manager=workflow,
            )
            
            # Create agent with logging callbacks
            agent = Agent(
                config=agent_config,
                llm=llm,
                tools=tools,
                context=context,
                on_tool_call=log_tool_call,
            )
            
            print(f"Starting agent with objective:\n{objective}")
            print("-" * 50)
            
            # Run the agent
            result = await agent.run(
                objective=objective,
                max_steps=agent_config.max_total_steps,
            )
    else:
        print("WARNING: Running in local mode (no container). Set TEMPO_LOCAL_MODE=true only for testing.\n")
        
        # Create workflow manager and local tools
        workflow = WorkflowManager(agent_config)
        tools = create_local_tools(context_store=context, workflow_manager=workflow)
        
        # Create agent with logging callbacks
        agent = Agent(
            config=agent_config,
            llm=llm,
            tools=tools,
            context=context,
            on_tool_call=log_tool_call,
        )
        
        print(f"Starting agent with objective:\n{objective}")
        print("-" * 50)
        
        # Run the agent
        result = await agent.run(
            objective=objective,
            max_steps=agent_config.max_total_steps,
        )
    
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
    
    # Save context
    context_path = context.save()
    print(f"\nContext saved to: {context_path}")


if __name__ == "__main__":
    asyncio.run(main())
