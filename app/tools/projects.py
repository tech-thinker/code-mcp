from app import projects
from app.config import settings
from app.server import mcp


@mcp.tool()
def list_reference_projects() -> dict:
    """
    List all reference projects served by this server.

    Returns:
        dict: Each project's name, type, description, path, and file/directory counts.
    """
    result = []
    for project in projects.describe_projects():
        files, directories = projects.count_entries(projects.get_project(project["name"]))
        result.append({**project, "files": files, "directories": directories})
    return {"projects": result}


@mcp.tool()
def browse_reference_directory(project_name: str, relative_path: str = "") -> dict:
    """
    Browse a directory inside a reference project.

    Args:
        project_name: Name of the project folder (e.g. 'frontend').
        relative_path: Path inside the project. Empty means the project root.

    Returns:
        dict: Directory entries, directories first.
    """
    root = projects.get_project(project_name)
    target = projects.resolve_path(project_name, relative_path)
    if not target.is_dir():
        raise ValueError(f"'{relative_path}' is not a directory")

    entries = []
    for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
        if projects.should_ignore(entry.name):
            continue
        is_dir = entry.is_dir()
        entries.append({
            "name": entry.name,
            "path": entry.relative_to(root).as_posix(),
            "type": "directory" if is_dir else "file",
            "size": None if is_dir else entry.stat().st_size,
        })

    return {"project": project_name, "path": relative_path or ".", "entries": entries}


@mcp.tool()
def get_reference_file(project_name: str, relative_path: str) -> dict:
    """
    Read the full text content of a file inside a reference project.

    Args:
        project_name: Name of the project folder (e.g. 'backend').
        relative_path: Path to the file inside the project.

    Returns:
        dict: File path, size in bytes, and text content.
    """
    target = projects.resolve_path(project_name, relative_path)
    if not target.is_file():
        raise ValueError(f"'{relative_path}' is not a file")

    size = target.stat().st_size
    if size > settings.max_file_size:
        raise ValueError(f"File size ({size} bytes) exceeds maximum allowed ({settings.max_file_size} bytes)")

    try:
        content = target.read_text(encoding=settings.encoding)
    except UnicodeDecodeError:
        raise ValueError(f"'{relative_path}' is not valid {settings.encoding} text")

    return {"project": project_name, "path": relative_path, "size": size, "content": content}
