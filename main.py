#!/usr/bin/env python3
"""
Tempo Sec - Main Entry Point

Redirects to the CLI implementation in tempo.cli.
Run with: python3 main.py [options]
"""

import sys
import asyncio
from tempo.cli import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(0)
