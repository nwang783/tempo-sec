"""Tests for tempo/findings/persistence.py."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from tempo.findings.persistence import load_from_yaml, save_to_yaml
from tempo.findings.schema import (
    AttackSurface,
    Finding,
    FindingStatus,
    FindingsDocumentSchema,
    ReconSummary,
    Severity,
)


class TestSaveToYaml:
    """Tests for save_to_yaml function."""

    def test_save_minimal_document(self):
        """Test saving a minimal document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            doc = FindingsDocumentSchema(target="https://example.com")
            save_to_yaml(doc, path)

            assert Path(path).exists()

            # Verify it's valid YAML
            with open(path) as f:
                data = yaml.safe_load(f)

            assert data["target"] == "https://example.com"
            assert data["version"] == "1.0"

    def test_save_with_nested_data(self):
        """Test saving document with nested structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            surface = AttackSurface(
                id="surf-1",
                surface_type="endpoint",
                url="https://example.com/api",
                description="Test endpoint",
                discovered_by="recon",
            )

            finding = Finding(
                id="find-1",
                title="Test Finding",
                severity=Severity.HIGH,
                status=FindingStatus.CONFIRMED,
                description="A test finding",
                evidence="Test evidence",
                discovered_by="tester",
            )

            doc = FindingsDocumentSchema(
                target="https://example.com",
                attack_surfaces=[surface],
                findings=[finding],
            )

            save_to_yaml(doc, path)

            # Verify structure
            with open(path) as f:
                data = yaml.safe_load(f)

            assert len(data["attack_surfaces"]) == 1
            assert data["attack_surfaces"][0]["id"] == "surf-1"
            assert len(data["findings"]) == 1
            assert data["findings"][0]["severity"] == "high"

    def test_save_creates_parent_directory(self):
        """Test that save creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "subdir" / "test.yaml")

            doc = FindingsDocumentSchema(target="https://example.com")
            save_to_yaml(doc, path)

            assert Path(path).exists()

    def test_save_preserves_datetime(self):
        """Test that datetime objects are properly serialized."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            now = datetime.utcnow()
            doc = FindingsDocumentSchema(
                target="https://example.com",
                created_at=now,
                updated_at=now,
            )

            save_to_yaml(doc, path)

            # Load and verify
            with open(path) as f:
                data = yaml.safe_load(f)

            # Should be datetime objects or ISO strings
            assert "created_at" in data
            assert "updated_at" in data


class TestLoadFromYaml:
    """Tests for load_from_yaml function."""

    def test_load_minimal_document(self):
        """Test loading a minimal document."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            # Create YAML file manually
            data = {
                "version": "1.0",
                "target": "https://example.com",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

            with open(path, "w") as f:
                yaml.safe_dump(data, f)

            # Load
            doc = load_from_yaml(path)

            assert doc.target == "https://example.com"
            assert doc.version == "1.0"
            assert isinstance(doc.created_at, datetime)

    def test_load_with_nested_data(self):
        """Test loading document with nested structures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            data = {
                "version": "1.0",
                "target": "https://example.com",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "attack_surfaces": [
                    {
                        "id": "surf-1",
                        "surface_type": "endpoint",
                        "url": "https://example.com/api",
                        "description": "Test",
                        "discovered_by": "recon",
                        "discovered_at": datetime.utcnow().isoformat(),
                    }
                ],
                "findings": [
                    {
                        "id": "find-1",
                        "title": "Test",
                        "severity": "high",
                        "status": "confirmed",
                        "description": "Test finding",
                        "evidence": "proof",
                        "discovered_by": "tester",
                        "discovered_at": datetime.utcnow().isoformat(),
                    }
                ],
            }

            with open(path, "w") as f:
                yaml.safe_dump(data, f)

            # Load
            doc = load_from_yaml(path)

            assert len(doc.attack_surfaces) == 1
            assert doc.attack_surfaces[0].id == "surf-1"
            assert len(doc.findings) == 1
            assert doc.findings[0].severity == Severity.HIGH

    def test_load_nonexistent_file_raises(self):
        """Test that loading nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_from_yaml("/nonexistent/file.yaml")

    def test_load_invalid_yaml_raises(self):
        """Test that invalid YAML raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            with open(path, "w") as f:
                f.write("invalid: yaml: content: [")

            with pytest.raises(yaml.YAMLError):
                load_from_yaml(path)

    def test_load_invalid_schema_raises(self):
        """Test that data not matching schema raises validation error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            # Missing required field
            data = {"version": "1.0"}  # Missing 'target'

            with open(path, "w") as f:
                yaml.safe_dump(data, f)

            with pytest.raises(Exception):  # Pydantic ValidationError
                load_from_yaml(path)


class TestRoundTrip:
    """Tests for save/load round-trip consistency."""

    def test_round_trip_preserves_data(self):
        """Test that save then load preserves all data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.yaml")

            # Create comprehensive document
            surface = AttackSurface(
                id="surf-1",
                surface_type="endpoint",
                url="https://example.com/api",
                description="Test endpoint",
                parameters=["param1", "param2"],
                technology_hints=["React"],
                priority="high",
                discovered_by="recon",
            )

            finding = Finding(
                id="find-1",
                title="XSS",
                severity=Severity.MEDIUM,
                status=FindingStatus.SUSPECTED,
                description="Possible XSS",
                evidence="User input reflected",
                reproduction_steps=["Step 1", "Step 2"],
                remediation="Sanitize input",
                discovered_by="tester",
            )

            recon = ReconSummary(
                total_endpoints=10,
                total_forms=3,
                technologies_detected=["React", "Express"],
            )

            original = FindingsDocumentSchema(
                target="https://example.com",
                recon_summary=recon,
                attack_surfaces=[surface],
                findings=[finding],
                agents_invoked=["recon", "tester"],
                total_steps_taken=42,
            )

            # Save and load
            save_to_yaml(original, path)
            loaded = load_from_yaml(path)

            # Verify data preserved
            assert loaded.target == original.target
            assert len(loaded.attack_surfaces) == 1
            assert loaded.attack_surfaces[0].id == "surf-1"
            assert loaded.attack_surfaces[0].parameters == ["param1", "param2"]
            assert len(loaded.findings) == 1
            assert loaded.findings[0].severity == Severity.MEDIUM
            assert loaded.findings[0].reproduction_steps == ["Step 1", "Step 2"]
            assert loaded.recon_summary.total_endpoints == 10
            assert loaded.agents_invoked == ["recon", "tester"]
            assert loaded.total_steps_taken == 42
