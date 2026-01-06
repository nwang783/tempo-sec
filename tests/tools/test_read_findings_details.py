
import pytest
from unittest.mock import MagicMock
from tempo.tools.findings_tools import ReadFindingsTool
from tempo.findings.schema import Finding, AttackSurface, Severity

@pytest.mark.asyncio
async def test_read_findings_with_details():
    mock_updater = MagicMock()
    
    # Mock summary
    mock_updater.get_summary.return_value = {
        "target": "test.com",
        "created_at": "now",
        "updated_at": "now",
        "total_surfaces": 1,
        "tested_surfaces": 0,
        "untested_surfaces": 1,
        "total_findings": 1,
        "findings_by_severity": {"critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0},
        "agents_invoked": [],
        "total_steps": 0
    }

    # Mock detailed lists
    mock_finding = MagicMock(spec=Finding)
    mock_finding.id = "f1"
    mock_finding.title = "Test Finding"
    mock_finding.severity = "high"
    mock_finding.status = "confirmed"

    mock_surface = MagicMock(spec=AttackSurface)
    mock_surface.id = "s1"
    mock_surface.surface_type = "api"
    mock_surface.url = "/api/v1"
    mock_surface.tested = False

    mock_updater.get_all_findings.return_value = [mock_finding]
    mock_updater.get_all_surfaces.return_value = [mock_surface]

    tool = ReadFindingsTool(findings_updater=mock_updater)

    # Test with details enabled
    result = await tool.execute(include_findings=True, include_surfaces=True)

    assert result.success
    assert "Test Finding" in result.output
    assert "f1" in result.output
    assert "/api/v1" in result.output
    assert "s1" in result.output
    assert "### Detailed Findings List ###" in result.output
    assert "### Attack Surfaces List ###" in result.output
