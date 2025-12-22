#!/usr/bin/env python3
"""
Tempo Sec - Testing Cycle Script

Loads a target manifest and runs hypothesis/test/reflect cycles.
This script is designed to consume the output from recon.py and
execute the testing workflow until completion.

Usage:
    python -m tempo.scripts.test_cycle --config config.toml --manifest ./manifests/target_manifest.json
    python -m tempo.scripts.test_cycle --manifest ./manifests/target_manifest.json --context ./contexts/previous.json
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Tempo Sec Test Cycle - Run hypothesis/test/reflect loops"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.toml",
        help="Path to configuration file (default: config.toml)",
    )
    
    parser.add_argument(
        "--manifest",
        type=str,
        help="Path to target manifest JSON from recon phase (overrides config)",
    )
    
    parser.add_argument(
        "--context",
        type=str,
        help="Path to existing context file to resume from",
    )
    
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run in local mode (no docker sandbox)",
    )
    
    parser.add_argument(
        "--max-steps",
        type=int,
        help="Maximum steps for testing (overrides config)",
    )
    
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Disable visualization server",
    )
    
    return parser.parse_args()


def load_manifest(manifest_path: str) -> "TargetManifest":
    """Load and validate the target manifest."""
    from tempo.schema.manifest import TargetManifest
    
    if not Path(manifest_path).exists():
        print(f"Error: Manifest file not found: {manifest_path}")
        sys.exit(1)
    
    try:
        return TargetManifest.load(manifest_path)
    except Exception as e:
        print(f"Error loading manifest: {e}")
        sys.exit(1)


async def main() -> None:
    """Main entry point for test cycle script."""
    args = parse_args()
    
    # Load environment
    load_dotenv()
    
    # Import after dotenv
    from tempo import AgentConfig, Agent, ContextStore, LiteLLMClient, WorkflowManager
    from tempo.infra.container import ContainerConfig, ContainerManager
    from tempo.tools.registry import ToolRegistry
    from tempo.tools.shell import ShellTool
    from tempo.tools.filesystem import FileReadTool, FileWriteTool
    from tempo.tools.browser_tools import (
        BrowserSession,
        BrowserNavigateTool,
        BrowserSnapshotTool,
        BrowserClickTool,
        BrowserTypeTool,
        BrowserFillFormTool,
    )
    from tempo.tools.meta import (
        TransitionPhaseTool,
        SummarizeOutputTool,
        ContinueAnalysisTool,
        BranchToSubtasksTool,
        FinishSubtaskTool,
        CreateTestPlanTool,
        AddTodoTool,
        CompleteTodoTool,
    )
    from tempo.tools.view_output import ViewToolOutputTool
    from tempo.prompts.phases import Phase
    from tempo.prompts.builder import PromptBuilder
    from tempo.context.frame import MessageRole
    from tempo.schema.manifest import TargetManifest
    
    try:
        from tempo.visualization import VisualizationCollector, VisualizationServer, UserPromptManager
    except ImportError:
        VisualizationServer = None
        VisualizationCollector = None
        UserPromptManager = None
    
    # Load config
    try:
        config = AgentConfig.from_toml(args.config)
    except FileNotFoundError:
        print(f"Config file not found: {args.config}")
        if args.config == "config.toml":
            print("Using default configuration.")
            config = AgentConfig()
        else:
            sys.exit(1)
    
    # Validate API keys
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")):
        print("Error: No API key found in environment variables.")
        sys.exit(1)
    
    # Determine manifest path
    manifest_path = args.manifest or getattr(config, "manifest_path", None)
    if not manifest_path:
        print("Error: No manifest path provided. Use --manifest or set [manifest].path in config.")
        sys.exit(1)
    
    # Load manifest
    print(f"📄 Loading manifest: {manifest_path}")
    manifest = load_manifest(manifest_path)
    print(f"🎯 Target: {manifest.metadata.target_domain}")
    print(f"   {len(manifest.sitemap)} endpoints, {len(manifest.attack_surfaces)} attack surfaces")
    
    # Setup Context
    step_count = 0
    if args.context:
        print(f"Loading context from {args.context}...")
        try:
            context = ContextStore.load(args.context)
            # Estimate step count from tool calls
            step_count = len(context.current_frame.tool_calls)
        except Exception as e:
            print(f"Error loading context: {e}")
            sys.exit(1)
    else:
        context = ContextStore(persistence_dir=config.persistence_dir)
    
    # Setup LLM
    llm = LiteLLMClient(model=config.model)
    
    # Setup Visualization
    viz_server = None
    viz_collector = None
    prompt_manager = None
    stop_event = asyncio.Event()
    
    if not args.no_viz and config.enable_visualization and VisualizationServer:
        print(f"Starting visualization server on {config.visualization_host}:{config.visualization_port}")
        if UserPromptManager:
            prompt_manager = UserPromptManager()
        viz_server = VisualizationServer(
            host=config.visualization_host,
            port=config.visualization_port,
            auto_open=config.auto_open_browser,
            prompt_manager=prompt_manager,
            stop_event=stop_event,
        )
        await viz_server.start()
        viz_collector = VisualizationCollector(viz_server)
    
    # Create testing tools registry
    def create_testing_tools(container=None, workflow=None) -> ToolRegistry:
        """Create testing-specific tool registry."""
        tools = ToolRegistry()
        
        # Core tools
        if container:
            tools.register(ShellTool(container_manager=container))
            tools.register(FileReadTool(container_manager=container))
            tools.register(FileWriteTool(container_manager=container))
            
            # Playwright-style browser tools
            browser_session = BrowserSession(container_manager=container)
        else:
            tools.register(ShellTool())
            tools.register(FileReadTool())
            tools.register(FileWriteTool())
            
            # Playwright-style browser tools (local)
            browser_session = BrowserSession()
        
        # Register browser tools
        tools.register(BrowserNavigateTool(browser_session))
        tools.register(BrowserSnapshotTool(browser_session))
        tools.register(BrowserClickTool(browser_session))
        tools.register(BrowserTypeTool(browser_session))
        tools.register(BrowserFillFormTool(browser_session))
        
        # Meta tools for testing workflow
        tools.register(SummarizeOutputTool(context_store=context))
        tools.register(ViewToolOutputTool(context_store=context))
        tools.register(ContinueAnalysisTool())
        
        # Hypothesis checklist tools
        tools.register(CreateTestPlanTool(test_plan_manager=context))
        tools.register(AddTodoTool(test_plan_manager=context))
        tools.register(CompleteTodoTool(test_plan_manager=context))
        
        if workflow:
            tools.register(TransitionPhaseTool(workflow_manager=workflow))
        
        return tools
    
    # Build testing objective with manifest context
    manifest_summary = manifest.to_summary()
    
    objective = f"""Perform security testing on {manifest.metadata.target_domain}

## Reconnaissance Summary (from manifest)

{manifest_summary}

---

## Your Task

Based on the reconnaissance data above:

1. **HYPOTHESIZE**: Form specific, testable security hypotheses based on the identified attack surfaces
2. **TEST**: Execute tests to validate or refute each hypothesis
3. **REFLECT**: Analyze results and decide whether to continue with more testing

Focus on the attack surfaces identified during recon. Prioritize by risk level.

After reflecting, use `continue_analysis` to either:
- Continue with more testing (should_continue=true) → loops back to HYPOTHESIZE
- Complete the analysis (should_continue=false) → provide final findings"""

    # Determine max steps
    max_steps = args.max_steps or config.max_total_steps or 100
    
    # Runner function
    async def run_testing_agent(tools: ToolRegistry, workflow: WorkflowManager) -> None:
        """Run the testing agent."""
        prompts = PromptBuilder()
        
        agent = Agent(
            config=config,
            llm=llm,
            tools=tools,
            context=context,
            prompts=prompts,
            workflow=workflow,
            visualization_collector=viz_collector,
            prompt_manager=prompt_manager,
            stop_event=stop_event,
        )
        
        result = await agent.run(
            objective=objective,
            initial_phase=Phase.HYPOTHESIZE,  # Start at HYPOTHESIZE since recon is done
            max_steps=max_steps,
            start_step=step_count,
        )
        
        print(f"\n{'='*50}")
        if result.success:
            print("✅ Testing completed successfully")
        else:
            print(f"❌ Testing failed: {result.error}")
        
        print(f"Steps taken: {result.steps_taken}")
        print(f"Final phase: {result.final_phase.value}")
        
        if result.findings:
            print("\n📋 Findings:")
            for finding in result.findings:
                print(f"  - {finding}")
    
    # Execute with appropriate container setup
    use_container = not args.local and os.getenv("TEMPO_LOCAL_MODE", "").lower() != "true"
    
    try:
        if use_container:
            print("🐳 Initializing container sandbox...")
            container_config = ContainerConfig(
                image=config.container_image,
                timeout=config.container_timeout,
            )
            container = ContainerManager(container_config)
            async with container:
                workflow = WorkflowManager(config, initial_phase=Phase.HYPOTHESIZE)
                tools = create_testing_tools(container, workflow)
                await run_testing_agent(tools, workflow)
        else:
            print("⚠️  Running in LOCAL mode (no sandbox)...")
            workflow = WorkflowManager(config, initial_phase=Phase.HYPOTHESIZE)
            tools = create_testing_tools(workflow=workflow)
            await run_testing_agent(tools, workflow)
        
        # Save context
        save_path = context.save()
        print(f"Context saved to: {save_path}")
        
    finally:
        if viz_server:
            print("Press Enter to stop visualization server...")
            try:
                input()
            except:
                pass
            await viz_server.stop()


def main_sync() -> None:
    """Synchronous entry point for CLI."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTesting cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main_sync()
