# Kerno 🧭
### AI-Powered Open-Source Contribution Guide for Beginners

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![Framework: Flask](https://img.shields.io/badge/Framework-Flask%203.x-black.svg)](https://flask.palletsprojects.com/)
[![AI Model: Gemma 4](https://img.shields.io/badge/AI%20Model-Gemma%204%20(gemma--4--31b--it)-indigo.svg)](https://ai.google.dev/gemma)

> **Kerno** is an AI-powered open-source contribution guide that helps developers understand unfamiliar GitHub repositories quickly. Users paste a public repository URL to receive a project overview, explanations of important files, setup guidance based on repository contents, and AI-generated suggestions for beginner-friendly contribution areas.
>
> The application uses the GitHub REST API to retrieve repository information and Gemma to explain the project in simple language. It is built with Python, Flask, HTML, CSS, and JavaScript, with the goal of making open-source development more accessible to students and new contributors.
>
> **Exact Gemma Model Identifier:** `gemma-4-31b-it` (Google Gemma 4 31B Instruction-Tuned model via Google Gemini API).

---

## 📌 Problem

Newcomers to open-source software face overwhelming friction when trying to make their first contribution:
1. **Unfamiliar Architectures:** Repositories often have hundreds of files without a clear explanation of where execution begins or what each folder does.
2. **Ambiguous Local Setup:** Setup instructions in READMEs are frequently outdated, platform-specific, or assume prior tribal knowledge.
3. **Paralysis in Finding Tasks:** Beginners do not know where to start or how to match their current skills with safe, productive contribution areas.
4. **Hallucinated or Generic AI Advice:** Generic chatbots often fabricate nonexistent files, suggest outdated command-line flags, or invent imaginary open issues.

---

## 💡 Solution

**Kerno** bridges this gap by combining **deterministic repository truth** with **grounded Gemma 4 synthesis**:
- A developer simply pastes any public GitHub repository link (e.g., `https://github.com/pallets/flask` or `expressjs/express`).
- Kerno connects to the GitHub REST API to extract verified repository facts: languages, stars, license, root directory trees, community health files, and build manifests (such as `pyproject.toml`, `package.json`, or `Cargo.toml`).
- Google's **Gemma 4** (`gemma-4-31b-it`) processes this verified ground truth under strict grounding rules to produce plain-English architectural explanations, identify critical files, generate copy-pasteable setup instructions, and highlight beginner-friendly contribution avenues.
- Facts and AI synthesis are strictly separated: users always know which details are verified GitHub facts and which are AI-generated suggestions.

---

## ✨ Features

- **Instant Repository Ingestion:** Accepts full GitHub URLs (`https://github.com/owner/repo`), subpage links, or `owner/repo` shorthands.
- **Verified Repository Overview:** Displays real-time GitHub stars, forks, open issue counts, default branch, SPDX license badge, and language breakdown with percentage bars.
- **Plain-English Project Purpose:** Explains the project's real-world purpose and core architecture in accessible language without technical jargon.
- **Important Files Directory Guide:** Identifies critical project files and configuration manifests from the repository root, explaining the role of each file and providing direct GitHub links.
- **Verified Setup & Run Instructions:** Derives environment creation, dependency installation, and test suite commands directly from actual project manifests (e.g., `pip install -r requirements.txt`, `npm install`, or `cargo test`), complete with one-click copy buttons.
- **Beginner Contribution Opportunities:** Proposes grounded contribution areas (documentation clarity, test coverage, issue reproduction, examples) backed by concrete repository evidence.
- **Transparent AI Disclaimer:** Explicitly marks AI recommendations as exploratory avenues to investigate rather than verified open issues.
- **Interactive First-Time Checklist:** Built-in interactive checklist for beginners tracking fork, clone, branch, test, and pull request workflows.
- **Helpful External Links:** Direct links to official open-source guides, Good First Issue trackers, and Git documentation.
- **Graceful Degradation:** If API limits are reached or an API key is missing, Kerno falls back to a deterministic rule-based analysis without crashing.

---

## 🤖 Exact Gemma Model Used & How Gemma Contributes

### Verified Model Identifier: `gemma-4-31b-it`
Kerno uses Google's **Gemma 4** instruction-tuned model, accessed via the Google Gemini API (`generativelanguage.googleapis.com`):
- **Model Name:** Gemma 4 31B IT
- **Model ID:** `gemma-4-31b-it`
- **Alternative Supported:** `gemma-4-26b-a4b-it` (Gemma 4 26B MoE IT)
- **SDK:** `google-genai` Python SDK (`genai.Client`)

### How Gemma Contributes:
1. **Strict Grounding:** Gemma 4 is fed a structured prompt containing only verified ground truth extracted from GitHub (description, root file listing, detected manifests, and README excerpt).
2. **Hallucination Prevention:** The system prompt explicitly forbids inventing files, tools, flags, or features not present in the input facts.
3. **Cognitive Synthesis:** Gemma 4 translates dense code manifests and developer READMEs into plain, welcoming English tailored for a junior contributor.
4. **Structured JSON Output:** The model is constrained to return a predictable JSON schema validated by the backend before reaching the dashboard.

---

## 🏗️ Architecture

```
                                  +-----------------------------+
                                  |   User Browser (Dashboard) |
                                  +--------------+--------------+
                                                 |
                                         HTTP POST /api/analyze
                                                 |
                                                 v
                                  +-----------------------------+
                                  |     Flask Application       |
                                  |          (app.py)           |
                                  +------+---------------+------+
                                         |               |
               1. Fetch Facts & Manifests|               | 2. Grounded Prompt
                                         v               v
                        +--------------------+   +-----------------------+
                        |   GitHub REST API  |   |   Google Gemini API   |
                        | (api.github.com)   |   |   (gemma-4-31b-it)    |
                        +--------------------+   +-----------------------+
                                         |               |
                                         +-------+-------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  | Structured Response & UI    |
                                  | (Facts + Gemma 4 Guide)     |
                                  +-----------------------------+
```

---

## 💻 Windows Setup & Installation

Follow these steps to set up and run Kerno on Windows (PowerShell or Command Prompt):

### Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14 installed and on your `PATH`.
- Git installed.

### 1. Clone or Open the Repository
```powershell
cd c:\Users\ADMIN\Downloads\anti
```

### 2. Create and Activate a Python Virtual Environment
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy the example environment file:
```powershell
Copy-Item .env.example .env
```
Edit `.env` using your preferred text editor (e.g., `notepad .env`) and add your API keys:
```env
GEMINI_API_KEY=AIzaSy...
GEMMA_MODEL=gemma-4-31b-it
GITHUB_TOKEN=ghp_...
PORT=5000
```

---

## 🔑 Environment Variables Reference

| Variable | Description | Required? | Default / Notes |
|---|---|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key used for Gemma 4 calls. | Recommended | Free tier available at [Google AI Studio](https://aistudio.google.com/). |
| `GEMMA_MODEL` | The verified Gemma 4 model identifier. | Optional | `gemma-4-31b-it` (or `gemma-4-26b-a4b-it`). |
| `GITHUB_TOKEN` | GitHub Personal Access Token. | Optional | Increases GitHub API rate limit from 60 to 5,000 req/hr. |
| `PORT` | Local web server port. | Optional | `5000` |
| `FLASK_DEBUG` | Enable Flask auto-reloading during development. | Optional | `false` |

---

## 🚀 Launch Instructions

### Start the Web Application
```powershell
python app.py
```
You will see output similar to:
```
Kerno running on http://127.0.0.1:5000
 * Serving Flask app 'app'
 * Running on all addresses (0.0.0.0)
 * Running on http://127.0.0.1:5000
```

Open your browser and navigate to:
**`http://127.0.0.1:5000`**

### Running the Test Suite
Kerno includes a full test suite covering URL parsing, manifest detection, heuristic fallbacks, and Flask endpoints:
```powershell
python -m pytest tests/test_kerno.py -v
```

---

## ⚠️ Limitations

- **Exploratory Opportunities vs. Live GitHub Issues:** The contribution areas suggested by Gemma 4 are exploratory hypotheses based on repository structure (e.g. missing documentation files, testing gaps, example code). They are **not** verified open GitHub issues or triaged bugs. Contributors must always check the repository's open issues and discuss ideas with maintainers first.
- **GitHub API Rate Limits:** Without a `GITHUB_TOKEN`, the unauthenticated GitHub REST API is capped at 60 requests per hour per IP. Adding a free personal access token in `.env` increases the limit to 5,000 requests per hour.
- **Large Monorepos:** For massive repositories, only the root directory tree and top-level manifests are scanned for context to ensure low latency and adhere to token limits.
- **Private Repositories:** Kerno is specifically designed for public open-source repositories; private repositories are not supported.

---

## 📄 License

This project is licensed under the terms of the **MIT License**. See the [LICENSE](LICENSE) file for full details.
