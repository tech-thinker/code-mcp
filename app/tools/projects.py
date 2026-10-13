import fnmatch
import subprocess
from pathlib import Path
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


@mcp.tool()
def search_reference_project(
    project_name: str,
    query: str,
    search_type: str = "both",
    max_results: int = 50,
) -> dict:
    """
    Search inside a reference project.

    Args:
        project_name: Name of the project folder (e.g. 'frontend').
        query: Search query string. For 'files' type, supports wildcards (*, ?).
               For 'content' type, searches file contents.
        search_type: What to search - 'files' (filenames), 'content' (file contents), or 'both' (default: "both").
        max_results: Maximum number of results to return (default: 50).

    Returns:
        dict: Search results with matches.
    """
    if search_type not in ("files", "content", "both"):
        raise ValueError(f"Invalid search_type: {search_type}. Must be 'files', 'content', or 'both'")

    root = projects.get_project(project_name)

    # Collect all files in the project (excluding ignored)
    all_files = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        try:
            rel = file_path.relative_to(root)
            if any(projects.should_ignore(part) for part in rel.parts):
                continue
            all_files.append(file_path)
        except ValueError:
            continue

    matches = []

    if search_type in ("files", "both"):
        # File name pattern matching using fnmatch (supports *, ?, [])
        file_matches = []
        for file_path in all_files:
            rel = file_path.relative_to(root)
            # Match against basename and relative path
            if fnmatch.fnmatch(rel.name, query) or fnmatch.fnmatch(rel.as_posix(), query):
                file_matches.append(file_path)

        # For "both" type, we'll combine with content matches later
        if search_type == "files":
            matches = file_matches[:max_results]
        else:
            # For "both", collect file matches to combine with content matches
            matches = file_matches

    if search_type in ("content", "both"):
        # Search file contents using grep
        try:
            grep_result = subprocess.run(
                ["grep", "-r", "-l", "--", query, str(root)],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("Content search timed out")

        content_files = []
        if grep_result.stdout.strip():
            for f in grep_result.stdout.strip().split("\n"):
                try:
                    file_path = Path(f)
                    rel = file_path.relative_to(root)
                    if not any(projects.should_ignore(part) for part in rel.parts):
                        content_files.append(file_path)
                except ValueError:
                    continue

        if search_type == "content":
            matches = content_files[:max_results]
        else:
            # Combine file and content matches (union, preserving order)
            seen = set()
            combined = []
            for f in matches + content_files:
                key = f.as_posix()
                if key not in seen:
                    seen.add(key)
                    combined.append(f)
            matches = combined[:max_results]

    if not matches:
        return {
            "project": project_name,
            "query": query,
            "search_type": search_type,
            "matches": [],
            "total": 0,
        }

    # Limit results
    matches = matches[:max_results]

    # Convert to relative paths and add metadata
    formatted_matches = []
    for match in matches:
        try:
            rel_path = match.relative_to(root)
            stat = match.stat()
            formatted_matches.append({
                "path": rel_path.as_posix(),
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
        except (ValueError, OSError):
            continue

    return {
        "project": project_name,
        "query": query,
        "search_type": search_type,
        "matches": formatted_matches,
        "total": len(formatted_matches),
    }
