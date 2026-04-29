# Test Report: Topic Scenarios (agent skill / agent harness / multi-agent / agentic rag)

## Summary

This report documents end-to-end workflow tests for the following topics:

- `agent skill`
- `agent harness`
- `multi-agent`
- `agentic rag`

The tests validate:

- The 8-phase session workflow completes (Phase 0 → Phase 8) with expected artifacts.
- Knowledge compilation outputs are generated (`compile`, `drill`, `show`).

## Test Environment

- Python: 3.13.0
- Platform: macOS-26.4.1-arm64-arm-64bit-Mach-O
- Test runner: `pytest`

## Test Approach

### Why simulated (mocked) end-to-end tests

The workflow is interactive (human-in-the-loop checkpoints) and depends on external services (Grok API, websites). To make tests repeatable and safe to run locally/CI:

- Grok API calls are simulated using a fake client with deterministic responses.
- Web fetching is simulated (no external network dependency).
- Human inputs (`yes`, `approve`, etc.) are simulated.

This validates system orchestration, state transitions, file outputs, and command wiring. It does not validate real-world answer quality.

### Where the tests live

- Topic-scenario end-to-end test: [test_workflow_happy_path.py](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/tests/test_workflow_happy_path.py#L167-L249)
- Existing baseline workflow test: [test_workflow_happy_path.py](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/tests/test_workflow_happy_path.py#L40-L117)
- Compile + drill output test: [test_workflow_happy_path.py](file:///Users/nicholashui/Documents/research_agent/grok-research-agent/tests/test_workflow_happy_path.py#L120-L164)

## Test Execution

Command executed from repository root:

```bash
pytest -q
```

Result:

```
10 passed in 0.72s
```

## Test Cases

### TC1: End-to-end workflow completes for each topic

**Inputs**

- Topic: one of the 4 topics listed above
- Focus: `definitions`
- Human steps (simulated inputs):
  - H0 scope confirm: `yes`
  - H1 curation: `all`, then `approve`
  - H2 synthesis approval: `approve`
  - H3 full collection: `none`

**Steps**

1. Create session via `SessionManager.create_session(topic, focus)`.
2. Run `WorkflowRunner.run(session_id)` repeatedly to drive Phase 0→8.
3. Verify key workflow artifacts exist in the session directory:
   - `FINAL_REPORT.md`
   - `images_to_generate.md`

**Expected**

- `current_phase == 8`
- Final report and image prompt files exist.

**Actual**

- Pass for all four topics.

### TC2: Knowledge compilation artifacts are generated (`compile`, `drill`, `show`)

**Inputs**

- Session that already reached Phase 8.

**Steps**

1. Run `compile`:
   - `WorkflowRunner.run(session_id, command="compile", compile_type="auto-hypergraph")`
2. Run `drill`:
   - `WorkflowRunner.run(session_id, command="drill", drill_mode="backward")`
3. Run `show`:
   - `WorkflowRunner.run(session_id, command="show")`

**Expected outputs** (under `knowledge_base/`)

- `hypergraph.json`
- `auto_types/auto_hypergraph.json`
- `core_concepts.json`
- `drill_pack.md`
- `drill_questions.json`
- `hypergraph.mmd` (Mermaid)

**Actual**

- Pass for all four topics.

## Results Matrix

| Topic | Workflow to Phase 8 | FINAL_REPORT.md | images_to_generate.md | compile outputs | drill outputs | show (Mermaid) |
|------|----------------------|----------------|------------------------|----------------|--------------|----------------|
| agent skill | PASS | PASS | PASS | PASS | PASS | PASS |
| agent harness | PASS | PASS | PASS | PASS | PASS | PASS |
| multi-agent | PASS | PASS | PASS | PASS | PASS | PASS |
| agentic rag | PASS | PASS | PASS | PASS | PASS | PASS |

## Notes / Limitations

- These tests validate orchestration, persistence, and command wiring using deterministic LLM outputs.
- They do not validate real Grok API behavior, rate limits, or network error conditions from live URLs.
- For a “live” quality evaluation, run the CLI with a real `GROK_API_KEY` and review the generated session artifacts manually.
