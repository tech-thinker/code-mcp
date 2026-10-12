# MCP Reference Code Server - Agent Knowledge Base

## Project Overview

This is a production-ready Model Context Protocol (MCP) server that serves multiple reference codebases to LLM clients over a remote Server-Sent Events (SSE) connection. The server allows AI assistants to browse and read files from configured projects securely.

### Key Features

- **Multi-Project Support**: Configure multiple codebases via `config.json` (mounted at `/app/config/config.json`)
- **Remote SSE Transport**: Uses `mcp.server.sse.SseServerTransport` with Starlette + uvicorn for remote hosting
- **Security First**: Strict path validation prevents directory traversal attacks
- **Production Ready**: Docker support, health checks, non-root user, structured logging
- **Hot-Reload Config**: Edit `config.json` and restart container to change projects (no rebuild needed)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Client (LLM)                         │
└─────────────────────────────┬───────────────────────────────────┘
                              │ SSE Connection
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Starlette + Uvicorn                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              SseServerTransport (/sse, /messages/)      │   │
│  └─────────────────────────────┬───────────────────────────┘   │
│                                │                                │
│  ┌─────────────────────────────▼───────────────────────────┐   │
│  │                    MCP Server                            │   │
│  │  ┌─────────────┐  ┌─────────────────┐  ┌─────────────┐  │   │
│  │  │ list_projects│  │ browse_directory│  │ get_file    │  │   │
│  │  └─────────────┘  └─────────────────┘  └─────────────┘  │   │
│  └─────────────────────────────┬───────────────────────────┘   │
│                                │                                │
│  ┌─────────────────────────────▼───────────────────────────┐   │
│  │              Path Security Layer                         │   │
│  │  • validate_path() - prevents traversal                  │   │
│  │  • should_ignore() - filters unwanted files              │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
            /app/projects/frontend    /app/projects/backend
            /app/projects/shared      (mounted volumes)
```

---

## Configuration

### Configuration Priority

The server loads configuration in this order (highest priority first):

1. **`config.json`** (mounted at `/app/config/config.json` or `./config.json`)
2. **Environment variables** (fallback)
3. **Built-in defaults**

### Config File Schema (`config.json`)

```json
{
  "projects": {
    "frontend": {
      "path": "/app/projects/frontend",
      "description": "Frontend application (React/Vue/Svelte)"
    },
    "backend": {
      "path": "/app/projects/backend",
      "description": "Backend API (FastAPI/Express/Go)"
    },
    "shared": {
      "path": "/app/projects/shared",
      "description": "Shared libraries and types"
    }
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8000,
    "log_level": "INFO"
  },
  "file_access": {
    "max_file_size": 1048576,
    "encoding": "utf-8"
  },
  "ignore_patterns": [
    "node_modules",
    ".git",
    "dist",
    "__pycache__",
    "*.pyc",
    ".env"
  ]
}
```

### Project Configuration

Each project in the `projects` object requires:
- **`path`**: Absolute path inside the container (must exist and be a directory)
- **`description`** (optional): Human-readable description

### Server Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `server.host` | `0.0.0.0` | Server bind address |
| `server.port` | `8000` | Server port |
| `server.log_level` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### File Access Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `file_access.max_file_size` | `1048576` | Max file size in bytes (1MB) |
| `file_access.encoding` | `utf-8` | Text file encoding |

### Ignore Patterns

Array of fnmatch patterns to exclude when browsing directories. Default includes:
```
node_modules, .venv, venv, .git, dist, build, __pycache__,
.pytest_cache, .mypy_cache, .tox, *.pyc, *.pyo, *.pyd,
.DS_Store, Thumbs.db, *.log, *.tmp, *.temp,
.env, .env.local, .env.*.local
```

### Environment Variable Fallback

If no `config.json` is found, these environment variables are used:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_HOST` | `0.0.0.0` | Server bind address |
| `MCP_SERVER_PORT` | `8000` | Server port |
| `MCP_LOG_LEVEL` | `INFO` | Logging level |
| `REFERENCE_PROJECTS` | *(required)* | Comma-separated `key=path` pairs |
| `MCP_MAX_FILE_SIZE` | `1048576` | Max file size in bytes |
| `MCP_FILE_ENCODING` | `utf-8` | Text file encoding |
| `MCP_IGNORE_PATTERNS` | *(built-in)* | Comma-separated ignore patterns |

---

## Available Tools

### 1. `list_reference_projects`

Lists all registered projects with their paths and basic statistics.

**Input**: None

**Output**: Text summary of all projects

```json
{
  "name": "list_reference_projects",
  "arguments": {}
}
```

**Example Response**:
```
Registered Reference Projects:
==================================================

Project: frontend
  Path: /app/projects/frontend
  Files: 142, Directories: 23

Project: backend
  Path: /app/projects/backend
  Files: 87, Directories: 15

Project: shared
  Path: /app/projects/shared
  Files: 31, Directories: 5
```

---

### 2. `browse_reference_directory`

Lists files and directories in a project path.

**Input**:
```json
{
  "project_name": "frontend",      // Required: registered project key
  "relative_path": "src/components" // Optional: defaults to root
}
```

**Output**: Structured directory listing with file sizes

**Example Response**:
```
Contents of 'frontend:src/components':
📁 Button/
📄 Button/index.tsx (2.1 KB)
📄 Button/Button.tsx (3.4 KB)
📄 Button/styles.css (1.2 KB)
📁 Modal/
📄 Modal/Modal.tsx (5.6 KB)
```

---

### 3. `get_reference_file`

Reads the full content of a file.

**Input**:
```json
{
  "project_name": "backend",
  "relative_path": "src/api/routes.py"
}
```

**Output**: File content with metadata header

**Example Response**:
```
File: backend:src/api/routes.py (4.2 KB)
========================================
from fastapi import APIRouter
from . import users, items

router = APIRouter()
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(items.router, prefix="/items", tags=["items"])
```

---

## Security Model

### Path Validation

The `validate_path()` function implements defense-in-depth:

1. **Project Existence Check**: Verifies project is registered
2. **Absolute Path Rejection**: Blocks absolute paths in `relative_path`
3. **Path Resolution**: Uses `Path.resolve()` to normalize
4. **Commonpath Verification**: Ensures resolved path is within project root using `os.path.commonpath()`
5. **Existence Check**: Confirms target exists

### Attack Vectors Mitigated

| Attack | Mitigation |
|--------|------------|
| `../../../etc/passwd` | `commonpath` check fails |
| Absolute paths `/etc/passwd` | Rejected early |
| Symlink traversal | `resolve()` follows symlinks, then `commonpath` validates |
| Different drive (Windows) | `ValueError` caught, treated as traversal |
| Null bytes | Python 3 `Path` handles safely |

---

## Deployment

### Local Development

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create project directories
mkdir -p projects/frontend projects/backend projects/shared

# 4. Copy your codebases to the project directories
cp -r /path/to/your/frontend/* projects/frontend/
cp -r /path/to/your/backend/* projects/backend/
cp -r /path/to/your/shared/* projects/shared/

# 5. Edit config.json with your project paths (use absolute paths)
#    Example: "path": "/home/user/code-mcp/projects/frontend"

# 6. Run server
python server.py
```

### Docker Deployment

```bash
# 1. Edit config.json to define your projects
#    Paths should be /app/projects/<project-name> (container paths)

# 2. Place your codebases in ./projects/ subdirectories
#    mkdir -p projects/frontend projects/backend projects/shared

# 3. Build and start
docker-compose up -d --build

# 4. View logs
docker-compose logs -f

# 5. To update projects: edit config.json, then restart (no rebuild needed!)
docker-compose restart

# 6. Stop
docker-compose down
```

### Updating Projects Without Rebuild

Since config is loaded from a mounted `config.json`:

1. Edit `config.json` on host
2. Run `docker-compose restart`
3. New projects are loaded immediately

### Production Considerations

1. **Reverse Proxy**: Use nginx/Traefik for TLS termination
2. **Authentication**: Add API key or OAuth at proxy layer
3. **Rate Limiting**: Implement at proxy or application level
4. **Monitoring**: Health endpoint at `/health`
5. **Resource Limits**: Configure Docker memory/CPU limits

---

## Client Configuration

### Claude Desktop (claude_desktop_config.json)

```json
{
  "mcpServers": {
    "reference-code": {
      "transport": "sse",
      "url": "http://your-server:8000/sse"
    }
  }
}
```

### VS Code (settings.json)

```json
{
  "mcp": {
    "servers": {
      "reference-code": {
        "type": "sse",
        "url": "http://your-server:8000/sse"
      }
    }
  }
}
```

### Generic MCP Client

```python
from mcp.client.sse import sse_client

async with sse_client("http://your-server:8000/sse") as (read, write):
    # Use the client
    pass
```

---

## Testing

### Manual Testing

```bash
# Health check
curl http://localhost:8000/health

# List projects (requires MCP protocol)
# Use an MCP client or the inspector
npx @modelcontextprotocol/inspector http://localhost:8000/sse
```

### Tool Testing via Inspector

1. Run inspector: `npx @modelcontextprotocol/inspector http://localhost:8000/sse`
2. Click "List Tools" to see available tools
3. Click "Call Tool" to test each tool

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "No reference projects configured" | config.json missing or invalid | Check config.json syntax and paths |
| "Project 'X' not found" | Typo in project name | Use exact key from `list_reference_projects` |
| "Path traversal attempt detected" | Relative path escapes project root | Use paths relative to project root only |
| "File size exceeds maximum" | File > 1MB | Increase `file_access.max_file_size` in config.json |
| "Permission denied" | Docker volume mount issues | Check volume permissions, use `:ro` for read-only |
| "Project path does not exist" | Path in config.json doesn't match mount | Ensure container path matches volume mount |

### Debug Mode

```bash
# Run with debug logging
MCP_LOG_LEVEL=DEBUG python server.py

# Docker with debug
docker-compose run -e MCP_LOG_LEVEL=DEBUG mcp-reference-server

# Check loaded config
docker-compose exec mcp-reference-server cat /app/config/config.json
```

---

## Extending the Server

### Adding New Tools

1. Add tool definition in `list_tools()`
2. Implement handler function
3. Add case in `call_tool()`

```python
# Example: Search tool
Tool(
    name="search_reference_files",
    description="Search for files matching a pattern",
    inputSchema={
        "type": "object",
        "properties": {
            "project_name": {"type": "string"},
            "pattern": {"type": "string"},
            "max_results": {"type": "integer", "default": 50}
        },
        "required": ["project_name", "pattern"]
    }
)
```

### Custom Ignore Patterns

Add to `config.json`:
```json
{
  "ignore_patterns": ["node_modules", ".git", "dist", "*.test.ts", "*.spec.ts", "coverage"]
}
```

Or via environment variable:
```bash
MCP_IGNORE_PATTERNS=node_modules,.git,dist,*.test.ts,*.spec.ts,coverage
```

---

## File Structure

```
code-mcp/
├── server.py              # Main MCP server implementation
├── requirements.txt       # Python dependencies
├── Dockerfile            # Multi-stage Docker build
├── docker-compose.yaml   # Docker Compose configuration
├── config.json           # Main configuration file (mounted to /app/config/)
├── .env.example          # Environment variable template
├── AGENTS.md             # This file - agent knowledge base
├── projects/             # Mount point for reference codebases
│   ├── frontend/         # Frontend codebase (mount here)
│   ├── backend/          # Backend codebase (mount here)
│   └── shared/           # Shared libraries (mount here)
└── venv/                 # Virtual environment (local dev)
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-10-12 | Initial release with 3 tools, SSE transport, Docker support |
| 1.1.0 | 2026-10-12 | Added config.json support, hot-reload via container restart |

---

## License

MIT License - Feel free to use and modify for your projects.