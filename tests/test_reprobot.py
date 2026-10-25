import pytest
import os
import json
from app import app, determine_verdict, fetch_github_issue, execute_in_docker, is_docker_running

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    res = client.get('/health')
    assert res.status_code == 200
    data = res.get_json()
    assert data['status'] == 'ok'
    assert data['app'] == 'ReproBot'
    assert data['default_gemma_model'] == 'gemma-4-31b-it'
    assert 'docker_running' in data

def test_web_interface_serves_html(client):
    res = client.get('/')
    assert res.status_code == 200
    assert b"ReproBot" in res.data
    assert b"Gemma 4" in res.data
    assert b"--network none" in res.data
    assert b"--memory 256m" in res.data
    assert b"--cpus 1" in res.data
    assert b"Load sample (offline demo)" in res.data
    assert b"SAMPLE, not a live run" in res.data
    assert b"footerModelName" in res.data

def test_missing_issue_url_returns_400(client):
    res = client.post('/reproduce', json={})
    assert res.status_code == 400
    assert "GitHub issue URL" in res.get_json().get("error", "")

def test_invalid_github_url_rejection():
    with pytest.raises(ValueError, match="Invalid GitHub issue URL"):
        fetch_github_issue("https://google.com")

def test_verdict_no_code_found():
    gemma = {
        "status": "NO CODE FOUND",
        "code": "",
        "language": "none",
        "expected_error": "",
        "summary": "Feature request without reproduction steps"
    }
    docker = {"executed": False}
    verdict = determine_verdict(gemma, docker)
    assert verdict == "NO CODE FOUND"

def test_verdict_reproduced():
    gemma = {
        "status": "REPRODUCED",
        "code": "raise KeyError('missing')",
        "language": "python",
        "expected_error": "KeyError",
        "summary": "KeyError raised"
    }
    docker = {
        "executed": True,
        "exit_code": 1,
        "stdout": "",
        "stderr": "Traceback: KeyError: missing",
        "timed_out": False
    }
    verdict = determine_verdict(gemma, docker)
    assert verdict == "REPRODUCED"

def test_verdict_not_reproduced():
    gemma = {
        "status": "REPRODUCED",
        "code": "print('ok')",
        "language": "python",
        "expected_error": "KeyError",
        "summary": "KeyError expected"
    }
    docker = {
        "executed": True,
        "exit_code": 0,
        "stdout": "ok",
        "stderr": "",
        "timed_out": False
    }
    verdict = determine_verdict(gemma, docker)
    assert verdict == "NOT_REPRODUCED"

def test_verdict_unclear_on_timeout():
    gemma = {
        "status": "REPRODUCED",
        "code": "while True: pass",
        "language": "python",
        "expected_error": "TimeoutError",
        "summary": "Loop"
    }
    docker = {
        "executed": True,
        "exit_code": 124,
        "stdout": "",
        "stderr": "Execution timed out after 30 seconds",
        "timed_out": True
    }
    verdict = determine_verdict(gemma, docker)
    assert verdict == "UNCLEAR"

def test_mock_reproduction_endpoint(client):
    res = client.post('/reproduce', json={
        "url": "https://github.com/demo/sample-repo/issues/42",
        "mock": True
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["language"] == "python"
    assert "KeyError" in data["expected_error"]
    assert "payload" in data["code"]
    assert "docker" in data
    assert "verdict" in data

def test_docker_security_never_runs_on_host_when_offline(monkeypatch):
    import app as app_module
    # Force docker to report offline
    monkeypatch.setattr(app_module, "is_docker_running", lambda: False)
    
    result = execute_in_docker("import os; print('malicious')", "python")
    assert result["executed"] is False
    assert "Docker is not currently running" in result["error"]
    assert "Sandbox execution refused on host machine" in result["stderr"]
