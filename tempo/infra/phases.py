"""
Workflow phase definitions.

Located in infra/ so tools can import without violating dependency rules:
    Context, Prompts, and Tools MUST NOT import from each other.
    They may only import from infra/ or external packages.
"""

from enum import Enum


class Phase(str, Enum):
    """Workflow phases for the security agent."""
    RECON = "recon"
    HYPOTHESIZE = "hypothesize"
    TEST = "test"
    REFLECT = "reflect"
