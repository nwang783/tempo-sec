"""
Findings module for structured security testing results.

Exports:
    - FindingsDocument: Main interface for managing findings
    - Schema models: Severity, FindingStatus, AttackSurface, Finding, etc.
    - Persistence: save_to_yaml, load_from_yaml
"""

from tempo.findings.document import FindingsDocument
from tempo.findings.schema import (
    AttackSurface,
    Finding,
    FindingStatus,
    FindingsDocumentSchema,
    ReconSummary,
    Severity,
)
from tempo.findings.persistence import load_from_yaml, save_to_yaml

__all__ = [
    "FindingsDocument",
    "FindingsDocumentSchema",
    "AttackSurface",
    "Finding",
    "ReconSummary",
    "Severity",
    "FindingStatus",
    "save_to_yaml",
    "load_from_yaml",
]
