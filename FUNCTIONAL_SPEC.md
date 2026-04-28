# Functional Specification: grok-research-agent

## 1) Purpose

`grok-research-agent` is a local-first Python CLI that:

- Runs an 8-phase research workflow to produce a citation-oriented Markdown report.
- Persists work as resumable “sessions” with per-run artifacts.
- Optionally compiles structured knowledge outputs (hypergraph + core concepts) and produces a backward drill pack for study.

The system is designed to keep the user in control via explicit human-in-the-loop checkpoints while automating web discovery, extraction, synthesis, and structured compilation.

## 2) Scope

### In Scope

- CLI commands for creating, resuming, and managing sessions.
- Session persistence to a local folder (`research_sessions/` by default).
- Web fetching and readability extraction for curated URLs.
- Grok (xAI) LLM usage via OpenAI-compatible API for generating all artifacts.
- Knowledge compilation commands (`compile`, `drill`, `feed`, `show`, `list-types`) that operate on an existing session’s materials.

### Out of Scope (Current Implementation)

- Rich visualizations beyond Mermaid text output.
- Full Hyper-Extract-style templating catalog (only a small set of prompt templates is included).
- Automatic “auto-type” classification of documents in discovery/curation phases.
- Local LLM backend support.

## 3) User Personas & Primary Use Cases

### Personas

- **Researcher/Engineer**: wants a structured, citation-rich report from a topic, with control over scope and sources.
- **Student/Exam Prep**: wants a drill pack built from the compiled core concepts.

### Use Cases

- Start a new research session for a topic and iteratively progress through phases.
- Resume the workflow at each checkpoint until completion.
- Update a session’s discovery results to include new sources.
- Compile the session’s notebook into a structured hypergraph and core concepts.
- Generate a backward drill pack from the core concepts.
- Feed new documents into an existing session to evolve the hypergraph.
- Export a Mermaid view for quick visualization.

## 4) Architecture Overview

### Components

- **CLI entrypoint**: parses commands and dispatches to the workflow runner.
- **Workflow runner**: implements the phase state machine and the compile/drill/feed/show operations.
- **Session manager**: creates sessions, loads/saves session state, manages run directories, and manages knowledge base paths.
- **Grok client**: wraps xAI Grok chat completions via OpenAI-compatible API.

### External Dependencies

- Grok API (xAI) via `openai` client with base URL `https://api.x.ai/v1`.
- `requests` + `readability-lxml` for web content fetching and readable extraction.

## 5) Installation & Configuration (Functional Requirements)

### Requirements

- Python 3.11+
- `GROK_API_KEY` must be set either:
  - in a `.env` file at the repository root, or
  - as an environment variable.

### Configuration Variables

- `GROK_API_KEY` (required): xAI Grok API key.
- `GROK_MODEL` (optional): defaults to `grok-3`.

Behavior:

- If `GROK_API_KEY` is missing, the system must refuse to call the API and print a clear error message.

## 6) Command Line Interface

All commands support:

- `--sessions-dir <path>` (optional): folder for sessions (default: `<cwd>/research_sessions`).

### 6.1 `start`

Start a new session.

Arguments:

- `--topic <string>` (required)
- `--focus <string>` (optional)
- `--mode report|compiler|drill` (optional, default: `report`)

Behavior:

- Creates a new session folder.
- Initializes `session.json`.
- Immediately enters the workflow state machine at Phase 0.

Outputs:

- Prints session id to console.
- Creates run artifacts under `runs/<run_id>/`.

### 6.2 `resume`

Resume an existing session at its current phase.

Arguments:

- `--session-id <id>` (required)

Behavior:

- Loads session state.
- Executes the next automated steps until the next human checkpoint or completion.

### 6.3 `list-sessions`

List session ids in `--sessions-dir` that contain `session.json`.

### 6.4 `update`

Refresh discovery results for a session.

Arguments:

- `--session-id <id>` (required)

Behavior:

- Runs discovery with a “since last run” hint.
- Sets the session to Phase 2 and prompts user to resume to curate.

### 6.5 `synthesize`

Force a synthesis step using the current notebook.

Arguments:

- `--session-id <id>` (required)

Behavior:

- Runs the synthesis phase (Phase 5) even if not at that phase.

### 6.6 `generate-images`

Generate image prompts based on the final report.

Arguments:

- `--session-id <id>` (required)

Behavior:

- Reads `FINAL_REPORT.md` and generates `images_to_generate.md`.

### 6.7 `list-types`

Print available knowledge compilation types.

Current output:

- `auto-hypergraph`

### 6.8 `compile`

Compile structured knowledge outputs for a session.

Arguments:

- `--session-id <id>` (required)
- `--type auto-hypergraph` (optional, default: `auto-hypergraph`)

Inputs (priority order):

- `04_master_notebook.md` if present, else merged `03_extracted/*.md` if present.

Outputs (under `knowledge_base/`):

- `hypergraph.json`
- `auto_types/auto_hypergraph.json`
- `core_concepts.json`

### 6.9 `drill`

Generate a backward drill pack for a session.

Arguments:

- `--session-id <id>` (required)
- `--mode backward` (optional, default: `backward`)

Inputs:

- `knowledge_base/core_concepts.json` (if missing, the system attempts `compile` first)

Outputs:

- `knowledge_base/drill_pack.md`
- `knowledge_base/drill_questions.json`

### 6.10 `feed`

Feed a new document into an existing session and update the hypergraph.

Arguments:

- `--session-id <id>` (required)
- `--new-doc <path>` (required)

Behavior:

- Copies the doc into `knowledge_base/feed_docs/` with a timestamp prefix.
- If no existing `hypergraph.json` exists, runs `compile` first.
- Otherwise calls Grok to merge/extend the existing hypergraph.

Outputs:

- Updated `knowledge_base/hypergraph.json`
- Updated `knowledge_base/auto_types/auto_hypergraph.json`

### 6.11 `show`

Generate a Mermaid file for the session hypergraph.

Arguments:

- `--session-id <id>` (required)

Inputs:

- `knowledge_base/hypergraph.json` (requires `compile` to have been run)

Outputs:

- `knowledge_base/hypergraph.mmd`

## 7) Workflow State Machine (8-Phase Research Workflow)

Session state is controlled by `current_phase` (integer) and advanced by the workflow runner.

### Phase 0: Scope (Human Step H0)

- System generates a scope proposal from topic/focus.
- User must choose: `yes`, `edit`, or `cancel`.
- On `yes`: writes `00_scope_confirmed.md` and advances to Phase 1.

### Phase 1: Discovery (Automated)

- System generates a discovery table of candidate sources.
- Writes:
  - `01_discovery_table.md` to the run directory and session root.
- Advances to Phase 2 and prompts user to resume for curation.

### Phase 2: Curation + Gap Check (Human Step H1)

- System displays a preview of discovery results.
- User provides a selection command (e.g., `all`, `1,3,4`, `remove 2,5`, `add <urls>`).
- System produces:
  - `02_curated_sources.json` (run dir + session root)
  - `02_gap_report.md` (run dir)
- User must type `approve` to advance to Phase 3.

### Phase 3: Extraction (Automated)

- For each curated source, system fetches content and asks Grok to extract key information.
- Writes:
  - `03_extraction_plan.md` (run dir)
  - Extracted Markdown: `03_extracted/<nnn>.md` (run dir and session root)
- Advances to Phase 4.

Failure behavior:

- If a fetch fails, the system logs a warning and continues with remaining sources.
- If curated sources JSON is not a list, the system instructs user to fix it and resume.

### Phase 4: Notebook (Automated)

- Merges extractions and generates `04_master_notebook.md` (run dir + session root).
- Advances to Phase 5.

### Phase 5: Synthesis (Human Step H2)

- Generates a draft `05_draft_vX.md` from the notebook.
- User must respond:
  - `approve` to advance to Phase 6, or
  - any other feedback string, which triggers a revision into the next version.

### Phase 6: Full Collection (Human Step H3)

- Prompts user to select sources to save “full offline Markdown copies”.
- Writes chosen sources to:
  - `06_full_sources/<nnn>.md` (run dir + session root)
- Advances to Phase 7.

### Phase 7: Final Polish (Automated)

- Produces:
  - `FINAL_REPORT.md` (run dir + session root)
  - `images_to_generate.md` (run dir + session root)
- Advances to Phase 8 (complete).

### Phase 8: Complete

- No further automatic actions; session is considered finished.

## 8) Data Model & Storage

### 8.1 Session Id

Derived from a slugified topic plus date, ensuring uniqueness by suffixing `-2`, `-3`, etc. if needed.

### 8.2 Session State (`session.json`)

Fields (current implementation):

- `session_id`: string
- `topic`: string
- `focus`: string | null
- `mode`: string (default: `report`)
- `created_at`: ISO timestamp
- `updated_at`: ISO timestamp
- `grok_model`: string (default `grok-3`)
- `current_phase`: integer
- `run_history`: list[string] (reserved; not required for current operation)

### 8.3 Session Folder Layout

Default:

```
research_sessions/
  <session-id>/
    session.json
    runs/
      <run_id>/
        ...phase outputs for that run...
    00_scope_confirmed.md
    01_discovery_table.md
    02_curated_sources.json
    03_extracted/
    04_master_notebook.md
    05_draft_v*.md
    FINAL_REPORT.md
    images_to_generate.md
    knowledge_base/
      auto_types/
        auto_hypergraph.json
      feed_docs/
      hypergraph.json
      hypergraph.mmd
      core_concepts.json
      drill_pack.md
      drill_questions.json
```

### 8.4 Run Directories

Each command invocation creates a unique `runs/<run_id>/` folder based on a timestamp with microseconds to avoid collisions.

## 9) Knowledge Compilation Outputs

### 9.1 AutoHypergraph JSON Schema (MVP)

The system expects a JSON object with:

- `nodes`: list of `{ "id": string, "label": string }`
- `hyperedges` (or `edges`): list of `{ "id": string, "nodes": [string, ...], "relation": string, "evidence": string }`

If the model output is not valid JSON, the system stores a fallback structure:

- `{ "raw": "<model_output>" }`

### 9.2 Core Concepts JSON Schema

`core_concepts.json` stores:

```
{
  "core_concepts": [
    {
      "name": "...",
      "definition": "...",
      "why_load_bearing": "..."
    }
  ]
}
```

### 9.3 Drill Pack Outputs

- `drill_pack.md` contains a study-ready Markdown pack.
- `drill_questions.json` contains structured questions/answers/pitfalls when available.

## 10) Error Handling & UX Requirements

The system must:

- Provide actionable error messages when required inputs are missing (e.g., missing `GROK_API_KEY`, missing notebook/extractions).
- Avoid crashing the entire run when individual URLs fail to fetch; continue with remaining sources.
- Stop at human checkpoints and instruct the user exactly how to proceed (`resume`, `approve`, etc.).

## 11) Security & Privacy Requirements

- API keys must never be written into tracked repository files.
- Local sessions may include fetched page contents; these are stored under `research_sessions/` and should be treated as potentially sensitive.
- `.env` should remain untracked; repository should ignore it.

## 12) Non-Functional Requirements

- **Local-first persistence**: all outputs stored under `--sessions-dir`.
- **Deterministic artifacts**: each phase writes named files so users can inspect and edit manually if needed.
- **Resumability**: workflow can be resumed multiple times across terminal sessions using `resume`.
- **Testability**: workflow runner supports dependency injection for client and HTTP fetch in tests.

## 13) Acceptance Criteria

- Starting a session produces a new session folder with `session.json`.
- Resuming progresses the phase state machine and produces expected artifacts.
- `compile` produces `knowledge_base/hypergraph.json` and `knowledge_base/core_concepts.json` for a session that has a notebook or extractions.
- `drill` produces `knowledge_base/drill_pack.md` and `knowledge_base/drill_questions.json`.
- `feed` copies a new doc into `knowledge_base/feed_docs/` and updates `knowledge_base/hypergraph.json`.
- `show` produces `knowledge_base/hypergraph.mmd` after `compile`.
