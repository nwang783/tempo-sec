"""Tests for tempo/tools/findings_tools.py."""

import pytest

from tempo.findings.document import FindingsDocument
from tempo.findings.schema import FindingStatus, Severity
from tempo.tools.findings_tools import (
    AddAttackSurfaceTool,
    AddFindingTool,
    MarkSurfaceTestedTool,
    ReadFindingsTool,
    UpdateReconSummaryTool,
)


@pytest.fixture
def findings_doc():
    """Create a findings document for testing."""
    return FindingsDocument(target="https://example.com")


class TestReadFindingsTool:
    """Tests for ReadFindingsTool."""

    @pytest.mark.asyncio
    async def test_read_empty_document(self, findings_doc):
        """Test reading an empty findings document."""
        tool = ReadFindingsTool(findings_doc)

        result = await tool.execute()

        assert result.success is True
        assert "https://example.com" in result.output
        assert "Total: 0" in result.output

    @pytest.mark.asyncio
    async def test_read_with_data(self, findings_doc):
        """Test reading document with data."""
        # Add some data
        findings_doc.add_attack_surface(
            surface_id="surf-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="Test",
            discovered_by="recon",
        )

        findings_doc.add_finding(
            finding_id="find-1",
            title="Test Finding",
            severity=Severity.HIGH,
            status=FindingStatus.CONFIRMED,
            description="Test",
            evidence="proof",
            discovered_by="tester",
        )

        tool = ReadFindingsTool(findings_doc)
        result = await tool.execute()

        assert result.success is True
        assert "Total: 1" in result.output
        assert "High: 1" in result.output

    def test_get_schema(self, findings_doc):
        """Test tool schema."""
        tool = ReadFindingsTool(findings_doc)
        schema = tool.get_schema()

        assert schema.name == "read_findings"
        assert "properties" in schema.parameters


class TestAddAttackSurfaceTool:
    """Tests for AddAttackSurfaceTool."""

    @pytest.mark.asyncio
    async def test_add_basic_surface(self, findings_doc):
        """Test adding a basic attack surface."""
        tool = AddAttackSurfaceTool(findings_doc)

        result = await tool.execute(
            surface_type="endpoint",
            url="https://example.com/api/login",
            description="Login endpoint",
            discovered_by="recon_agent",
        )

        assert result.success is True
        assert "endpoint" in result.output
        assert "surface_id" in result.metadata
        assert len(findings_doc._data.attack_surfaces) == 1

    @pytest.mark.asyncio
    async def test_add_surface_with_all_fields(self, findings_doc):
        """Test adding surface with all optional fields."""
        tool = AddAttackSurfaceTool(findings_doc)

        result = await tool.execute(
            surface_type="form",
            url="https://example.com/upload",
            description="File upload form",
            discovered_by="recon_agent",
            parameters=["file", "description"],
            technology_hints=["PHP", "nginx"],
            priority="high",
        )

        assert result.success is True

        surface = findings_doc._data.attack_surfaces[0]
        assert surface.surface_type == "form"
        assert surface.parameters == ["file", "description"]
        assert surface.technology_hints == ["PHP", "nginx"]
        assert surface.priority == "high"

    @pytest.mark.asyncio
    async def test_add_surface_invalid_priority(self, findings_doc):
        """Test that invalid priority defaults to medium."""
        tool = AddAttackSurfaceTool(findings_doc)

        result = await tool.execute(
            surface_type="endpoint",
            url="https://example.com/api",
            description="Test",
            discovered_by="recon",
            priority="invalid",
        )

        assert result.success is True
        surface = findings_doc._data.attack_surfaces[0]
        assert surface.priority == "medium"

    def test_get_schema(self, findings_doc):
        """Test tool schema."""
        tool = AddAttackSurfaceTool(findings_doc)
        schema = tool.get_schema()

        assert schema.name == "add_attack_surface"
        assert "surface_type" in schema.parameters["properties"]
        assert "url" in schema.parameters["properties"]
        assert "surface_type" in schema.parameters["required"]


class TestAddFindingTool:
    """Tests for AddFindingTool."""

    @pytest.mark.asyncio
    async def test_add_basic_finding(self, findings_doc):
        """Test adding a basic finding."""
        tool = AddFindingTool(findings_doc)

        result = await tool.execute(
            title="SQL Injection",
            severity="high",
            status="confirmed",
            description="SQL injection in login form",
            evidence="Error message reveals database structure",
            discovered_by="test_agent",
        )

        assert result.success is True
        assert "SQL Injection" in result.output
        assert "finding_id" in result.metadata
        assert len(findings_doc._data.findings) == 1

    @pytest.mark.asyncio
    async def test_add_finding_with_all_fields(self, findings_doc):
        """Test adding finding with all optional fields."""
        tool = AddFindingTool(findings_doc)

        result = await tool.execute(
            title="XSS Vulnerability",
            severity="medium",
            status="suspected",
            description="Reflected XSS",
            evidence="Script executed",
            discovered_by="xss_scanner",
            attack_surface_id="surf-123",
            reproduction_steps=["Step 1", "Step 2", "Step 3"],
            remediation="Sanitize user input",
            validated_by="manual_tester",
        )

        assert result.success is True

        finding = findings_doc._data.findings[0]
        assert finding.title == "XSS Vulnerability"
        assert finding.attack_surface_id == "surf-123"
        assert len(finding.reproduction_steps) == 3
        assert finding.remediation == "Sanitize user input"
        assert finding.validated_by == "manual_tester"

    @pytest.mark.asyncio
    async def test_add_finding_invalid_severity(self, findings_doc):
        """Test that invalid severity returns error."""
        tool = AddFindingTool(findings_doc)

        result = await tool.execute(
            title="Test",
            severity="invalid",
            status="confirmed",
            description="Test",
            evidence="proof",
            discovered_by="tester",
        )

        assert result.success is False
        assert "Invalid severity" in result.error

    @pytest.mark.asyncio
    async def test_add_finding_invalid_status(self, findings_doc):
        """Test that invalid status returns error."""
        tool = AddFindingTool(findings_doc)

        result = await tool.execute(
            title="Test",
            severity="high",
            status="invalid",
            description="Test",
            evidence="proof",
            discovered_by="tester",
        )

        assert result.success is False
        assert "Invalid status" in result.error

    def test_get_schema(self, findings_doc):
        """Test tool schema."""
        tool = AddFindingTool(findings_doc)
        schema = tool.get_schema()

        assert schema.name == "add_finding"
        assert "title" in schema.parameters["properties"]
        assert "severity" in schema.parameters["properties"]
        assert "status" in schema.parameters["properties"]
        assert set(schema.parameters["required"]) >= {
            "title",
            "severity",
            "status",
            "description",
            "evidence",
            "discovered_by",
        }


class TestMarkSurfaceTestedTool:
    """Tests for MarkSurfaceTestedTool."""

    @pytest.mark.asyncio
    async def test_mark_surface_tested(self, findings_doc):
        """Test marking an attack surface as tested."""
        # Add a surface first
        findings_doc.add_attack_surface(
            surface_id="surf-1",
            surface_type="endpoint",
            url="https://example.com/api",
            description="Test",
            discovered_by="recon",
        )

        tool = MarkSurfaceTestedTool(findings_doc)
        result = await tool.execute(surface_id="surf-1")

        assert result.success is True
        assert "surf-1" in result.output
        assert findings_doc._data.attack_surfaces[0].tested is True

    @pytest.mark.asyncio
    async def test_mark_nonexistent_surface(self, findings_doc):
        """Test marking non-existent surface returns error."""
        tool = MarkSurfaceTestedTool(findings_doc)

        result = await tool.execute(surface_id="nonexistent")

        assert result.success is False
        assert "not found" in result.error

    def test_get_schema(self, findings_doc):
        """Test tool schema."""
        tool = MarkSurfaceTestedTool(findings_doc)
        schema = tool.get_schema()

        assert schema.name == "mark_surface_tested"
        assert "surface_id" in schema.parameters["properties"]
        assert "surface_id" in schema.parameters["required"]


class TestUpdateReconSummaryTool:
    """Tests for UpdateReconSummaryTool."""

    @pytest.mark.asyncio
    async def test_update_all_fields(self, findings_doc):
        """Test updating all recon summary fields."""
        tool = UpdateReconSummaryTool(findings_doc)

        result = await tool.execute(
            total_endpoints=10,
            total_forms=5,
            total_apis=3,
            technologies_detected=["React", "Express", "MongoDB"],
            authentication_mechanisms=["JWT", "Session Cookies"],
            notes="Modern web application",
        )

        assert result.success is True
        assert "endpoints: 10" in result.output
        assert "forms: 5" in result.output

        summary = findings_doc._data.recon_summary
        assert summary.total_endpoints == 10
        assert summary.total_forms == 5
        assert summary.total_apis == 3
        assert len(summary.technologies_detected) == 3
        assert len(summary.authentication_mechanisms) == 2
        assert summary.notes == "Modern web application"

    @pytest.mark.asyncio
    async def test_update_partial_fields(self, findings_doc):
        """Test updating only some fields."""
        tool = UpdateReconSummaryTool(findings_doc)

        result = await tool.execute(
            total_endpoints=15,
            notes="Updated notes",
        )

        assert result.success is True
        assert "endpoints: 15" in result.output
        assert "notes updated" in result.output

        summary = findings_doc._data.recon_summary
        assert summary.total_endpoints == 15
        assert summary.total_forms == 0  # Default
        assert summary.notes == "Updated notes"

    @pytest.mark.asyncio
    async def test_update_creates_summary_if_none(self, findings_doc):
        """Test that update creates summary if it doesn't exist."""
        assert findings_doc._data.recon_summary is None

        tool = UpdateReconSummaryTool(findings_doc)
        await tool.execute(total_endpoints=5)

        assert findings_doc._data.recon_summary is not None
        assert findings_doc._data.recon_summary.total_endpoints == 5

    def test_get_schema(self, findings_doc):
        """Test tool schema."""
        tool = UpdateReconSummaryTool(findings_doc)
        schema = tool.get_schema()

        assert schema.name == "update_recon_summary"
        assert "total_endpoints" in schema.parameters["properties"]
        assert "technologies_detected" in schema.parameters["properties"]
        assert schema.parameters["required"] == []  # All fields optional
