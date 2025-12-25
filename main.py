"""
Tempo Sec - Agentic Cybersecurity System

This is the main entry point for running Tempo agents.
It redirects to the unified runner.

Usage:
    python main.py --agent <name> [options]
    
Example:
    python main.py --agent recon --target https://example.com
    python main.py --agent test_cycle --manifest ./manifests/example_com_manifest.json
"""

import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

from tempo.scripts.run import main_sync

if __name__ == "__main__":
    main_sync()
