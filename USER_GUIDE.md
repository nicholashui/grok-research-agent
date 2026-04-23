# Grok-Powered Research Workflow Automation Tool

Welcome to `grok-research-agent`, a powerful Python CLI that automates an 8-phase research workflow using the Grok (xAI) API. It turns raw topics into complete, citation-rich Markdown research reports while keeping you strictly in the loop at exactly four critical human interaction points.

## Features
- **Automated Discovery**: Parallel reasoning to find sources across web, arXiv, GitHub, and more.
- **Human-in-the-Loop**: You retain full control over scope, source curation, draft synthesis, and offline collection.
- **Living Knowledge Base**: Automatically extracts and merges source data into a single master notebook.
- **Session Management**: Supports saving and resuming sessions, so your research can span multiple runs.
- **Markdown Export**: Everything is output as clean, usable Markdown files.

---

## 1. Installation

This project requires **Python 3.11+**.

1. **Clone the repository** (or navigate to the project directory):
   ```bash
   cd grok-research-agent
   ```
2. **Install in editable mode**:
   ```bash
   python -m pip install -e .
   ```
3. **Verify the installation**:
   ```bash
   grok-research-agent --help
   ```

*(Note: If your system warns that the installation path is not on your `PATH`, you may need to add it, e.g., `export PATH="$HOME/.local/bin:$PATH"`).*

---

## 2. Configuration

The tool relies exclusively on the **Grok API** (xAI) as its LLM backend.

1. Create a `.env` file in the root of the project:
   ```bash
   touch .env
   ```
2. Add your Grok API key and model preference:
   ```env
   GROK_API_KEY=xai-your-api-key-here
   GROK_MODEL=grok-3
   ```

---

## 3. Command-Line Usage

### Starting a New Session
To begin a new research topic, use the `start` command. You can provide an optional `--focus` flag to narrow the scope.

```bash
grok-research-agent start --topic "What is Harness Engineering on AI?" --focus "definitions, key papers 2025-2026, real-world implementations"
```
*The CLI will output a session ID (e.g., `what-is-harness-engineering-on-ai-20260326`).*

### Resuming a Session
Because the tool stops at explicit human-in-the-loop steps, you will frequently use the `resume` command to advance to the next phase.

```bash
grok-research-agent resume --session-id what-is-harness-engineering-on-ai-20260326
```

### Managing Sessions
To see a list of all your active or past research sessions:
```bash
grok-research-agent list-sessions
```

### Other Commands
- **Force Synthesis**: Generate a draft at any time from your current notebook.
  ```bash
  grok-research-agent synthesize --session-id <your-session-id>
  ```
- **Generate Images**: Create Grok Imagine prompts based on your final report.
  ```bash
  grok-research-agent generate-images --session-id <your-session-id>
  ```
- **Update Sources**: Re-run discovery for new sources since your last run.
  ```bash
  grok-research-agent update --session-id <your-session-id>
  ```

---

## 4. The 8-Phase Workflow

The tool guides you through 8 distinct phases. **Four of these phases require human input (H0 - H3)**, ensuring you direct the research without being bogged down by manual extraction.

### Phase 0: Quick Scope Confirmation (Human Step H0)
- **What happens**: Grok generates a refined scope summary based on your topic.
- **Your input**: The tool prompts: `Do you confirm this scope? (yes/edit/cancel)`. 
  - Reply `yes` to proceed.
  - Reply `edit` to open the scope in your default `$EDITOR` to modify it before confirming.

### Phase 1: AI-Led Comprehensive Discovery (Automated)
- **What happens**: Grok searches for academic papers, docs, talks, and blogs, returning a prioritized Markdown table of URLs.
- **Next step**: Run `resume` to proceed.

### Phase 2: Collaborative Curation & Gap Check (Human Step H1)
- **What happens**: The tool prints the discovered sources in a table.
- **Your input**: 
  - Select sources to keep by entering numbers (e.g., `1,3,4`), `all`, or remove some (`remove 2,5`).
  - You can type `gap` to have Grok analyze the list for missing subtopics.
  - Type `approve` to finalize your selection.

### Phase 3: Targeted Extraction (Automated)
- **What happens**: The tool automatically fetches the raw content of your approved URLs and uses Grok to extract key definitions, quotes, and architectures.
- **Next step**: Run `resume` to proceed.

### Phase 4: Iterative Note-Taking (Automated)
- **What happens**: All extractions are merged into a grouped `04_master_notebook.md`, highlighting contradictions and cross-references.
- **Next step**: Run `resume` to proceed.

### Phase 5: Periodic Synthesis & Gap Analysis (Human Step H2)
- **What happens**: Grok drafts an executive summary and report sections with inline citations.
- **Your input**: Review the generated `05_draft_vX.md`. Reply with:
  - `approve` to accept the draft.
  - `revise <section> <feedback>` to have Grok rewrite specific parts.
  - `add-section "Title"` to request a new section.

### Phase 6: Selective Full Collection (Human Step H3)
- **What happens**: The tool asks if you want full, raw Markdown copies of specific sources saved locally.
- **Your input**: Reply with source numbers, `all`, or `none`.

### Phase 7 & 8: Final Polish & Versioning (Automated)
- **What happens**: Grok generates the `FINAL_REPORT.md` complete with a TOC, glossary, and reference list. The session is marked as complete.

---

## 5. Output Folder Structure

All research is saved locally in the `research_sessions` directory. A completed session looks like this:

```
research_sessions/
└── <topic-slug>-<date>/
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
    └── runs/                   # Backups of intermediate states per run
```

Happy researching!
