import os
import re
import json
import logging
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional, Tuple

import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")
load_dotenv(".env")

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("repocompass")

app = Flask(__name__)

# ==============================================================================
# GEMMA 4 VERIFIED MODEL IDENTIFIERS
# Verified from Google Gemini API official documentation:
# - "gemma-4-31b-it"   (Default recommended 31B instruction-tuned model)
# - "gemma-4-26b-a4b-it" (Open-weight 26B MoE instruction-tuned model)
# ==============================================================================
DEFAULT_GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")

GITHUB_API_BASE = "https://api.github.com"


# ==============================================================================
# GITHUB REPOSITORY URL VALIDATION & EXTRACTION
# ==============================================================================
def parse_github_url(raw_url: str) -> Tuple[str, str]:
    """
    Validates and extracts (owner, repo) from a GitHub URL or 'owner/repo' string.
    Supports:
      - https://github.com/owner/repo
      - https://github.com/owner/repo.git
      - https://github.com/owner/repo/tree/main/subfolder
      - github.com/owner/repo
      - owner/repo
    """
    if not raw_url or not isinstance(raw_url, str):
        raise ValueError("Please provide a valid GitHub repository URL.")

    raw_url = raw_url.strip()

    # If user provided owner/repo shorthand
    shorthand_match = re.match(r"^([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)$", raw_url)
    if shorthand_match:
        owner, repo = shorthand_match.group(1), shorthand_match.group(2)
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo

    # Normalize protocol if omitted
    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
        raw_url = "https://" + raw_url

    parsed = urlparse(raw_url)
    if "github.com" not in parsed.netloc.lower():
        raise ValueError("Only public GitHub repositories (github.com) are supported.")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2:
        raise ValueError("Invalid GitHub URL format. Expected: https://github.com/owner/repo")

    owner = parts[0]
    repo = parts[1]

    if repo.endswith(".git"):
        repo = repo[:-4]

    # Sanitize owner and repo
    if not re.match(r"^[a-zA-Z0-9_.-]+$", owner) or not re.match(r"^[a-zA-Z0-9_.-]+$", repo):
        raise ValueError("GitHub owner or repository name contains invalid characters.")

    return owner, repo


# ==============================================================================
# GITHUB REST API DATA EXTRACTION
# ==============================================================================
def fetch_github_repo_facts(owner: str, repo: str, github_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches real repository facts directly from the GitHub REST API.
    Retrieves metadata, language breakdown, root tree files, README, and manifests.
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "RepoCompass-OpenSource-Guide/1.0"
    }
    token = github_token or os.environ.get("GITHUB_TOKEN")
    if token and token.strip() and token.strip() != "your_github_personal_access_token_here":
        headers["Authorization"] = f"token {token.strip()}"

    # 1. Fetch Repository Metadata
    repo_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
    try:
        resp = requests.get(repo_url, headers=headers, timeout=12)
    except requests.RequestException as e:
        raise RuntimeError(f"Network error connecting to GitHub: {str(e)}")

    if resp.status_code == 404:
        raise ValueError(f"Repository '{owner}/{repo}' was not found or is private.")
    elif resp.status_code == 403:
        rate_limit_reset = resp.headers.get("X-RateLimit-Reset", "unknown")
        raise RuntimeError(
            "GitHub API rate limit exceeded. Please configure a GITHUB_TOKEN in .env to increase the rate limit."
        )
    elif resp.status_code != 200:
        raise RuntimeError(f"GitHub API returned error status {resp.status_code}: {resp.text[:150]}")

    repo_info = resp.json()

    # 2. Fetch Languages
    languages: Dict[str, int] = {}
    try:
        lang_resp = requests.get(f"{repo_url}/languages", headers=headers, timeout=8)
        if lang_resp.status_code == 200:
            languages = lang_resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch languages for {owner}/{repo}: {e}")

    # Calculate language percentages
    total_bytes = sum(languages.values())
    languages_breakdown = []
    if total_bytes > 0:
        for name, count in sorted(languages.items(), key=lambda x: x[1], reverse=True):
            pct = round((count / total_bytes) * 100, 1)
            languages_breakdown.append({"name": name, "bytes": count, "percentage": pct})

    # 3. Fetch Root Contents (Real Files)
    root_files: List[Dict[str, Any]] = []
    try:
        contents_resp = requests.get(f"{repo_url}/contents", headers=headers, timeout=8)
        if contents_resp.status_code == 200:
            for item in contents_resp.json():
                root_files.append({
                    "name": item.get("name", ""),
                    "path": item.get("path", ""),
                    "type": item.get("type", "file"),
                    "html_url": item.get("html_url", "")
                })
    except Exception as e:
        logger.warning(f"Failed to fetch root contents for {owner}/{repo}: {e}")

    root_file_names = {f["name"].lower(): f for f in root_files}

    # 4. Check for Key Community & Contribution Files
    community_files = {
        "readme": None,
        "contributing": None,
        "license": None,
        "code_of_conduct": None,
        "issue_templates": False,
        "workflows": False
    }

    for item in root_files:
        name_lower = item["name"].lower()
        if "readme" in name_lower:
            community_files["readme"] = item["html_url"]
        elif "contributing" in name_lower:
            community_files["contributing"] = item["html_url"]
        elif "license" in name_lower:
            community_files["license"] = item["html_url"]
        elif "code_of_conduct" in name_lower:
            community_files["code_of_conduct"] = item["html_url"]
        elif item["name"] == ".github" and item["type"] == "dir":
            # Check .github contents
            try:
                gh_resp = requests.get(f"{repo_url}/contents/.github", headers=headers, timeout=6)
                if gh_resp.status_code == 200:
                    gh_files = [f.get("name", "").lower() for f in gh_resp.json()]
                    if "contributing.md" in gh_files and not community_files["contributing"]:
                        community_files["contributing"] = f"https://github.com/{owner}/{repo}/blob/{repo_info.get('default_branch', 'main')}/.github/CONTRIBUTING.md"
                    if any("issue_template" in f for f in gh_files):
                        community_files["issue_templates"] = True
                    if "workflows" in gh_files:
                        community_files["workflows"] = True
            except Exception:
                pass

    # 5. Fetch README Content (Excerpt for Grounding)
    readme_content = ""
    try:
        readme_resp = requests.get(
            f"{repo_url}/readme",
            headers={"Accept": "application/vnd.github.raw+json", "User-Agent": headers["User-Agent"]},
            timeout=8
        )
        if readme_resp.status_code == 200:
            # Take first 3000 chars for concise context
            readme_content = readme_resp.text[:3000]
    except Exception as e:
        logger.warning(f"Could not fetch raw README for {owner}/{repo}: {e}")

    # 6. Detect Real Configuration & Manifest Files
    detected_configs: List[Dict[str, str]] = []
    manifest_candidates = [
        # Python
        ("requirements.txt", "Python Pip dependency list"),
        ("pyproject.toml", "Python modern build & dependency config (PEP 517/621)"),
        ("setup.py", "Python setuptools build file"),
        ("Pipfile", "Pipenv dependency manifest"),
        ("environment.yml", "Conda environment file"),
        # JavaScript / TypeScript
        ("package.json", "Node.js npm/yarn dependency & script manifest"),
        ("tsconfig.json", "TypeScript compiler configuration"),
        # Rust
        ("Cargo.toml", "Rust Cargo package & dependency manifest"),
        # Go
        ("go.mod", "Go module and dependency definition"),
        # Java / Kotlin
        ("pom.xml", "Maven project configuration"),
        ("build.gradle", "Gradle build configuration"),
        ("build.gradle.kts", "Gradle Kotlin DSL configuration"),
        # Ruby
        ("Gemfile", "Ruby Bundler dependency file"),
        # PHP
        ("composer.json", "PHP Composer dependency manifest"),
        # Containers & Build
        ("Dockerfile", "Container build recipe"),
        ("docker-compose.yml", "Multi-container local development orchestration"),
        ("docker-compose.yaml", "Multi-container local development orchestration"),
        ("Makefile", "GNU Make build automation commands")
    ]

    for filename, description in manifest_candidates:
        if filename.lower() in root_file_names:
            file_obj = root_file_names[filename.lower()]
            detected_configs.append({
                "filename": filename,
                "description": description,
                "html_url": file_obj.get("html_url", f"https://github.com/{owner}/{repo}/blob/{repo_info.get('default_branch', 'main')}/{filename}")
            })

    # Fetch brief snippet from primary manifest if present
    manifest_snippet = ""
    if "package.json" in root_file_names:
        try:
            pkg_resp = requests.get(
                f"{repo_url}/contents/package.json",
                headers={"Accept": "application/vnd.github.raw+json", "User-Agent": headers["User-Agent"]},
                timeout=5
            )
            if pkg_resp.status_code == 200:
                pkg_data = json.loads(pkg_resp.text)
                scripts = pkg_data.get("scripts", {})
                deps = list(pkg_data.get("dependencies", {}).keys())[:8]
                dev_deps = list(pkg_data.get("devDependencies", {}).keys())[:8]
                manifest_snippet = f"package.json scripts: {json.dumps(scripts)}\nDependencies: {', '.join(deps)}\nDevDependencies: {', '.join(dev_deps)}"
        except Exception:
            pass
    elif "requirements.txt" in root_file_names:
        try:
            req_resp = requests.get(
                f"{repo_url}/contents/requirements.txt",
                headers={"Accept": "application/vnd.github.raw+json", "User-Agent": headers["User-Agent"]},
                timeout=5
            )
            if req_resp.status_code == 200:
                lines = [l.strip() for l in req_resp.text.splitlines() if l.strip() and not l.startswith("#")][:15]
                manifest_snippet = f"requirements.txt packages: {', '.join(lines)}"
        except Exception:
            pass

    return {
        "owner": owner,
        "repo": repo,
        "full_name": repo_info.get("full_name", f"{owner}/{repo}"),
        "html_url": repo_info.get("html_url", f"https://github.com/{owner}/{repo}"),
        "description": repo_info.get("description") or "No description provided by repository maintainers.",
        "stars": repo_info.get("stargazers_count", 0),
        "forks": repo_info.get("forks_count", 0),
        "open_issues": repo_info.get("open_issues_count", 0),
        "default_branch": repo_info.get("default_branch", "main"),
        "license": repo_info.get("license", {}).get("name") if repo_info.get("license") else "No license specified",
        "license_spdx": repo_info.get("license", {}).get("spdx_id") if repo_info.get("license") else None,
        "topics": repo_info.get("topics", []),
        "homepage": repo_info.get("homepage"),
        "created_at": repo_info.get("created_at"),
        "updated_at": repo_info.get("updated_at"),
        "languages": languages_breakdown,
        "root_files": root_files,
        "community_files": community_files,
        "detected_configs": detected_configs,
        "readme_excerpt": readme_content,
        "manifest_snippet": manifest_snippet
    }


# ==============================================================================
# HEURISTIC FALLBACK (RULE-BASED DERIVATION FROM REAL FILES)
# Used when Gemini API key is missing or encounters quota/auth errors,
# ensuring the app is always functional and 100% grounded in verified facts.
# ==============================================================================
def generate_heuristic_guide(facts: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    """
    Generates a deterministic contribution guide strictly from the detected GitHub facts.
    Clearly marked as rule-based synthesis.
    """
    owner = facts["owner"]
    repo = facts["repo"]
    default_branch = facts["default_branch"]
    configs = [c["filename"].lower() for c in facts["detected_configs"]]
    root_names = [f["name"].lower() for f in facts["root_files"]]

    # Important files analysis
    important_files = []
    for f in facts["root_files"]:
        name = f["name"]
        name_l = name.lower()
        if "readme" in name_l:
            important_files.append({"path": name, "role": "Project documentation & getting started overview", "importance": "Essential"})
        elif "contributing" in name_l:
            important_files.append({"path": name, "role": "Maintainer contribution guidelines and code style", "importance": "Essential"})
        elif "license" in name_l:
            important_files.append({"path": name, "role": "Open-source legal permissions and usage rights", "importance": "Reference"})
        elif name_l in ["package.json", "requirements.txt", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml", "build.gradle"]:
            important_files.append({"path": name, "role": "Primary project dependency and build configuration", "importance": "Essential"})
        elif name_l in ["dockerfile", "docker-compose.yml"]:
            important_files.append({"path": name, "role": "Containerization and local development runtime", "importance": "Helpful"})
        elif name_l in ["makefile"]:
            important_files.append({"path": name, "role": "Automated build and test shortcuts", "importance": "Helpful"})
        elif name_l in ["tests", "test", "spec", "src", "lib", "app", "docs"]:
            important_files.append({"path": name, "role": f"Core directory for {name}", "importance": "High"})

    # Setup instructions derived from actual configs
    setup_steps = [
        {"title": "1. Fork & Clone", "command": f"git clone https://github.com/{owner}/{repo}.git\ncd {repo}", "notes": "Fork the repository on GitHub first, then clone your fork."}
    ]

    if "requirements.txt" in configs or "pyproject.toml" in configs:
        setup_steps.append({
            "title": "2. Create Python Environment",
            "command": "python -m venv .venv\n# On Windows:\n.venv\\Scripts\\activate\n# On macOS/Linux:\nsource .venv/bin/activate",
            "notes": "Isolate project dependencies in a virtual environment."
        })
        if "requirements.txt" in configs:
            setup_steps.append({
                "title": "3. Install Dependencies",
                "command": "pip install -r requirements.txt",
                "notes": "Installs packages specified in the verified requirements.txt."
            })
        elif "pyproject.toml" in configs:
            setup_steps.append({
                "title": "3. Install Dependencies",
                "command": "pip install -e .",
                "notes": "Installs the package in editable mode as defined in pyproject.toml."
            })
        setup_steps.append({
            "title": "4. Run Test Suite",
            "command": "pytest",
            "notes": "Verify your local environment passes all existing test cases."
        })
    elif "package.json" in configs:
        setup_steps.append({
            "title": "2. Install Node Dependencies",
            "command": "npm install",
            "notes": "Installs dependencies specified in package.json."
        })
        setup_steps.append({
            "title": "3. Run Development / Tests",
            "command": "npm test",
            "notes": "Runs the test script defined in package.json."
        })
    elif "cargo.toml" in configs:
        setup_steps.append({
            "title": "2. Build & Test Rust Project",
            "command": "cargo build\ncargo test",
            "notes": "Compiles and executes test suite via Cargo."
        })
    elif "go.mod" in configs:
        setup_steps.append({
            "title": "2. Download Go Modules & Test",
            "command": "go mod download\ngo test ./...",
            "notes": "Downloads dependencies and runs Go tests."
        })
    else:
        setup_steps.append({
            "title": "2. Check Documentation",
            "command": "# Refer to README.md in the repository",
            "notes": "No standard manifest detected in repository root. Consult README for custom setup."
        })

    # Suggested contribution areas grounded in repository evidence
    has_contributing = bool(facts["community_files"].get("contributing"))
    has_tests = any("test" in f["name"].lower() for f in facts["root_files"])
    has_docs = any("doc" in f["name"].lower() for f in facts["root_files"])

    suggestions = [
        {
            "area": "Documentation & Setup Clarity",
            "difficulty": "Beginner",
            "description": "Follow the setup guide yourself and verify that installation instructions in README.md are clear and reproducible.",
            "evidence": f"Repository has {len(facts['detected_configs'])} detected config file(s) and {facts['stars']} stars."
        },
        {
            "area": "Add or Improve Test Coverage",
            "difficulty": "Intermediate",
            "description": "Check existing test coverage and add unit tests for edge cases or untested helper functions.",
            "evidence": f"Root directory contains {', '.join([f['name'] for f in facts['root_files'] if 'test' in f['name'].lower()]) or 'standard project directories'}."
        },
        {
            "area": "Triage Open Issues & Reproduce Bugs",
            "difficulty": "Beginner to Intermediate",
            "description": "Browse open issues on GitHub, help reproduce reported bugs, or clarify steps with reporters.",
            "evidence": f"Repository currently has {facts['open_issues']} open issue(s)."
        }
    ]

    if not has_contributing:
        suggestions.append({
            "area": "Suggest a CONTRIBUTING.md Guide",
            "difficulty": "Beginner",
            "description": "The repository does not have a dedicated CONTRIBUTING.md in its root. Proposing a contribution guide helps future developers.",
            "evidence": "No CONTRIBUTING.md was detected in repository root or .github folder."
        })

    purpose = facts["description"]
    if facts.get("readme_excerpt"):
        # Strip HTML tags and markdown badge links from README excerpt for a clean summary
        cleaned_readme = re.sub(r"<[^>]+>", "", facts["readme_excerpt"])
        cleaned_readme = re.sub(r"\[!\[.*?\]\(.*?\)\]\(.*?\)", "", cleaned_readme)
        cleaned_readme = re.sub(r"!\[.*?\]\(.*?\)", "", cleaned_readme)
        cleaned_readme = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", cleaned_readme)
        paragraphs = [p.strip() for p in cleaned_readme.split("\n\n") if p.strip() and not p.strip().startswith("#") and len(p.strip()) > 30]
        if paragraphs:
            purpose += " " + paragraphs[0][:300]

    return {
        "project_purpose": purpose,
        "important_files": important_files,
        "setup_steps": setup_steps,
        "suggested_contributions": suggestions,
        "checklist": [
            {"step": "Star and fork the repository on GitHub", "done": False},
            {"step": "Clone your fork locally and configure git remotes", "done": False},
            {"step": "Read CONTRIBUTING.md and Code of Conduct if available", "done": False},
            {"step": "Create an isolated feature branch (e.g., git checkout -b fix/issue-name)", "done": False},
            {"step": "Set up the local environment and ensure tests pass before changing code", "done": False},
            {"step": "Make minimal, well-documented changes addressing a single concern", "done": False},
            {"step": "Write new unit tests covering your change", "done": False},
            {"step": "Push your branch and submit a clear Pull Request with details", "done": False}
        ],
        "is_ai_generated": False,
        "model_used": "Heuristic Rule Engine (Gemma 4 fallback)",
        "ai_status_message": reason or "Generated using rule-based synthesis from verified repository files."
    }


# ==============================================================================
# GEMINI API CALL WITH GEMMA 4 (EXPLICIT, VISIBLE IN SOURCE CODE)
# ==============================================================================
def call_gemma_model(facts: Dict[str, Any], api_key: Optional[str] = None, model_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Calls the Google Gemini API using a verified Gemma 4 model identifier.
    Uses google.genai.Client to execute the prompt.
    Includes strict grounding rules and structured JSON response parsing.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    target_model = model_name or os.environ.get("GEMMA_MODEL", DEFAULT_GEMMA_MODEL)

    if not key or not key.strip() or key.strip() == "your_gemini_api_key_here":
        logger.info("GEMINI_API_KEY is not set. Using heuristic rule engine fallback.")
        return generate_heuristic_guide(
            facts,
            reason="Gemini API key is not configured. Displaying structured analysis from verified repository files."
        )

    # Prepare grounding context strictly from facts
    file_list = [f"{f['name']} ({f['type']})" for f in facts["root_files"]]
    config_list = [f"{c['filename']} - {c['description']}" for c in facts["detected_configs"]]
    languages_str = ", ".join([f"{l['name']} ({l['percentage']}%)" for l in facts["languages"]]) or "None specified"

    prompt = f"""You are RepoCompass, an AI open-source onboarding mentor powered by Gemma 4.
Analyze the following real repository data and synthesize an accurate, beginner-friendly contribution guide.

=== REPOSITORY FACTS (VERIFIED GROUND TRUTH) ===
Repository: {facts['full_name']}
GitHub URL: {facts['html_url']}
Description: {facts['description']}
Stars: {facts['stars']} | Forks: {facts['forks']} | Open Issues: {facts['open_issues']}
License: {facts['license']}
Default Branch: {facts['default_branch']}
Languages: {languages_str}

Detected Root Files:
{json.dumps(file_list, indent=2)}

Detected Configuration & Manifest Files:
{json.dumps(config_list, indent=2)}

Configuration Snippet:
{facts.get('manifest_snippet', 'None available')}

README Excerpt:
{facts.get('readme_excerpt', 'No README provided')[:1500]}
================================================

=== INSTRUCTIONS & GROUNDING RULES ===
1. STRICT GROUNDING: Rely ONLY on the verified facts above. Do NOT invent files, commands, libraries, or project features that are not substantiated by the provided data.
2. DISTINGUISH FACTS FROM INFERENCES: Clearly explain what the repository does based on its README and code manifests.
3. IMPORTANT FILES: Select 4 to 8 files from the DETECTED ROOT FILES and explain their exact role for a newcomer.
4. SETUP INSTRUCTIONS: Provide realistic setup commands based ONLY on the detected config files (e.g. if package.json is present, use npm/yarn; if requirements.txt or pyproject.toml is present, use Python venv and pip).
5. BEGINNER CONTRIBUTIONS: Suggest 3 to 5 realistic contribution areas for beginners (e.g. documentation, test coverage, issue reproduction, examples) citing the actual evidence (e.g. "Root contains X but lacks Y"). Explicitly indicate that these are exploratory AI suggestions, not verified open GitHub issues.
6. FORMAT: You MUST return a single valid JSON object with the exact keys:
{{
  "project_purpose": "Clear 2-3 paragraph explanation of what the project does and who it is for in plain English.",
  "important_files": [
    {{"path": "filename", "role": "concise explanation of role", "importance": "Essential" | "High" | "Helpful"}}
  ],
  "setup_steps": [
    {{"title": "Step Name", "command": "shell commands", "notes": "helpful tips"}}
  ],
  "suggested_contributions": [
    {{"area": "Title", "difficulty": "Beginner" | "Intermediate", "description": "detailed description", "evidence": "evidence from repo"}}
  ],
  "checklist": [
    {{"step": "Step description", "done": false}}
  ]
}}
Do NOT include markdown formatting outside the JSON. Return raw JSON.
"""

    try:
        # VISIBLE GOOGLE GEMINI API CALL WITH GEMMA 4
        from google import genai
        from google.genai import types

        logger.info(f"Invoking Gemini API with model: {target_model}")
        client = genai.Client(api_key=key.strip())

        response = client.models.generate_content(
            model=target_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                top_p=0.9,
                max_output_tokens=2500
            )
        )

        raw_text = response.text.strip()
        logger.info(f"Gemini API returned response length: {len(raw_text)}")

        # Strip markdown code blocks if wrapped
        clean_text = raw_text
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()

        parsed_data = json.loads(clean_text)

        # Validate required keys
        required_keys = ["project_purpose", "important_files", "setup_steps", "suggested_contributions", "checklist"]
        for rk in required_keys:
            if rk not in parsed_data:
                raise ValueError(f"Missing expected key '{rk}' in Gemma output.")

        parsed_data["is_ai_generated"] = True
        parsed_data["model_used"] = target_model
        parsed_data["ai_status_message"] = f"Synthesized by Gemma 4 ({target_model}) via Google Gemini API."
        return parsed_data

    except Exception as e:
        logger.error(f"Gemma 4 API call failed: {str(e)}")
        # Provide helpful graceful degradation
        err_msg = str(e)
        if "401" in err_msg or "UNAUTHENTICATED" in err_msg:
            reason = "Gemini API Key is invalid or expired. Switched to rule-based analysis."
        elif "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
            reason = "Gemini API rate limit reached. Switched to rule-based analysis."
        elif "not found" in err_msg.lower() or "404" in err_msg:
            reason = f"Model '{target_model}' unavailable. Switched to rule-based analysis."
        else:
            reason = f"Gemini API request failed: {err_msg[:120]}. Switched to rule-based analysis."

        return generate_heuristic_guide(facts, reason=reason)


# ==============================================================================
# FLASK WEB APPLICATION ROUTES
# ==============================================================================
@app.route("/")
def index():
    """Renders the main RepoCompass developer dashboard."""
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def analyze_repository():
    """
    Core API endpoint.
    Accepts: { "url": "https://github.com/owner/repo", "api_key": "(optional)" }
    Returns: Complete repository facts + Gemma 4 generated guide.
    """
    data = request.get_json(force=True, silent=True) or {}
    raw_url = data.get("url") or data.get("repo_url") or ""
    custom_api_key = data.get("api_key") or ""
    custom_model = data.get("model") or ""

    if not raw_url:
        return jsonify({"error": "Please provide a public GitHub repository URL."}), 400

    # 1. Validate & Parse GitHub URL
    try:
        owner, repo = parse_github_url(raw_url)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400

    # 2. Fetch Facts from GitHub REST API
    try:
        facts = fetch_github_repo_facts(owner, repo)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 404
    except RuntimeError as re_err:
        return jsonify({"error": str(re_err)}), 502
    except Exception as e:
        logger.exception(f"Unexpected error fetching repo facts: {e}")
        return jsonify({"error": f"Failed to retrieve repository data: {str(e)}"}), 500

    # 3. Generate Guide via Gemma 4 (or Fallback)
    guide = call_gemma_model(
        facts,
        api_key=custom_api_key if custom_api_key.strip() else None,
        model_name=custom_model if custom_model.strip() else None
    )

    # 4. Construct complete response
    return jsonify({
        "success": True,
        "facts": facts,
        "guide": guide,
        "model_id": guide.get("model_used", DEFAULT_GEMMA_MODEL)
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    """Returns application status, verified models, and configuration state."""
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") and os.environ.get("GEMINI_API_KEY") != "your_gemini_api_key_here")
    has_github = bool(os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_TOKEN") != "your_github_personal_access_token_here")

    return jsonify({
        "status": "healthy",
        "service": "RepoCompass",
        "configured_model": DEFAULT_GEMMA_MODEL,
        "verified_models": ["gemma-4-31b-it", "gemma-4-26b-a4b-it"],
        "gemini_api_configured": has_gemini,
        "github_token_configured": has_github
    })


@app.route("/api/sample", methods=["GET"])
def get_sample():
    """Returns sample pre-generated data for instant testing or offline demo."""
    sample_facts = {
        "owner": "pallets",
        "repo": "flask",
        "full_name": "pallets/flask",
        "html_url": "https://github.com/pallets/flask",
        "description": "The Python micro framework for building web applications.",
        "stars": 69200,
        "forks": 16100,
        "open_issues": 34,
        "default_branch": "main",
        "license": "BSD 3-Clause 'New' or 'Revised' License",
        "license_spdx": "BSD-3-Clause",
        "topics": ["python", "flask", "wsid", "microframework", "web-framework"],
        "homepage": "https://palletsprojects.com/p/flask",
        "created_at": "2010-04-06T11:11:59Z",
        "updated_at": "2026-10-25T10:00:00Z",
        "languages": [
            {"name": "Python", "bytes": 742000, "percentage": 98.4},
            {"name": "HTML", "bytes": 12000, "percentage": 1.6}
        ],
        "root_files": [
            {"name": "pyproject.toml", "path": "pyproject.toml", "type": "file", "html_url": "https://github.com/pallets/flask/blob/main/pyproject.toml"},
            {"name": "requirements", "path": "requirements", "type": "dir", "html_url": "https://github.com/pallets/flask/tree/main/requirements"},
            {"name": "src", "path": "src", "type": "dir", "html_url": "https://github.com/pallets/flask/tree/main/src"},
            {"name": "tests", "path": "tests", "type": "dir", "html_url": "https://github.com/pallets/flask/tree/main/tests"},
            {"name": "docs", "path": "docs", "type": "dir", "html_url": "https://github.com/pallets/flask/tree/main/docs"},
            {"name": "README.md", "path": "README.md", "type": "file", "html_url": "https://github.com/pallets/flask/blob/main/README.md"},
            {"name": "LICENSE.txt", "path": "LICENSE.txt", "type": "file", "html_url": "https://github.com/pallets/flask/blob/main/LICENSE.txt"}
        ],
        "community_files": {
            "readme": "https://github.com/pallets/flask/blob/main/README.md",
            "contributing": "https://github.com/pallets/flask/blob/main/CONTRIBUTING.rst",
            "license": "https://github.com/pallets/flask/blob/main/LICENSE.txt",
            "code_of_conduct": None,
            "issue_templates": True,
            "workflows": True
        },
        "detected_configs": [
            {"filename": "pyproject.toml", "description": "Python modern build & dependency config (PEP 517/621)", "html_url": "https://github.com/pallets/flask/blob/main/pyproject.toml"}
        ]
    }
    sample_guide = generate_heuristic_guide(sample_facts, reason="Sample demonstration mode for Flask.")
    sample_guide["project_purpose"] = (
        "Flask is a lightweight WSGI web application framework designed to make getting started quick and easy, "
        "with the ability to scale up to complex applications. It provides core web primitives (routing, request handling, "
        "templating via Jinja) while leaving extensions and architectural choices to the developer."
    )
    return jsonify({
        "success": True,
        "facts": sample_facts,
        "guide": sample_guide,
        "model_id": DEFAULT_GEMMA_MODEL
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    print(f"RepoCompass running on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
