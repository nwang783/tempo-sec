#!/usr/bin/env python3
"""
Tempo Sec - Main Entry Point

Usage:
    Recon:  python -m tempo.scripts.recon --target example.com
    Test:   python -m tempo.scripts.test_cycle --manifest ./manifests/example.json
"""

import sys


def main():
    print("Tempo Sec - Security Testing Agent")
    print()
    print("Usage:")
    print("  Recon:  python -m tempo.scripts.recon --target <domain>")
    print("  Test:   python -m tempo.scripts.test_cycle --manifest <path>")
    print()
    print("Or use the installed commands:")
    print("  tempo-recon --target <domain>")
    print("  tempo-test --manifest <path>")


if __name__ == "__main__":
    main()
