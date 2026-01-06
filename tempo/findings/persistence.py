"""
YAML persistence utilities for findings documents.

Provides safe YAML serialization and deserialization for FindingsDocumentSchema
with proper datetime handling and validation.
"""

from datetime import datetime
from pathlib import Path

import yaml

from tempo.findings.schema import FindingsDocumentSchema


def _datetime_representer(dumper: yaml.Dumper, data: datetime) -> yaml.Node:
    """Custom YAML representer for datetime objects."""
    return dumper.represent_scalar("tag:yaml.org,2002:timestamp", data.isoformat())


def _datetime_constructor(loader: yaml.Loader, node: yaml.Node) -> datetime:
    """Custom YAML constructor for datetime objects."""
    value = loader.construct_scalar(node)
    # Handle ISO format strings
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


# Register custom datetime handlers
yaml.add_representer(datetime, _datetime_representer)
yaml.add_constructor("tag:yaml.org,2002:timestamp", _datetime_constructor)


def save_to_yaml(document: FindingsDocumentSchema, path: str) -> None:
    """
    Save a findings document to a YAML file.

    Args:
        document: The FindingsDocumentSchema instance to save
        path: Path to the YAML file

    Raises:
        IOError: If the file cannot be written
        ValueError: If the document is invalid
    """
    # Ensure parent directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict for YAML serialization
    # Use model_dump instead of dict() for better control
    data = document.model_dump(mode="json")

    # Convert ISO string datetimes back to datetime objects for proper YAML formatting
    def convert_datetimes(obj):
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key.endswith("_at") and isinstance(value, str):
                    try:
                        result[key] = datetime.fromisoformat(value)
                    except (ValueError, TypeError):
                        result[key] = value
                else:
                    result[key] = convert_datetimes(value)
            return result
        elif isinstance(obj, list):
            return [convert_datetimes(item) for item in obj]
        else:
            return obj

    data = convert_datetimes(data)

    # Write to YAML with safe dumper
    with open(path, "w") as f:
        yaml.safe_dump(
            data,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def load_from_yaml(path: str) -> FindingsDocumentSchema:
    """
    Load a findings document from a YAML file.

    Args:
        path: Path to the YAML file

    Returns:
        Validated FindingsDocumentSchema instance

    Raises:
        FileNotFoundError: If the file does not exist
        yaml.YAMLError: If the file is not valid YAML
        pydantic.ValidationError: If the document doesn't match schema
    """
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    # Validate and construct the document
    return FindingsDocumentSchema.model_validate(data)
