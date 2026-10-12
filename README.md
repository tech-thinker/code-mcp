# MCP Reference Code Server

An MCP server that serves reference codebases to LLM clients. Every folder inside `projects/` is one reference project, and its folder name is the project name.

## Project Layout

```
projects/
├── frontend/   -> project "frontend"
├── backend/    -> project "backend"
└── shared/     -> project "shared"
```

Add or remove a codebase by adding or removing a folder. Files placed directly in `projects/` are ignored.

### Optional `projects/config.json`

To help AI agents understand each project, add `projects/config.json`. Keys are project folder names:

```json
{
  "frontend": {
    "type": "frontend",
    "description": "React dashboard for the admin panel"
  },
  "backend": {
    "type": "backend",
    "description": "FastAPI service with auth and billing"
  }
}
```

- `type` and `description` are shown in the server instructions and in `list_reference_projects`.
- Projects without an entry work as normal with empty values.
- If the file is missing or invalid JSON, it is ignored and the server still runs.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| APP_NAME | Server name | code-mcp |
| PROTOCOL | Transport (`http`, `sse`, `stdio`) | http |
| PORT | Port to run the server on | 8000 |
| PROJECTS_DIR | Folder whose subfolders are the projects | projects |
| MAX_FILE_SIZE | Max bytes returned by `get_reference_file` | 1048576 |
| ENCODING | Text encoding used to read files | utf-8 |

Copy `.env.example` to `.env` to override them.

## Tools

| Tool | Description |
|------|-------------|
| `list_reference_projects` | List all projects with their paths and file/directory counts |
| `browse_reference_directory` | List the entries of a directory inside a project |
| `get_reference_file` | Read the full text content of a file inside a project |

Ignored names (for example `node_modules`, `.git`, `.env`, `__pycache__`) are hidden from browsing and cannot be read.

## Local Development

```bash
# 1. Put codebases in ./projects
mkdir -p projects/frontend projects/backend
# cp -r /path/to/frontend/* projects/frontend/

# 2. Run
just run        # or: make run  /  uv run main.py

# 3. Test
just test       # or: make test
```

Health check: `curl http://localhost:8000/health`

## Docker

```bash
docker compose up -d --build
docker compose logs -f
curl http://localhost:8000/health
```

`./projects` is mounted read-only at `/app/projects`. To change the projects, edit the folders on the host and restart the container with `docker compose restart`. No rebuild is needed.

## Client Configuration

```json
{
  "mcpServers": {
    "code-mcp": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

## Security

- Path traversal is blocked by resolving the target path and checking it stays inside the project folder
- Absolute paths are rejected
- Symlinks are resolved before the check
- Ignored names are blocked
- File size limit is enforced
- The projects volume is mounted read-only
