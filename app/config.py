from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "code-mcp"
    protocol: str = "http"
    port: int = 8000
    projects_dir: Path = Path("projects")
    max_file_size: int = 1048576
    encoding: str = "utf-8"


settings = Settings()
