# MCP Reference Code Server

A production-ready Model Context Protocol (MCP) server that serves multiple reference codebases to LLM clients over a remote Server-Sent Events (SSE) connection.

## Features

- **Multi-Project Support**: Serve multiple codebases (frontend, backend, shared libraries) from a single server
- **Config-Driven**: Define projects in `config.json` - no code changes needed
- **Hot Reload**: Edit `config.json` and restart container (no rebuild required)
- **Security First**: Strict path validation prevents directory traversal attacks
- **Remote Access**: SSE transport for connecting LLMs over network
- **Production Ready**: Docker support, health checks, non-root user, structured logging
- **Multi-Arch**: Built for `linux/amd64` and `linux/arm64`

## Quick Start

### Docker (Recommended)

```bash
# 1. Clone and configure
git clone <this-repo>
cd code-mcp

# 2. Edit config.json with your project paths (container paths)
#    Example uses /app/projects/<name>

# 3. Place your codebases in ./projects/
mkdir -p projects/frontend projects/backend projects/shared
# cp -r /path/to/your/frontend/* projects/frontend/
# cp -r /path/to/your/backend/* projects/backend/
# cp -r /path/to/your/shared/* projects/shared/

# 4. Start server
docker compose up -d

# 5. Verify
curl http://localhost:8000/health
```

### Local Development

```bash
# 1. Create virtual environment
python -m venv venv && source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Edit config.json with absolute host paths
#    Example: "path": "/home/user/code-mcp/projects/frontend"

# 4. Run server
python server.py
```

## Configuration

### config.json (Primary)

```json
{
  "projects": {
    "frontend": {
      "path": "/app/projects/frontend",
      "description": "Frontend application"
    },
    "backend": {
      "path": "/app/projects/backend",
      "description": "Backend API"
    },
    "shared": {
      "path": "/app/projects/shared",
      "description": "Shared libraries"
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
    "node_modules", ".git", "dist", "__pycache__", "*.pyc", ".env"
  ]
}
```

### Key Points

| Setting | Description |
|---------|-------------|
| `projects.<name>.path` | **Absolute path inside container** (must match volume mount) |
| `server.host/port` | Bind address and port |
| `file_access.max_file_size` | Max file size to read (bytes) |
| `ignore_patterns` | fnmatch patterns to exclude when browsing |

### Updating Projects (No Rebuild)

```bash
# Edit config.json on host
vim config.json

# Restart container only
docker compose restart
```

## Available Tools

| Tool | Description |
|------|-------------|
| `list_reference_projects` | List all registered projects with stats |
| `browse_reference_directory` | Browse directory tree with file sizes |
| `get_reference_file` | Read full file content with metadata |

## Client Configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "reference-code": {
      "transport": "sse",
      "url": "http://localhost:8000/sse"
    }
  }
}
```

### VS Code

```json
{
  "mcp": {
    "servers": {
      "reference-code": {
        "type": "sse",
        "url": "http://localhost:8000/sse"
      }
    }
  }
}
```

### Generic MCP Client

```python
from mcp.client.sse import sse_client

async with sse_client("http://localhost:8000/sse") as (read, write):
    # Use the client
    pass
```

## Docker Compose

```yaml
services:
  mcp-reference-server:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./projects/frontend:/app/projects/frontend:ro
      - ./projects/backend:/app/projects/backend:ro
      - ./projects/shared:/app/projects/shared:ro
      - ./config.json:/app/config/config.json:ro
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
```

## Security

- Path traversal prevented via `os.path.commonpath` validation
- Absolute paths rejected
- Symlinks resolved before validation
- File size limits enforced
- Runs as non-root user in container

## CI/CD

Automated builds on push to main/tags via GitHub Actions:
- Multi-platform images (`amd64`, `arm64`) pushed to `ghcr.io/tech-thinker/code-mcp`
- Health checks run on every build
- Releases created from git tags

## Project Structure

```
code-mcp/
├── server.py              # Main MCP server
├── config.json            # Project configuration
├── requirements.txt       # Python dependencies
├── Dockerfile             # Multi-stage build
├── docker-compose.yaml    # Local orchestration
├── .github/workflows/     # CI/CD pipelines
├── projects/              # Codebase mount points
│   ├── frontend/
│   ├── backend/
│   └── shared/
└── AGENTS.md              # Agent knowledge base
```

## License

MIT