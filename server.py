#!/usr/bin/env python3
"""
Production-ready MCP Server for serving multiple reference codebases over SSE.

This server exposes tools for browsing and reading files from configured reference projects
via a remote Server-Sent Events (SSE) connection using the Model Context Protocol (MCP).

Configuration Priority:
1. config.json (mounted at /app/config/config.json or ./config.json)
2. Environment variables (fallback)
3. Default values
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Awaitable, Callable

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent, ListToolsRequest, CallToolRequest, CallToolResult
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import Response
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class Config:
    """Server configuration loaded from config.json with environment variable fallback."""
    
    DEFAULT_CONFIG_PATHS = [
        Path("/app/config/config.json"),      # Docker mounted config
        Path("/app/projects/config.json"),    # Alternative mount point
        Path("./config.json"),                # Local development
        Path("../config.json"),               # From subdirectory
    ]
    
    def __init__(self):
        # Load config from file first
        file_config = self._load_config_file()
        
        # Server settings (file config -> env -> default)
        self.host = self._get_value(file_config, "server.host", "MCP_SERVER_HOST", "0.0.0.0")
        self.port = int(self._get_value(file_config, "server.port", "MCP_SERVER_PORT", "8000"))
        self.log_level = self._get_value(file_config, "server.log_level", "MCP_LOG_LEVEL", "INFO").upper()
        
        # Projects (from config file primarily)
        self.projects = self._parse_projects(file_config)
        
        # File access settings
        self.max_file_size = int(self._get_value(file_config, "file_access.max_file_size", "MCP_MAX_FILE_SIZE", "1048576"))
        self.encoding = self._get_value(file_config, "file_access.encoding", "MCP_FILE_ENCODING", "utf-8")
        
        # Ignore patterns
        self.ignore_patterns = self._parse_ignore_patterns(file_config)
        
        logger.setLevel(getattr(logging, self.log_level, logging.INFO))
        logger.info(f"Configuration loaded: {len(self.projects)} projects, host={self.host}, port={self.port}")
    
    def _load_config_file(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        for config_path in self.DEFAULT_CONFIG_PATHS:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    logger.info(f"Loaded configuration from {config_path}")
                    return config
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in {config_path}: {e}")
                except Exception as e:
                    logger.warning(f"Failed to load config from {config_path}: {e}")
        
        logger.info("No config file found, using environment variables and defaults")
        return {}
    
    def _get_value(self, file_config: Dict, key_path: str, env_var: str, default: str) -> str:
        """Get value from file config (nested key), then env var, then default."""
        # Try file config with dot notation (e.g., "server.host")
        keys = key_path.split('.')
        value = file_config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                value = None
                break
        
        if value is not None:
            return str(value)
        
        # Fallback to environment variable
        return os.getenv(env_var, default)
    
    def _parse_projects(self, file_config: Dict) -> Dict[str, Path]:
        """Parse project mappings from config file, then environment variable."""
        projects = {}
        
        # Try config file first
        projects_config = file_config.get("projects", {})
        if projects_config:
            for name, project_info in projects_config.items():
                if isinstance(project_info, dict):
                    path_str = project_info.get("path", "")
                else:
                    # Support legacy string format
                    path_str = str(project_info)
                
                if path_str:
                    path = Path(path_str).resolve()
                    if path.exists() and path.is_dir():
                        projects[name] = path
                        logger.info(f"Registered project from config: {name} -> {path}")
                    else:
                        logger.warning(f"Project path does not exist or is not a directory: {name} -> {path}")
        
        # Fallback to environment variable if no projects from config
        if not projects:
            projects_env = os.getenv("REFERENCE_PROJECTS", "")
            if projects_env:
                logger.info("No projects in config file, falling back to REFERENCE_PROJECTS env var")
                for pair in projects_env.split(","):
                    if "=" in pair:
                        key, path = pair.split("=", 1)
                        key = key.strip()
                        path = Path(path.strip()).resolve()
                        if path.exists() and path.is_dir():
                            projects[key] = path
                            logger.info(f"Registered project from env: {key} -> {path}")
                        else:
                            logger.warning(f"Project path does not exist or is not a directory: {key} -> {path}")
        
        if not projects:
            logger.warning("No valid projects configured. Check config.json or REFERENCE_PROJECTS environment variable.")
        
        return projects
    
    def _parse_ignore_patterns(self, file_config: Dict) -> List[str]:
        """Parse ignore patterns from config file, then environment variable."""
        # Try config file
        patterns = file_config.get("ignore_patterns")
        if patterns and isinstance(patterns, list):
            return [str(p) for p in patterns if p]
        
        # Fallback to environment variable
        patterns_env = os.getenv("MCP_IGNORE_PATTERNS", "")
        if patterns_env:
            return [p.strip() for p in patterns_env.split(",") if p.strip()]
        
        # Default ignore patterns
        return [
            "node_modules",
            "venv",
            ".venv",
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
            ".env.local",
            ".env.*.local",
        ]


config = Config()


# =============================================================================
# Security Utilities
# =============================================================================

class PathSecurityError(Exception):
    """Raised when a path validation fails."""
    pass


def validate_path(project_name: str, relative_path: str = "") -> Path:
    """
    Validate and resolve a path within a registered project.
    
    Prevents directory traversal attacks by ensuring the resolved path
    is within the project's base directory.
    
    Args:
        project_name: The registered project key
        relative_path: Relative path within the project
        
    Returns:
        Resolved absolute Path object
        
    Raises:
        PathSecurityError: If path is invalid or attempts traversal
    """
    if project_name not in config.projects:
        raise PathSecurityError(f"Project '{project_name}' not found. Available: {list(config.projects.keys())}")
    
    base_dir = config.projects[project_name]
    
    # Handle empty or root path
    if not relative_path or relative_path == ".":
        return base_dir
    
    # Normalize the relative path
    relative_path = relative_path.strip()
    
    # Prevent absolute paths
    if os.path.isabs(relative_path):
        raise PathSecurityError("Absolute paths are not allowed")
    
    # Resolve the target path
    try:
        target_path = (base_dir / relative_path).resolve()
    except Exception as e:
        raise PathSecurityError(f"Invalid path: {e}")
    
    # Security check: ensure target is within base directory
    try:
        # Use commonpath to verify target is under base_dir
        common = os.path.commonpath([str(base_dir), str(target_path)])
        if common != str(base_dir):
            raise PathSecurityError("Path traversal attempt detected")
    except ValueError:
        # Raised if paths are on different drives (Windows)
        raise PathSecurityError("Path traversal attempt detected")
    
    # Ensure the path exists
    if not target_path.exists():
        raise PathSecurityError(f"Path does not exist: {relative_path}")
    
    return target_path


def should_ignore(name: str) -> bool:
    """Check if a file/directory name matches any ignore pattern."""
    import fnmatch
    for pattern in config.ignore_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        # Also check against full path components
        if pattern in name:
            return True
    return False


# =============================================================================
# Tool Implementations
# =============================================================================

async def list_reference_projects() -> List[TextContent]:
    """
    List all registered reference projects with their configurations.
    
    Returns:
        Text summary of all projects
    """
    if not config.projects:
        return [TextContent(
            type="text",
            text="No reference projects configured. Check config.json or REFERENCE_PROJECTS environment variable."
        )]
    
    lines = ["Registered Reference Projects:", "=" * 50, ""]
    
    for name, path in config.projects.items():
        # Count files and directories
        try:
            file_count = sum(1 for _ in path.rglob("*") if _.is_file() and not should_ignore(_.name))
            dir_count = sum(1 for _ in path.rglob("*") if _.is_dir() and not should_ignore(_.name))
        except Exception:
            file_count = 0
            dir_count = 0
        
        lines.append(f"Project: {name}")
        lines.append(f"  Path: {path}")
        lines.append(f"  Files: {file_count}, Directories: {dir_count}")
        lines.append("")
    
    return [TextContent(type="text", text="\n".join(lines))]


async def browse_reference_directory(project_name: str, relative_path: str = "") -> List[TextContent]:
    """
    Browse a directory in a reference project.
    
    Args:
        project_name: The registered project key
        relative_path: Relative path within the project (optional, defaults to root)
        
    Returns:
        Structured listing of files and directories
    """
    try:
        target_path = validate_path(project_name, relative_path)
    except PathSecurityError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    
    if not target_path.is_dir():
        return [TextContent(type="text", text=f"Error: '{relative_path}' is not a directory")]
    
    entries = []
    try:
        for entry in sorted(target_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if should_ignore(entry.name):
                continue
            
            rel_entry = entry.relative_to(config.projects[project_name])
            if entry.is_dir():
                entries.append(f"📁 {rel_entry}/")
            else:
                try:
                    size = entry.stat().st_size
                    size_str = _format_size(size)
                    entries.append(f"📄 {rel_entry} ({size_str})")
                except Exception:
                    entries.append(f"📄 {rel_entry}")
    except PermissionError:
        return [TextContent(type="text", text=f"Error: Permission denied accessing '{relative_path}'")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error browsing directory: {e}")]
    
    if not entries:
        display_path = relative_path if relative_path else "."
        return [TextContent(type="text", text=f"Directory '{display_path}' is empty (or all entries are ignored)")]
    
    display_path = relative_path if relative_path else "."
    header = f"Contents of '{project_name}:{display_path}':"
    return [TextContent(type="text", text=header + "\n" + "\n".join(entries))]


async def get_reference_file(project_name: str, relative_path: str) -> List[TextContent]:
    """
    Read a file from a reference project.
    
    Args:
        project_name: The registered project key
        relative_path: Relative path to the file within the project
        
    Returns:
        File content wrapped in text blocks
    """
    try:
        target_path = validate_path(project_name, relative_path)
    except PathSecurityError as e:
        return [TextContent(type="text", text=f"Error: {e}")]
    
    if not target_path.is_file():
        return [TextContent(type="text", text=f"Error: '{relative_path}' is not a file")]
    
    # Check file size
    try:
        file_size = target_path.stat().st_size
        if file_size > config.max_file_size:
            return [TextContent(
                type="text",
                text=f"Error: File size ({_format_size(file_size)}) exceeds maximum allowed ({_format_size(config.max_file_size)})"
            )]
    except Exception:
        pass
    
    try:
        content = target_path.read_text(encoding=config.encoding)
    except UnicodeDecodeError:
        return [TextContent(
            type="text",
            text=f"Error: File '{relative_path}' is not valid {config.encoding} encoded text"
        )]
    except PermissionError:
        return [TextContent(type="text", text=f"Error: Permission denied reading '{relative_path}'")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error reading file: {e}")]
    
    # Return with file info header
    header = f"File: {project_name}:{relative_path} ({_format_size(file_size)})"
    return [TextContent(type="text", text=f"{header}\n{'=' * len(header)}\n{content}")]


def _format_size(size: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# =============================================================================
# MCP Server Setup (New API)
# =============================================================================

# Create the MCP server
server = Server("reference-code-server")

# Define available tools
TOOLS = [
    Tool(
        name="list_reference_projects",
        description="List all registered reference projects with their paths and statistics",
        inputSchema={
            "type": "object",
            "properties": {},
            "additionalProperties": False
        }
    ),
    Tool(
        name="browse_reference_directory",
        description="Browse a directory in a reference project, listing files and subdirectories",
        inputSchema={
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the registered project (e.g., 'frontend', 'backend')"
                },
                "relative_path": {
                    "type": "string",
                    "description": "Relative path within the project (optional, defaults to root)",
                    "default": ""
                }
            },
            "required": ["project_name"],
            "additionalProperties": False
        }
    ),
    Tool(
        name="get_reference_file",
        description="Read the full content of a file from a reference project",
        inputSchema={
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "Name of the registered project (e.g., 'frontend', 'backend')"
                },
                "relative_path": {
                    "type": "string",
                    "description": "Relative path to the file within the project"
                }
            },
            "required": ["project_name", "relative_path"],
            "additionalProperties": False
        }
    )
]


async def handle_list_tools(request: ListToolsRequest) -> List[Tool]:
    """Handle tools/list request."""
    return TOOLS


async def handle_call_tool(request: CallToolRequest) -> CallToolResult:
    """Handle tools/call request."""
    name = request.params.name
    arguments = request.params.arguments or {}
    
    try:
        if name == "list_reference_projects":
            result = await list_reference_projects()
        elif name == "browse_reference_directory":
            project_name = arguments.get("project_name", "")
            relative_path = arguments.get("relative_path", "")
            result = await browse_reference_directory(project_name, relative_path)
        elif name == "get_reference_file":
            project_name = arguments.get("project_name", "")
            relative_path = arguments.get("relative_path", "")
            result = await get_reference_file(project_name, relative_path)
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown tool: {name}")],
                is_error=True
            )
        
        return CallToolResult(content=result, is_error=False)
    except Exception as e:
        logger.error(f"Error calling tool {name}: {e}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")],
            is_error=True
        )


# Register handlers using the new API (not decorators)
server.add_request_handler("tools/list", ListToolsRequest, handle_list_tools)
server.add_request_handler("tools/call", CallToolRequest, handle_call_tool)


# =============================================================================
# Starlette Application (SSE Transport)
# =============================================================================

sse = SseServerTransport("/messages/")


async def handle_sse(request):
    """Handle SSE connections."""
    async with sse.connect_sse(
        request.scope,
        request.receive,
        request._send
    ) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


async def handle_messages(request):
    """Handle message posting."""
    await sse.handle_post_message(
        request.scope,
        request.receive,
        request._send
    )


# Create Starlette app with routes
app = Starlette(
    routes=[
        Route("/sse", handle_sse, methods=["GET"]),
        Route("/messages/", handle_messages, methods=["POST"]),
        Mount("/messages/", sse.handle_post_message),
    ]
)


# Health check endpoint
async def health_check(request):
    return Response(
        content=json.dumps({
            "status": "healthy",
            "projects": list(config.projects.keys()),
            "version": "1.1.0"
        }),
        media_type="application/json"
    )

app.router.routes.append(Route("/health", health_check, methods=["GET"]))


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    """Run the server."""
    logger.info(f"Starting MCP Reference Code Server on {config.host}:{config.port}")
    logger.info(f"Registered projects: {list(config.projects.keys())}")
    
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        access_log=True
    )


if __name__ == "__main__":
    main()