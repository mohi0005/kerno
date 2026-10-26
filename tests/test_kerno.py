import pytest
from app import app, parse_github_url, generate_heuristic_guide, DEFAULT_GEMMA_MODEL


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# ==============================================================================
# 1. GitHub URL Parsing & Validation Tests
# ==============================================================================
def test_parse_github_url_standard():
    owner, repo = parse_github_url("https://github.com/pallets/flask")
    assert owner == "pallets"
    assert repo == "flask"


def test_parse_github_url_with_git_suffix():
    owner, repo = parse_github_url("https://github.com/psf/requests.git")
    assert owner == "psf"
    assert repo == "requests"


def test_parse_github_url_with_trailing_slash():
    owner, repo = parse_github_url("https://github.com/fastapi/fastapi/")
    assert owner == "fastapi"
    assert repo == "fastapi"


def test_parse_github_url_shorthand():
    owner, repo = parse_github_url("expressjs/express")
    assert owner == "expressjs"
    assert repo == "express"


def test_parse_github_url_subpath():
    owner, repo = parse_github_url("https://github.com/BurntSushi/ripgrep/tree/master/crates")
    assert owner == "BurntSushi"
    assert repo == "ripgrep"


def test_parse_github_url_invalid():
    with pytest.raises(ValueError):
        parse_github_url("")

    with pytest.raises(ValueError):
        parse_github_url("https://gitlab.com/owner/repo")

    with pytest.raises(ValueError):
        parse_github_url("not-a-valid-url")


# ==============================================================================
# 2. Heuristic Guide Derivation (Grounded in Configs)
# ==============================================================================
def test_heuristic_guide_python_repo():
    facts = {
        "owner": "pallets",
        "repo": "flask",
        "description": "The Python micro framework.",
        "stars": 69000,
        "forks": 16000,
        "open_issues": 30,
        "default_branch": "main",
        "detected_configs": [{"filename": "pyproject.toml", "description": "Python build config"}],
        "root_files": [
            {"name": "pyproject.toml", "type": "file"},
            {"name": "README.md", "type": "file"},
            {"name": "tests", "type": "dir"}
        ],
        "community_files": {"contributing": None, "readme": "https://..."},
        "languages": [{"name": "Python", "percentage": 98.5}],
        "readme_excerpt": "Flask is a lightweight WSGI framework."
    }

    guide = generate_heuristic_guide(facts)
    assert guide["is_ai_generated"] is False
    assert len(guide["important_files"]) >= 2
    assert any("pyproject.toml" in f["path"] for f in guide["important_files"])
    all_cmds = " ".join([s["command"] for s in guide["setup_steps"]])
    assert "pip install" in all_cmds or "venv" in all_cmds
    assert len(guide["checklist"]) > 0


def test_heuristic_guide_node_repo():
    facts = {
        "owner": "expressjs",
        "repo": "express",
        "description": "Fast, unopinionated web framework for node.",
        "stars": 64000,
        "forks": 12000,
        "open_issues": 150,
        "default_branch": "master",
        "detected_configs": [{"filename": "package.json", "description": "Node manifest"}],
        "root_files": [
            {"name": "package.json", "type": "file"},
            {"name": "Readme.md", "type": "file"}
        ],
        "community_files": {"contributing": None},
        "languages": [{"name": "JavaScript", "percentage": 100.0}],
        "readme_excerpt": "Fast, unopinionated, minimalist web framework."
    }

    guide = generate_heuristic_guide(facts)
    all_cmds = " ".join([s["command"] for s in guide["setup_steps"]])
    assert "npm install" in all_cmds


# ==============================================================================
# 3. Flask API Route Tests
# ==============================================================================
def test_index_route(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Kerno" in response.data
    assert b"gemma-4-31b-it" in response.data


def test_health_route(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert "gemma-4-31b-it" in data["verified_models"]
    assert data["configured_model"] == DEFAULT_GEMMA_MODEL


def test_sample_route(client):
    response = client.get("/api/sample")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["facts"]["repo"] == "flask"
    assert "important_files" in data["guide"]
    assert "setup_steps" in data["guide"]


def test_analyze_route_missing_url(client):
    response = client.post("/api/analyze", json={})
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_analyze_route_invalid_url(client):
    response = client.post("/api/analyze", json={"url": "not-a-repo"})
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
