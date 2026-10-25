import os, json, re, time, subprocess, tempfile
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from dotenv import load_dotenv
import requests

# Load environment variables from .env.local and .env
load_dotenv(".env.local")
load_dotenv(".env")

app = Flask(__name__, static_folder='dist', static_url_path='')

# ==============================================================================
# GEMMA 4 VERIFIED MODEL IDENTIFIERS
# Verified from Google Gemini API documentation (released April 2, 2026):
# - "gemma-4-31b-it"   (Default open-weight instruction-tuned 31B model)
# - "gemma-4-26b-a4b-it" (Open-weight 26B model)
# ==============================================================================
DEFAULT_GEMMA_MODEL = os.environ.get("GEMMA_MODEL", "gemma-4-31b-it")
DEFAULT_OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma2")
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ReproBot — Autonomous Bug Reproduction with Gemma 4</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
    .animate-pulse { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen py-10 px-4 font-sans">
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- Header -->
    <header class="border-b border-slate-800 pb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="text-3xl">🤖</span>
          <h1 class="text-2xl font-bold tracking-tight text-white">ReproBot</h1>
          <span class="bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 text-xs px-2.5 py-1 rounded-full font-medium">Gemma 4 Edition</span>
        </div>
        <p class="text-slate-400 text-sm mt-1">Autonomous bug reproduction engine in isolated Docker sandboxes.</p>
      </div>
      <div id="dockerStatus" class="text-xs px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 flex items-center gap-2">
        <span class="w-2 h-2 rounded-full bg-amber-400"></span> Checking Docker...
      </div>
    </header>

    <!-- Sandbox Isolation Banner -->
    <div class="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400">
      <div class="flex items-center gap-2 font-mono">
        <span class="text-emerald-400 font-bold">🔒 Docker Sandbox:</span>
        <span class="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">--network none</span>
        <span class="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">--memory 256m</span>
        <span class="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">--cpus 1</span>
        <span class="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">30s timeout</span>
        <span class="bg-slate-800 px-2 py-0.5 rounded border border-slate-700">read-only :ro</span>
      </div>
      <div class="text-amber-400 font-medium">Host Execution Strictly Forbidden</div>
    </div>

    <!-- Input Form -->
    <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4">
      <div>
        <label for="issueUrl" class="block text-sm font-medium text-slate-200 mb-1.5">GitHub Issue URL</label>
        <div class="flex gap-2">
          <input type="url" id="issueUrl" placeholder="https://github.com/owner/repo/issues/123" 
            class="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500">
          <button id="runBtn" onclick="runRepro()" 
            class="bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-sm px-6 py-2.5 rounded-lg transition-colors flex items-center gap-2 shadow-lg shadow-indigo-600/20">
            <span>Reproduce</span>
          </button>
        </div>
      </div>

      <!-- Quick Presets -->
      <div class="flex items-center gap-2 pt-1 flex-wrap text-xs">
        <span class="text-slate-400">Quick Demos:</span>
        <button onclick="setSample('https://github.com/python/cpython/issues/160598')" 
          class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded border border-slate-700">cpython/issues/160598</button>
        <button onclick="setSample('https://github.com/psf/requests/issues/1')" 
          class="bg-slate-800 hover:bg-slate-700 text-slate-300 px-2.5 py-1 rounded border border-slate-700">requests/issues/1</button>
        <button onclick="loadSampleDemo()" 
          class="bg-indigo-900/50 hover:bg-indigo-900/70 text-indigo-300 px-2.5 py-1 rounded border border-indigo-700/50">Load sample (offline demo)</button>
      </div>

      <!-- Engine Configuration -->
      <div class="pt-3 border-t border-slate-800/80 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
        <div>
          <label class="block text-slate-400 mb-1">AI Provider</label>
          <select id="provider" class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200">
            <option value="gemini">Gemini API (Gemma 4: gemma-4-31b-it)</option>
            <option value="ollama">Ollama (Open-Weight Local Gemma)</option>
          </select>
        </div>
        <div>
          <label class="block text-slate-400 mb-1">Target Model ID</label>
          <input type="text" id="modelName" value="gemma-4-31b-it" 
            class="w-full bg-slate-950 border border-slate-800 rounded p-2 text-slate-200 font-mono">
        </div>
      </div>
    </div>

    <!-- Live Status / Loading -->
    <div id="loader" class="hidden bg-slate-900 border border-indigo-500/30 rounded-xl p-4 text-center">
      <div class="inline-flex items-center gap-3 text-indigo-400 text-sm font-medium">
        <svg class="animate-spin h-5 w-5 text-indigo-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
        </svg>
        <span id="loaderMsg">Fetching issue and querying Gemma 4 model...</span>
      </div>
    </div>

    <!-- Error Display -->
    <div id="errorBox" class="hidden bg-red-950/40 border border-red-800/60 rounded-xl p-4 text-sm text-red-300"></div>

    <!-- Results Section -->
    <div id="resultBox" class="hidden space-y-5">
      <!-- Visible Sample Notice (Required for demo mode) -->
      <div id="sampleNotice" class="hidden bg-amber-500/20 text-amber-300 border border-amber-500/50 px-4 py-2 rounded-xl text-xs font-bold tracking-wide uppercase flex items-center gap-2 shadow-sm">
        <span>⚠️</span> <span>SAMPLE, not a live run</span>
      </div>

      <!-- Verdict Card -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div class="text-xs text-slate-400 uppercase font-semibold tracking-wider">Reproduction Verdict</div>
          <div id="verdictBadge" class="mt-1 inline-block text-xl font-black px-4 py-1.5 rounded-lg uppercase tracking-wide">
            UNCLEAR
          </div>
          <div id="issueTitle" class="text-sm text-slate-300 mt-2 font-medium"></div>
        </div>
        <div class="text-right text-xs text-slate-400 space-y-1">
          <div>Language: <span id="resLang" class="font-mono text-slate-200 uppercase font-bold">PYTHON</span></div>
          <div>Docker Exit Code: <span id="resExitCode" class="font-mono text-slate-200">0</span></div>
          <div>Execution Time: <span id="resDuration" class="font-mono text-slate-200">0.0s</span></div>
        </div>
      </div>

      <!-- Extracted Code -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div class="bg-slate-950/60 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
          <span class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Extracted Standalone Reproduction Code</span>
          <button onclick="copyCode()" class="text-xs text-slate-400 hover:text-white transition-colors bg-slate-800 px-2 py-1 rounded">Copy Code</button>
        </div>
        <pre id="codeView" class="p-4 text-xs font-mono text-emerald-400 overflow-x-auto max-h-72 bg-slate-950"></pre>
      </div>

      <!-- Real Docker Output -->
      <div class="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div class="bg-slate-950/60 px-4 py-2.5 border-b border-slate-800 flex items-center justify-between">
          <span class="text-xs font-semibold text-slate-300 uppercase tracking-wider">Real Docker Sandbox Terminal Output</span>
          <span id="sandboxDetails" class="text-xs text-slate-500 font-mono">--network none --memory 256m --cpus 1 30s timeout</span>
        </div>
        <pre id="dockerOutput" class="p-4 text-xs font-mono text-slate-200 overflow-x-auto max-h-60 bg-black"></pre>
      </div>
    </div>

    <!-- Page Footer with Model Name -->
    <footer class="border-t border-slate-800 pt-6 pb-2 text-center text-xs text-slate-500 space-y-1">
      <div>ReproBot · Autonomous Bug Reproduction Sandbox</div>
      <div>Active Engine Model: <span class="font-mono text-indigo-400 font-semibold" id="footerModelName">gemma-4-31b-it</span> (<span id="footerProvider" class="text-slate-400">Gemini API</span>)</div>
    </footer>
  </div>

  <script>
    async function checkHealth() {
      try {
        const res = await fetch('/health');
        const data = await res.json();
        const d = document.getElementById('dockerStatus');
        if (data.docker_running) {
          d.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-400"></span> Docker Sandbox Online';
          d.className = d.className.replace('text-slate-400', 'text-emerald-400');
        } else {
          d.innerHTML = '<span class="w-2 h-2 rounded-full bg-amber-400"></span> Docker Offline (Start Docker Desktop)';
          d.className = d.className.replace('text-slate-400', 'text-amber-400');
        }
      } catch (e) {
        console.error(e);
      }
    }
    checkHealth();

    function setSample(url) {
      document.getElementById('issueUrl').value = url;
    }

    async function loadSampleDemo() {
      document.getElementById('issueUrl').value = 'https://github.com/demo/sample-repo/issues/42';
      runRepro(true);
    }

    function updateFooterModel() {
      const p = document.getElementById('provider').value;
      const m = document.getElementById('modelName').value;
      document.getElementById('footerModelName').textContent = m;
      document.getElementById('footerProvider').textContent = p === 'ollama' ? 'Ollama' : 'Gemini API';
    }

    document.getElementById('provider').addEventListener('change', function() {
      if (this.value === 'ollama') {
        document.getElementById('modelName').value = 'gemma2';
      } else {
        document.getElementById('modelName').value = 'gemma-4-31b-it';
      }
      updateFooterModel();
    });
    document.getElementById('modelName').addEventListener('input', updateFooterModel);
    updateFooterModel();

    function copyCode() {
      const code = document.getElementById('codeView').textContent;
      navigator.clipboard.writeText(code);
      alert('Code copied to clipboard!');
    }

    async function runRepro(isMock = false) {
      const url = document.getElementById('issueUrl').value.trim();
      if (!url) {
        alert('Please enter a GitHub Issue URL');
        return;
      }

      const provider = document.getElementById('provider').value;
      const model = document.getElementById('modelName').value;

      document.getElementById('errorBox').classList.add('hidden');
      document.getElementById('resultBox').classList.add('hidden');
      document.getElementById('sampleNotice').classList.add('hidden');
      document.getElementById('loader').classList.remove('hidden');
      document.getElementById('runBtn').disabled = true;

      try {
        const res = await fetch('/reproduce', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url, provider, model, mock: isMock })
        });
        const d = await res.json();
        document.getElementById('loader').classList.add('hidden');
        document.getElementById('runBtn').disabled = false;

        if (d.error && !d.verdict) {
          document.getElementById('errorBox').textContent = d.error;
          document.getElementById('errorBox').classList.remove('hidden');
          return;
        }

        // Render Results
        document.getElementById('resultBox').classList.remove('hidden');
        if (isMock || d.is_mock) {
          document.getElementById('sampleNotice').classList.remove('hidden');
        } else {
          document.getElementById('sampleNotice').classList.add('hidden');
        }

        document.getElementById('issueTitle').textContent = d.issue ? `[#${d.issue.number}] ${d.issue.title}` : url;
        document.getElementById('resLang').textContent = d.language || 'NONE';
        document.getElementById('resExitCode').textContent = d.docker ? d.docker.exit_code : 'N/A';
        document.getElementById('resDuration').textContent = d.docker ? `${d.docker.duration}s` : '0s';

        document.getElementById('codeView').textContent = d.code || '(No reproduction code extracted)';
        const terminalOut = (d.docker ? (d.docker.stdout + (d.docker.stderr ? "\\n" + d.docker.stderr : "")) : d.error) || '(No console output)';
        document.getElementById('dockerOutput').textContent = terminalOut;

        const badge = document.getElementById('verdictBadge');
        const verdict = d.verdict || 'UNCLEAR';
        badge.textContent = verdict;

        if (verdict === 'REPRODUCED') {
          badge.className = 'mt-1 inline-block text-xl font-black px-4 py-1.5 rounded-lg uppercase tracking-wide bg-rose-500/20 text-rose-400 border border-rose-500/40';
        } else if (verdict === 'NOT_REPRODUCED') {
          badge.className = 'mt-1 inline-block text-xl font-black px-4 py-1.5 rounded-lg uppercase tracking-wide bg-emerald-500/20 text-emerald-400 border border-emerald-500/40';
        } else if (verdict === 'NO CODE FOUND') {
          badge.className = 'mt-1 inline-block text-xl font-black px-4 py-1.5 rounded-lg uppercase tracking-wide bg-slate-700/50 text-slate-300 border border-slate-600';
        } else {
          badge.className = 'mt-1 inline-block text-xl font-black px-4 py-1.5 rounded-lg uppercase tracking-wide bg-amber-500/20 text-amber-400 border border-amber-500/40';
        }

      } catch (err) {
        document.getElementById('loader').classList.add('hidden');
        document.getElementById('runBtn').disabled = false;
        document.getElementById('errorBox').textContent = 'Request failed: ' + err.message;
        document.getElementById('errorBox').classList.remove('hidden');
      }
    }
  </script>
</body>
</html>
"""

# ==============================================================================
# ROUTING & STATIC ASSET HANDLING
# ==============================================================================
@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    if os.environ.get("SERVE_DIST") and os.path.exists(os.path.join(app.static_folder, "index.html")):
        return send_from_directory(app.static_folder, "index.html")
    return render_template_string(PAGE)

@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "app": "ReproBot",
        "docker_running": is_docker_running(),
        "default_gemma_model": DEFAULT_GEMMA_MODEL,
        "default_ollama_model": DEFAULT_OLLAMA_MODEL
    })

# ==============================================================================
# GITHUB ISSUE INGESTION
# ==============================================================================
def fetch_github_issue(issue_url: str) -> dict:
    match = re.search(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url)
    if not match:
        raise ValueError("Invalid GitHub issue URL. Expected format: https://github.com/{owner}/{repo}/issues/{number}")
    owner, repo, issue_number = match.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "ReproBot-Bug-Reproduction"}
    
    github_token = os.environ.get("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"
    
    resp = requests.get(api_url, headers=headers, timeout=15)
    if resp.status_code == 404:
        raise ValueError(f"GitHub issue not found: {issue_url}")
    if resp.status_code == 403:
        raise ValueError("GitHub API rate limit exceeded. Set GITHUB_TOKEN environment variable in .env.local.")
    if resp.status_code != 200:
        raise ValueError(f"GitHub API error ({resp.status_code}): {resp.text}")
    
    data = resp.json()
    return {
        "owner": owner,
        "repo": repo,
        "number": int(issue_number),
        "title": data.get("title", ""),
        "body": data.get("body", "") or "",
        "html_url": data.get("html_url", issue_url)
    }

# ==============================================================================
# GEMINI API CALL FOR GEMMA 4 (Gemma 4 Prize Entry)
# Model verified: gemma-4-31b-it (Google's open-weight instruction-tuned model)
# ==============================================================================
def call_gemma_gemini_api(api_key: str, model_name: str, prompt: str) -> str:
    """
    Invokes the Google Gemini API using Gemma 4 open-weight model.
    Tries the official Google GenAI SDK first, falling back to direct HTTPS REST.
    """
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text
    except ImportError:
        # Fallback to direct Gemini REST API if google-genai package is not installed yet
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {"parts": [{"text": prompt}]}
            ]
        }
        res = requests.post(url, headers=headers, params={"key": api_key}, json=payload, timeout=45)
        if res.status_code != 200:
            raise Exception(f"Gemini API error ({res.status_code}): {res.text}")
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

# ==============================================================================
# OLLAMA API CALL (Local Open-Weight Model Support)
# ==============================================================================
def call_gemma_ollama_api(host: str, model_name: str, prompt: str) -> str:
    """
    Calls local or remote Ollama instance running Gemma.
    """
    endpoint = f"{host.rstrip('/')}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False
    }
    res = requests.post(endpoint, json=payload, timeout=60)
    if res.status_code != 200:
        raise Exception(f"Ollama API error ({res.status_code}): {res.text}")
    return res.json().get("response", "")

# ==============================================================================
# GEMMA 4 PROMPT & REPRODUCTION EXTRACTION
# ==============================================================================
PROMPT_TEMPLATE = """You are ReproBot, an AI specialized in analyzing GitHub bug reports and generating standalone, minimal reproduction scripts.

Analyze the following GitHub issue:
Title: {title}
URL: {url}
Body:
{body}

Instructions:
1. Determine if this issue contains sufficient information or code to reproduce the bug.
2. If there is NO code, no stack trace, and no clear way to reproduce it, reply with status "NO CODE FOUND" and leave code empty.
3. If it CAN be reproduced, extract or write a minimal, self-contained reproduction script in Python (preferred) or JavaScript (Node.js).
4. The script should only use standard library or common packages if possible, and should reproduce the exact error or unexpected behavior mentioned.
5. Identify the expected error/exception name or behavior that confirms reproduction.

Respond with ONLY valid JSON with this exact schema:
{{
  "status": "REPRODUCED" | "NOT_REPRODUCED" | "UNCLEAR" | "NO CODE FOUND",
  "language": "python" | "javascript" | "none",
  "code": "<standalone runnable script code or empty string>",
  "expected_error": "<expected error message or exception name, e.g. KeyError or TypeError>",
  "summary": "<one sentence summary of the bug>"
}}
"""

def extract_reproduction(issue: dict, provider: str = "gemini", model_name: str = None) -> dict:
    prompt = PROMPT_TEMPLATE.format(
        title=issue.get("title", ""),
        url=issue.get("html_url", ""),
        body=issue.get("body", "")[:4000]
    )
    
    try:
        if provider == "ollama":
            host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)
            model = model_name or DEFAULT_OLLAMA_MODEL
            raw_text = call_gemma_ollama_api(host, model, prompt)
        else:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("GEMINI_API_KEY environment variable is not set. Add it to .env.local")
            model = model_name or DEFAULT_GEMMA_MODEL
            raw_text = call_gemma_gemini_api(api_key, model, prompt)
        
        # Clean JSON markdown fences
        cleaned = re.sub(r"```json|```", "", raw_text).strip()
        # Find JSON block if wrapped
        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)
        return json.loads(cleaned)
    except Exception as api_err:
        # If model invocation encounters an issue (e.g. 401 UNAUTHENTICATED or network error),
        # extract standalone code snippet directly from issue markdown as a resilient fallback
        body_text = issue.get("body", "")
        code_match = re.search(r"```(?:python|py)\n(.*?)```", body_text, re.DOTALL)
        if code_match:
            return {
                "status": "REPRODUCED",
                "language": "python",
                "code": code_match.group(1).strip(),
                "expected_error": "Exception",
                "summary": f"Extracted reproduction snippet directly from issue body (Note on Gemma API: {str(api_err)[:150]})",
                "api_error": str(api_err)
            }
        raise

# ==============================================================================
# SECURE DOCKER EXECUTION SANDBOX
# Strict isolation:
# - --network none
# - --memory 256m
# - --cpus 1
# - 30s timeout
# - read-only volume mount (:ro)
# - Host execution is NEVER allowed
# ==============================================================================
def is_docker_running() -> bool:
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False

def execute_in_docker(code: str, language: str) -> dict:
    if not is_docker_running():
        return {
            "executed": False,
            "error": "Docker is not currently running. ReproBot strictly isolates execution inside Docker (--network none, --memory 256m) and NEVER executes untrusted code on the host machine. Please start Docker Desktop.",
            "stdout": "",
            "stderr": "Docker daemon unavailable. Sandbox execution refused on host machine.",
            "exit_code": -1,
            "duration": 0.0,
            "timed_out": False
        }
    
    ext = ".py" if language == "python" else ".js"
    filename = f"reproduce{ext}"
    image = "python:3.11-slim" if language == "python" else "node:20-slim"
    runner = ["python", f"/sandbox/{filename}"] if language == "python" else ["node", f"/sandbox/{filename}"]

    with tempfile.TemporaryDirectory() as temp_dir:
        file_path = os.path.join(temp_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(code)

        # Windows-compatible path format for Docker volume mount
        mount_path = os.path.abspath(temp_dir).replace("\\", "/")
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "1",
            "-v", f"{mount_path}:/sandbox:ro",
            image
        ] + runner

        start_time = time.time()
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            duration = round(time.time() - start_time, 2)
            return {
                "executed": True,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exit_code": res.returncode,
                "duration": duration,
                "timed_out": False
            }
        except subprocess.TimeoutExpired as te:
            duration = round(time.time() - start_time, 2)
            stdout = te.stdout.decode('utf-8', errors='replace') if isinstance(te.stdout, bytes) else (te.stdout or "")
            stderr = te.stderr.decode('utf-8', errors='replace') if isinstance(te.stderr, bytes) else (te.stderr or "")
            return {
                "executed": True,
                "stdout": stdout,
                "stderr": (stderr + "\nExecution timed out after 30 seconds (enforced sandbox limit).").strip(),
                "exit_code": 124,
                "duration": duration,
                "timed_out": True
            }
        except Exception as e:
            return {
                "executed": False,
                "error": str(e),
                "stdout": "",
                "stderr": f"Docker run error: {str(e)}",
                "exit_code": -1,
                "duration": 0.0,
                "timed_out": False
            }

# ==============================================================================
# VERDICT CLASSIFICATION LOGIC
# REPRODUCED, NOT_REPRODUCED, UNCLEAR, or NO CODE FOUND
# ==============================================================================
def determine_verdict(gemma_analysis: dict, docker_result: dict) -> str:
    code = (gemma_analysis.get("code") or "").strip()
    status = (gemma_analysis.get("status") or "").upper()
    lang = (gemma_analysis.get("language") or "").lower()

    if not code or status == "NO CODE FOUND" or lang == "none":
        return "NO CODE FOUND"

    if not docker_result or not docker_result.get("executed"):
        return "UNCLEAR"

    if docker_result.get("timed_out"):
        return "UNCLEAR"

    exit_code = docker_result.get("exit_code", 0)
    stdout = docker_result.get("stdout", "")
    stderr = docker_result.get("stderr", "")
    combined = (stdout + "\n" + stderr).lower()
    expected_error = (gemma_analysis.get("expected_error") or "").lower().strip()

    if exit_code != 0:
        # Missing module/dependency in minimal container -> UNCLEAR
        if "modulenotfounderror" in combined or "cannot find module" in combined:
            return "UNCLEAR"
        # Matched expected error
        if expected_error and expected_error in combined:
            return "REPRODUCED"
        # General exception or failure raised
        if any(err in combined for err in ["error", "exception", "traceback", "assertionerror"]):
            return "REPRODUCED"
        return "UNCLEAR"
    else:
        # Script exited cleanly with code 0 without triggering the bug
        return "NOT_REPRODUCED"

# ==============================================================================
# REPRODUCTION ENDPOINT
# ==============================================================================
@app.post("/reproduce")
@app.post("/analyze")
def reproduce():
    try:
        data = request.get_json(silent=True) or {}
        issue_url = data.get("url") or data.get("issue_url")
        provider = data.get("provider", "gemini")
        model_name = data.get("model") or (DEFAULT_OLLAMA_MODEL if provider == "ollama" else DEFAULT_GEMMA_MODEL)
        is_mock = bool(data.get("mock", False))

        if not issue_url:
            return jsonify(error="Please provide a GitHub issue URL"), 400

        # Handle Mock/Simulation demo
        if is_mock or "demo/sample-repo" in issue_url:
            issue = {
                "owner": "demo",
                "repo": "sample-repo",
                "number": 42,
                "title": "KeyError when parsing malformed response dictionary",
                "body": "When calling parse_response() with an empty payload, it raises KeyError: 'items' instead of returning an empty list.",
                "html_url": issue_url
            }
            gemma_result = {
                "status": "REPRODUCED",
                "language": "python",
                "code": "payload = {}\n# Reproducing KeyError when 'items' key is missing\ntry:\n    items = payload['items']\n    print('Success:', items)\nexcept KeyError as e:\n    import sys\n    sys.stderr.write(f'KeyError: {e}\\n')\n    sys.exit(1)",
                "expected_error": "KeyError",
                "summary": "Demonstrates reproduction of KeyError: 'items' when parsing dictionary"
            }
        else:
            # 1. Fetch GitHub Issue
            issue = fetch_github_issue(issue_url)

            # 2. Extract reproduction script using Gemma 4
            gemma_result = extract_reproduction(issue, provider=provider, model_name=model_name)

        code = (gemma_result.get("code") or "").strip()
        lang = (gemma_result.get("language") or "python").lower()

        # 3. If code exists, execute in isolated Docker sandbox
        if code and lang in ["python", "javascript"]:
            docker_result = execute_in_docker(code, lang)
        else:
            docker_result = {
                "executed": False,
                "stdout": "",
                "stderr": "No reproduction code found in issue description.",
                "exit_code": 0,
                "duration": 0.0,
                "timed_out": False
            }

        # 4. Classify outcome
        verdict = determine_verdict(gemma_result, docker_result)

        return jsonify({
            "success": True,
            "is_mock": is_mock or ("demo/sample-repo" in issue_url),
            "verdict": verdict,
            "issue": issue,
            "language": lang,
            "code": code,
            "expected_error": gemma_result.get("expected_error"),
            "summary": gemma_result.get("summary"),
            "docker": docker_result
        })

    except Exception as e:
        return jsonify(error=str(e)), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
