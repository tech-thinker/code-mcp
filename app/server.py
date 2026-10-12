from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.projects import describe_projects


def build_instructions() -> str:
    projects = describe_projects()
    if not projects:
        return "No reference projects are available."
    lines = ["Reference projects served by this server:"]
    for project in projects:
        details = " - ".join(part for part in (project["type"], project["description"]) if part)
        lines.append(f"- {project['name']}" + (f": {details}" if details else ""))
    return "\n".join(lines)


mcp = FastMCP(
    name=settings.app_name,
    instructions=build_instructions(),
)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "projects": [p["name"] for p in describe_projects()]})
