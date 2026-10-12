import fnmatch
import json
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

CONFIG_FILE = "config.json"

IGNORE_PATTERNS = [
    "node_modules",
    ".venv",
    "venv",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".DS_Store",
    "Thumbs.db",
    "*.log",
    "*.tmp",
    "*.temp",
    ".env",
    ".env.*",
]


def should_ignore(name: str) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in IGNORE_PATTERNS)


def list_projects() -> dict[str, Path]:
    """Every non-ignored subfolder of the projects directory is a reference project."""
    base = settings.projects_dir
    if not base.is_dir():
        return {}
    return {
        entry.name: entry.resolve()
        for entry in sorted(base.iterdir())
        if entry.is_dir() and not should_ignore(entry.name)
    }


def load_project_config() -> dict[str, dict[str, str]]:
    """
    Read the optional projects/config.json.
    Keys are project folder names; values hold "type" and "description".
    A missing or invalid file is ignored.
    """
    path = settings.projects_dir / CONFIG_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding=settings.encoding))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.warning(f"Ignoring {path}: {e}")
        return {}
    if not isinstance(data, dict):
        logger.warning(f"Ignoring {path}: top level must be a JSON object")
        return {}
    return {name: info for name, info in data.items() if isinstance(info, dict)}


def describe_projects() -> list[dict]:
    """Projects with their optional type and description from config.json."""
    metadata = load_project_config()
    described = []
    for name, path in list_projects().items():
        info = metadata.get(name, {})
        described.append({
            "name": name,
            "path": str(path),
            "type": str(info.get("type", "")),
            "description": str(info.get("description", "")),
        })
    return described


def get_project(project_name: str) -> Path:
    projects = list_projects()
    if project_name not in projects:
        raise ValueError(f"Project '{project_name}' not found. Available: {list(projects)}")
    return projects[project_name]


def resolve_path(project_name: str, relative_path: str = "") -> Path:
    root = get_project(project_name)
    relative_path = relative_path.strip()
    if relative_path in ("", "."):
        return root
    if Path(relative_path).is_absolute():
        raise ValueError("Absolute paths are not allowed")

    target = (root / relative_path).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Path traversal attempt detected")
    if any(should_ignore(part) for part in target.relative_to(root).parts):
        raise ValueError(f"Path is ignored: {relative_path}")
    if not target.exists():
        raise ValueError(f"Path does not exist: {relative_path}")
    return target


def count_entries(root: Path) -> tuple[int, int]:
    files = 0
    directories = 0
    for _, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not should_ignore(d)]
        directories += len(dirnames)
        files += sum(1 for f in filenames if not should_ignore(f))
    return files, directories
