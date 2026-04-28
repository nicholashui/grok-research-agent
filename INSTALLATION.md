# Installation Guide (grok-research-agent)

This guide installs `grok-research-agent` locally and configures it to run without committing any API keys.

## Requirements

- Python 3.11+
- Git
- A Grok (xAI) API key

## 1) Clone the repository

```bash
git clone https://github.com/nicholashui/grok-research-agent.git
cd grok-research-agent
```

## 2) Create and activate a virtual environment

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

## 3) Install the package (recommended)

Install in editable mode:

```bash
pip install -e .
```

Install with dev dependencies (for running tests):

```bash
pip install -e ".[dev]"
```

Verify the CLI is available:

```bash
grok-research-agent --help
```

If you see a warning that the script was installed but is not on your `PATH`, you have two options:

- Run via module:
  ```bash
  python -m grok_research_agent.cli --help
  ```
- Add your Python user bin directory to `PATH` (location varies by OS/Python install).

## 4) Configure your Grok API key (do not commit it)

Create a `.env` file in the repo root:

```bash
cat > .env << 'EOF'
GROK_API_KEY=xai-your-api-key-here
GROK_MODEL=grok-3
EOF
```

Notes:

- `.env` is ignored by git in this repo, so it will not be pushed to GitHub.
- You can also set `GROK_API_KEY` via environment variables instead of `.env`.

## 5) Run a session

Start a new session:

```bash
grok-research-agent start --topic "Your topic here" --focus "optional focus"
```

Resume a session by id:

```bash
grok-research-agent resume --session-id <session-id>
```

List sessions:

```bash
grok-research-agent list-sessions
```

Optional: store sessions in a custom directory:

```bash
grok-research-agent start --sessions-dir /path/to/research_sessions --topic "Your topic"
```

## 6) Knowledge compilation (optional)

Compile a structured knowledge base for an existing session:

```bash
grok-research-agent compile --session-id <session-id> --type auto-hypergraph
```

Generate a backward drill pack:

```bash
grok-research-agent drill --session-id <session-id> --mode backward
```

Feed a new document into a session:

```bash
grok-research-agent feed --session-id <session-id> --new-doc /path/to/doc.md
```

Generate Mermaid output for the hypergraph:

```bash
grok-research-agent show --session-id <session-id>
```

## 7) Run tests

```bash
pytest -q
```

## Troubleshooting

- **“Missing GROK_API_KEY”**
  - Ensure `.env` exists in the repo root and contains `GROK_API_KEY=...`, or export `GROK_API_KEY` in your shell.
- **Command not found: `grok-research-agent`**
  - Use `python -m grok_research_agent.cli --help`, or ensure the Python scripts directory is on `PATH`.
- **SSL / network errors during extraction**
  - Some sources block automated fetching; try different sources during curation or rerun later.
