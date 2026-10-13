import pytest

from app import projects
from app.config import settings
from app.tools.projects import search_reference_project


@pytest.fixture
def projects_dir(tmp_path, monkeypatch):
    base = tmp_path / "projects"
    (base / "frontend" / "src").mkdir(parents=True)
    (base / "frontend" / "src" / "app.ts").write_text("export const a = 1\n")
    (base / "backend" / "node_modules").mkdir(parents=True)
    (base / "backend" / "main.py").write_text("print(1)\n")
    (base / "README.md").write_text("not a project\n")
    monkeypatch.setattr(settings, "projects_dir", base)
    return base


def test_each_subfolder_is_a_project(projects_dir):
    assert set(projects.list_projects()) == {"frontend", "backend"}


def test_files_at_root_are_not_projects(projects_dir):
    assert "README.md" not in projects.list_projects()


def test_resolve_inside_project(projects_dir):
    target = projects.resolve_path("frontend", "src/app.ts")
    assert target.name == "app.ts"


def test_empty_path_is_project_root(projects_dir):
    assert projects.resolve_path("frontend", "") == projects.get_project("frontend")


def test_traversal_is_rejected(projects_dir):
    with pytest.raises(ValueError, match="traversal"):
        projects.resolve_path("frontend", "../backend/main.py")


def test_absolute_path_is_rejected(projects_dir):
    with pytest.raises(ValueError, match="Absolute"):
        projects.resolve_path("frontend", "/etc/passwd")


def test_unknown_project_is_rejected(projects_dir):
    with pytest.raises(ValueError, match="not found"):
        projects.resolve_path("missing", "x")


def test_missing_config_is_ignored(projects_dir):
    described = {p["name"]: p for p in projects.describe_projects()}
    assert described["frontend"]["type"] == ""
    assert described["frontend"]["description"] == ""


def test_config_adds_type_and_description(projects_dir):
    (projects_dir / "config.json").write_text(
        '{"frontend": {"type": "frontend", "description": "React app"}}'
    )
    described = {p["name"]: p for p in projects.describe_projects()}
    assert described["frontend"]["type"] == "frontend"
    assert described["frontend"]["description"] == "React app"
    assert described["backend"]["type"] == ""


def test_config_is_not_a_project(projects_dir):
    (projects_dir / "config.json").write_text("{}")
    assert "config.json" not in projects.list_projects()


def test_invalid_config_is_ignored(projects_dir):
    (projects_dir / "config.json").write_text("{not json")
    assert {p["name"] for p in projects.describe_projects()} == {"frontend", "backend"}


def test_ignored_path_is_rejected(projects_dir):
    with pytest.raises(ValueError, match="ignored"):
        projects.resolve_path("backend", "node_modules")


def test_search_files_exact_match(projects_dir):
    (projects_dir / "frontend" / "src" / "main.ts").write_text("console.log('main')\n")
    (projects_dir / "frontend" / "src" / "component.ts").write_text("export class Component {}\n")
    result = search_reference_project("frontend", "main.ts", "files")
    assert result["total"] == 1
    assert result["matches"][0]["path"] == "src/main.ts"


def test_search_files_wildcard(projects_dir):
    (projects_dir / "frontend" / "src" / "main.ts").write_text("console.log('main')\n")
    (projects_dir / "frontend" / "src" / "main_test.ts").write_text("test\n")
    (projects_dir / "frontend" / "src" / "component.ts").write_text("export class Component {}\n")
    result = search_reference_project("frontend", "*main*", "files")
    assert result["total"] == 2
    paths = [m["path"] for m in result["matches"]]
    assert "src/main.ts" in paths
    assert "src/main_test.ts" in paths


def test_search_files_no_matches(projects_dir):
    result = search_reference_project("frontend", "nonexistent", "files")
    assert result["total"] == 0
    assert result["matches"] == []


def test_search_content(projects_dir):
    (projects_dir / "frontend" / "src" / "app.ts").write_text("function main() {}\n")
    (projects_dir / "frontend" / "src" / "util.ts").write_text("export const helper = 1\n")
    result = search_reference_project("frontend", "function", "content")
    assert result["total"] == 1
    assert result["matches"][0]["path"] == "src/app.ts"


def test_search_both(projects_dir):
    (projects_dir / "frontend" / "src" / "main.ts").write_text("function main() {}\n")
    (projects_dir / "frontend" / "src" / "util.ts").write_text("export const helper = 1\n")
    result = search_reference_project("frontend", "main", "both")
    # Should find main.ts in both filename and content
    assert result["total"] >= 1
    paths = [m["path"] for m in result["matches"]]
    assert "src/main.ts" in paths


def test_search_unknown_project(projects_dir):
    with pytest.raises(ValueError, match="not found"):
        search_reference_project("missing", "test", "files")


def test_search_invalid_type(projects_dir):
    with pytest.raises(ValueError, match="Invalid search_type"):
        search_reference_project("frontend", "test", "invalid")
