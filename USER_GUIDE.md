# User Guide: grok-research-agent

`grok-research-agent` is a Python CLI that automates an 8-phase research workflow using the Grok (xAI) API. It turns raw topics into complete, citation-rich Markdown research reports while keeping you in control at four critical human-in-the-loop checkpoints. It also supports structured knowledge compilation (hypergraph + core concepts) and backward drill packs for studying.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Configuration](#2-configuration)
3. [Quick Start](#3-quick-start)
4. [Commands Reference](#4-commands-reference)
5. [Global Flags](#5-global-flags)
6. [The 8-Phase Workflow](#6-the-8-phase-workflow)
7. [Knowledge Compilation Commands](#7-knowledge-compilation-commands)
8. [Output Folder Structure](#8-output-folder-structure)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Installation

**Requirements:** Python 3.11+, Git, and a Grok (xAI) API key.

```bash
# Clone the repository
git clone https://github.com/nicholashui/grok-research-agent.git
cd grok-research-agent

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .\.venv\Scripts\Activate.ps1    # Windows (PowerShell)

# Install in editable mode
pip install -e .

# Verify the CLI is available
grok-research-agent --help
```

> **Note:** If you see a warning that the script is not on your `PATH`, either run via module (`python -m grok_research_agent.cli --help`) or add the Python user bin directory to your `PATH`.

---

## 2. Configuration

Create a `.env` file in the project root (it is git-ignored and will never be committed):

```env
GROK_API_KEY=xai-your-api-key-here
GROK_MODEL=grok-3
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROK_API_KEY` | ✅ Yes | — | Your xAI Grok API key |
| `GROK_MODEL` | No | `grok-3` | Model name to use for all LLM calls |

Alternatively, you can export the key as a shell environment variable instead of using `.env`.

---

## 3. Quick Start

```bash
# 1. Start a new research session
grok-research-agent start --topic "What is Harness Engineering on AI?" \
    --focus "definitions, key papers 2025-2026, real-world implementations"

# The CLI prints a session ID, e.g.: what-is-harness-engineering-on-ai-20260520

# 2. Follow the prompts, then resume to advance through each phase
grok-research-agent resume --session-id what-is-harness-engineering-on-ai-20260520

# 3. Continue resuming after each human checkpoint until the session is complete
grok-research-agent resume --session-id what-is-harness-engineering-on-ai-20260520

# 4. List all sessions at any time
grok-research-agent list-sessions
```

---

## 4. Commands Reference

### `start` — Begin a new session

```bash
grok-research-agent start --topic "<topic>" [--focus "<focus>"] [--mode report|compiler|drill]
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--topic` | ✅ Yes | — | The research topic |
| `--focus` | No | — | Optional focus area to narrow scope |
| `--mode` | No | `report` | Session mode: `report`, `compiler`, or `drill` |

**Example:**
```bash
grok-research-agent start --topic "MIT 6.824 Distributed Systems" --mode compiler
```

---

### `resume` — Continue an existing session

Picks up at the current phase and runs until the next human checkpoint or completion.

```bash
grok-research-agent resume --session-id <session-id>
```

---

### `list-sessions` — List all sessions

```bash
grok-research-agent list-sessions [--sessions-dir <path>]
```

---

### `update` — Refresh discovery sources

Re-runs the discovery phase to find new sources since the last run, then resets to Phase 2 so you can re-curate.

```bash
grok-research-agent update --session-id <session-id>
```

---

### `synthesize` — Force a synthesis step

Generates a new draft from the current notebook regardless of the current phase.

```bash
grok-research-agent synthesize --session-id <session-id>
```

---

### `generate-images` — Create image prompts

Reads `FINAL_REPORT.md` and generates `images_to_generate.md` with Grok Imagine-style prompts.

```bash
grok-research-agent generate-images --session-id <session-id>
```

---

### `youtube-script` — Generate a YouTube narration script

Produces a narration script from `FINAL_REPORT.md`, suitable for YouTube or podcast content.

```bash
grok-research-agent youtube-script --session-id <session-id>
```

---

### `compile` — Build a structured knowledge base

Compiles the session notebook (or extractions) into a hypergraph and core concepts.

```bash
grok-research-agent compile --session-id <session-id> [--type auto-hypergraph]
```

**Outputs** (under `knowledge_base/`):
- `hypergraph.json`
- `auto_types/auto_hypergraph.json`
- `core_concepts.json`

---

### `drill` — Generate a backward drill pack

Builds a study-ready drill pack from core concepts. Runs `compile` automatically if needed.

```bash
grok-research-agent drill --session-id <session-id> [--mode backward]
```

**Outputs** (under `knowledge_base/`):
- `drill_pack.md`
- `drill_questions.json`

---

### `feed` — Add a new document to an existing session

Copies a document into the session and updates the hypergraph with new information.

```bash
grok-research-agent feed --session-id <session-id> --new-doc /path/to/doc.md
```

**Outputs:** Updated `knowledge_base/hypergraph.json` and `auto_types/auto_hypergraph.json`.

---

### `show` — Export hypergraph as Mermaid diagram

Generates a Mermaid `.mmd` file for quick visualization. Requires `compile` to have been run first.

```bash
grok-research-agent show --session-id <session-id>
```

**Output:** `knowledge_base/hypergraph.mmd`

---

### `list-types` — List available knowledge compilation types

```bash
grok-research-agent list-types
```

Currently outputs: `auto-hypergraph`

---

## 5. Global Flags

These flags are supported by all commands that take a `--session-id` or run the workflow:

| Flag | Description |
|---|---|
| `--sessions-dir <path>` | Directory to store sessions (default: `<cwd>/research_sessions`) |
| `--auto` | Auto-accept all human-in-the-loop prompts and run the workflow to completion without pausing |
| `--auto-full-collection all\|none` | In `--auto` mode, whether to save full offline copies of sources at Phase 6 (default: `all`) |
| `--trace-llm` | Print LLM request/response payloads to the console (truncated) |
| `--trace-llm-max-chars <n>` | Max characters to print per LLM trace entry (default: `2000`) |

**Example — fully automated run:**
```bash
grok-research-agent start --topic "Transformer architecture" --auto --auto-full-collection none
```

---

## 6. The 8-Phase Workflow

The tool advances through 8 phases. **Four phases require your input** (marked H0–H3). Use `resume` after each human step to continue.

---

### Phase 0 — Scope Confirmation (H0: Human Input Required)

Grok generates a refined scope proposal from your topic and focus.

**Your input:**
- `yes` — Accept and advance to Phase 1.
- `edit` — Open the scope in `$EDITOR` to modify it before confirming.
- `cancel` — Abort the session.

---

### Phase 1 — Discovery (Automated)

Grok searches for academic papers, documentation, talks, and blogs, producing a prioritized Markdown table of candidate URLs saved as `01_discovery_table.md`.

**Next step:** Run `resume` to proceed to curation.

---

### Phase 2 — Curation & Gap Check (H1: Human Input Required)

The tool prints the discovered sources in a table.

**Your input:**
- `all` — Keep all sources.
- `1,3,4` — Keep only sources 1, 3, and 4.
- `remove 2,5` — Remove sources 2 and 5 from the list.
- `add <url1> <url2>` — Add additional URLs manually.
- `gap` — Ask Grok to analyze the list for missing subtopics.
- `approve` — Finalize your selection and advance to Phase 3.

---

### Phase 3 — Extraction (Automated)

Fetches raw content from each approved URL and asks Grok to extract key definitions, quotes, and architectures. Individual fetch failures are logged as warnings; the run continues with remaining sources.

**Outputs:** `03_extraction_plan.md` and `03_extracted/<nnn>.md` for each source.

**Next step:** Run `resume` to proceed.

---

### Phase 4 — Master Notebook (Automated)

Merges all extractions into a grouped `04_master_notebook.md`, highlighting contradictions and cross-references.

**Next step:** Run `resume` to proceed.

---

### Phase 5 — Synthesis (H2: Human Input Required)

Grok drafts an executive summary and report sections with inline citations, saved as `05_draft_vX.md`.

**Your input:**
- `approve` — Accept the draft and advance to Phase 6.
- Any other text — Provide revision feedback; Grok rewrites the draft as the next version.

---

### Phase 6 — Full Collection (H3: Human Input Required)

The tool asks if you want full offline Markdown copies of specific sources saved locally.

**Your input:**
- `all` — Save all sources.
- `none` — Skip this step.
- `1,3` — Save only the specified sources.

---

### Phase 7 — Final Polish (Automated)

Grok generates `FINAL_REPORT.md` with a full TOC, glossary, and reference list. Also writes `images_to_generate.md`.

---

### Phase 8 — Complete

The session is marked as complete. No further automatic actions are taken. You can still run `compile`, `drill`, `feed`, `show`, `generate-images`, and `youtube-script` on the completed session.

---

## 7. Knowledge Compilation Commands

These commands can be run on any session that has reached at least Phase 3 (extractions) or Phase 4 (notebook).

| Command | Input | Output |
|---|---|---|
| `compile` | `04_master_notebook.md` or `03_extracted/*.md` | `hypergraph.json`, `core_concepts.json` |
| `drill` | `core_concepts.json` (auto-compiles if missing) | `drill_pack.md`, `drill_questions.json` |
| `feed` | `--new-doc` path | Updated `hypergraph.json` |
| `show` | `hypergraph.json` | `hypergraph.mmd` |

**Typical knowledge compilation workflow:**
```bash
# After your session is complete:
grok-research-agent compile --session-id <session-id>
grok-research-agent drill   --session-id <session-id>
grok-research-agent show    --session-id <session-id>
```

---

## 8. Output Folder Structure

All research is saved locally under `research_sessions/` (or your custom `--sessions-dir`).

```
research_sessions/
└── <topic-slug>-<date>/
    ├── session.json                 # Session state (phase, topic, etc.)
    ├── 00_scope_confirmed.md
    ├── 01_discovery_table.md
    ├── 02_curated_sources.json
    ├── 03_extracted/
    │   ├── 001.md
    │   └── 002.md
    ├── 04_master_notebook.md
    ├── 05_draft_v1.md
    ├── FINAL_REPORT.md
    ├── images_to_generate.md
    ├── knowledge_base/
    │   ├── hypergraph.json
    │   ├── hypergraph.mmd
    │   ├── core_concepts.json
    │   ├── drill_pack.md
    │   ├── drill_questions.json
    │   ├── auto_types/
    │   │   └── auto_hypergraph.json
    │   └── feed_docs/               # Documents added via `feed`
    └── runs/                        # Per-run backups of intermediate artifacts
        └── <run_id>/
```

---

## 9. Troubleshooting

| Problem | Solution |
|---|---|
| `Missing GROK_API_KEY` | Ensure `.env` contains `GROK_API_KEY=...` in the project root, or export it as a shell variable |
| `command not found: grok-research-agent` | Run via `python -m grok_research_agent.cli` or add the Python scripts directory to `PATH` |
| SSL / network errors during extraction | Some sites block automated fetching; remove failing URLs during curation (Phase 2) or retry later |
| `curated sources JSON is not a list` | Manually edit `02_curated_sources.json` in the session folder to ensure it is a JSON array, then resume |
| Session stuck at a phase | Check the session folder for the expected output file; if it is missing or malformed, delete it and resume |
| API quota error | The run stops and prints an error; wait for quota to reset, then resume — no progress is lost |
