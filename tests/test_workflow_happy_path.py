from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import requests
from rich.console import Console

from grok_research_agent.grok_client import GrokTimeoutError
from grok_research_agent.session_manager import SessionManager
from grok_research_agent.workflow_phases import WorkflowContext, WorkflowRunner


class FakeGrokClient:
    def __init__(self, replies: list[str] | None = None, curated: list[dict[str, Any]] | None = None):
        self._replies = list(replies or [])
        self._curated = curated or [
            {
                "title": "Example",
                "url": "https://example.com",
                "type": "blog",
                "why_relevant": "x",
                "credibility": 3,
                "priority": "High",
            }
        ]

    def chat_text(self, *, system: str, user: str, **_: Any) -> str:
        if self._replies:
            return self._replies.pop(0)
        return self._auto_reply(user)

    def prompt_from_file(self, prompt_path: Path) -> str:
        return prompt_path.read_text(encoding="utf-8")

    def render_template(self, template: str, values: dict[str, Any]) -> str:
        text = template
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", str(v))
        return text

    def _auto_reply(self, user: str) -> str:
        lower = user.lower()
        if "youtube" in lower:
            return (
                "# YouTube Script\n\n"
                "## Introduction\n"
                "[beat] Today we’re breaking this down in plain English.\n\n"
                "## Section\n"
                "Here’s the idea, step by step, with simple explanations.\n\n"
                "## Conclusion\n"
                "[pause] That’s the big picture.\n"
            )
        if "comprehensive discovery table" in lower or "return a markdown table exactly in this format" in lower:
            return (
                "| Type | Title | URL | Why Relevant | Credibility (1-5) | Coverage Notes | Priority (High/Med/Low) |\n"
                "| - | - | - | - | - | - | - |\n"
                "| blog | Example | https://example.com | x | 3 | definitions, architecture, limitations | High |"
            )
        if "output json only" in lower:
            return json.dumps(self._curated)
        if "coverage gaps" in lower:
            return "# Gaps\nNone"
        if "detailed extraction plan" in lower:
            return "# Plan\n1. Extract mechanisms, examples, and limitations."
        if "extract detailed, evidence-preserving notes" in lower:
            return (
                "## Coverage Summary\nCaptures the chunk.\n"
                "## Definitions and Terminology\n- Term: detail [1]\n"
                "## Technical Mechanisms and Architecture\n- Mechanism [1]\n"
                "## Process, Workflow, or Algorithm Details\n- Step 1 [1]\n"
                "## Evidence, Examples, Metrics, and Experiments\n- Example [1]\n"
                "## Limitations, Trade-offs, and Critiques\n- Caveat [1]\n"
                "## Open Questions or Missing Details\n- Unknown [1]\n"
                "## Quotable Passages\n- \"Quoted line\" [1]\n"
                "## Extraction Notes\n- Preserved detail [1]\n"
            )
        if "extracting section-specific evidence" in lower:
            return (
                "## Relevant Claims\n- Claim [1]\n"
                "## Technical Details\n- Technical detail [1]\n"
                "## Examples, Evidence, and Case Studies\n- Example [1]\n"
                "## Contradictions and Caveats\n- Caveat [1]\n"
                "## Gaps in This Chunk\n- None\n"
            )
        if "writing one section of a detailed research report" in lower:
            section_name = "Section"
            for line in user.splitlines():
                if line.startswith("Section: "):
                    section_name = line.split("Section: ", 1)[1].strip()
                    break
            return (
                f"## {section_name}\n"
                "### Detail\n"
                "This section preserves mechanisms, examples, and caveats with citations [1].\n"
            )
        if "generate an executive summary" in lower:
            return "- Main finding: detailed workflow preserved.\n- Risk: contradictions need review."
        if "generating a glossary" in lower:
            return "- Term: precise definition\n- Workflow: ordered research pipeline"
        if "generate image prompts" in lower:
            return "# Images\n- prompt 1"
        if "structured-knowledge compiler" in lower:
            return json.dumps(
                {
                    "nodes": [{"id": "N1", "label": "Concept A"}, {"id": "N2", "label": "Concept B"}],
                    "hyperedges": [{"id": "E1", "nodes": ["N1", "N2"], "relation": "rel", "evidence": "x"}],
                }
            )
        if "extracting load-bearing concepts" in lower:
            return json.dumps(
                {
                    "core_concepts": [
                        {"name": f"C{i}", "definition": "d", "why_load_bearing": "w"} for i in range(1, 8)
                    ]
                }
            )
        if "backward drill pack" in lower:
            return json.dumps(
                {
                    "drill_pack_markdown": "# Drill Pack\n",
                    "drill_questions": [{"concept": "C1", "questions": [{"question": "q", "answer": "a", "pitfalls": []}]}],
                }
            )
        if "updating an existing json hypergraph" in lower:
            return json.dumps(
                {
                    "nodes": [{"id": "N1", "label": "Concept A"}, {"id": "N2", "label": "Concept B"}],
                    "hyperedges": [{"id": "E1", "nodes": ["N1", "N2"], "relation": "rel", "evidence": "x"}],
                }
            )
        raise RuntimeError(f"No auto reply for prompt: {user[:120]}")


def _input_iter(values: list[str]) -> Iterator[str]:
    for v in values:
        yield v
    while True:
        yield ""


def test_full_workflow_happy_path(tmp_path: Path, monkeypatch: Any) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus="definitions")

    curated = [
        {
            "title": "Example",
            "url": "https://example.com",
            "type": "blog",
            "why_relevant": "x",
            "credibility": 3,
            "priority": "High",
        }
    ]

    fake_client = FakeGrokClient(["# Scope\nOK"], curated=curated)

    def client_factory(_: WorkflowContext) -> FakeGrokClient:
        return fake_client

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console, client_factory=client_factory)

    inputs = _input_iter(
        [
            "yes",  # H0
            "all",  # H1 selection
            "approve",  # H1 approval
            "approve",  # H2 approval
            "none",  # H3 selection
        ]
    )
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: next(inputs))
    monkeypatch.setattr(
        runner,
        "_fetch_source_bundle",
        lambda *_args, **_kwargs: {
            "content_type": "text/html",
            "raw": "<html><body>content</body></html>",
            "main_text": "content",
            "full_text": "content",
            "analysis_text": "content",
        },
    )

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 1

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 2

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 3
    curated_path = sessions_dir / session.session_id / "02_curated_sources.json"
    assert curated_path.exists()
    assert isinstance(json.loads(curated_path.read_text(encoding="utf-8")), list)

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 4
    assert (sessions_dir / session.session_id / "03_source_snapshots").exists()
    assert (sessions_dir / session.session_id / "03_extracted_chunks").exists()

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 5
    assert (sessions_dir / session.session_id / "04_master_notebook.md").exists()

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 6
    assert (sessions_dir / session.session_id / "05_draft_v1.md").exists()

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 7

    runner.run(session.session_id)
    assert manager.load_state(session.session_id).current_phase == 8
    assert (sessions_dir / session.session_id / "FINAL_REPORT.md").exists()
    assert (sessions_dir / session.session_id / "images_to_generate.md").exists()
    assert (sessions_dir / session.session_id / "Youtube_Script.md").exists()
    final_report = (sessions_dir / session.session_id / "FINAL_REPORT.md").read_text(encoding="utf-8")
    assert "## Executive Summary" in final_report
    assert "## Source Catalog" in final_report
    assert "## Glossary" in final_report
    assert "## Architecture and Technical Mechanisms" in final_report


def test_full_workflow_auto_mode(tmp_path: Path, monkeypatch: Any) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus="definitions")

    curated = [
        {
            "title": "Example",
            "url": "https://example.com",
            "type": "blog",
            "why_relevant": "x",
            "credibility": 3,
            "priority": "High",
        }
    ]

    fake_client = FakeGrokClient(["# Scope\nOK"], curated=curated)

    def client_factory(_: WorkflowContext) -> FakeGrokClient:
        return fake_client

    def no_input(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("input() should not be called in --auto mode")

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console, client_factory=client_factory)

    monkeypatch.setattr("builtins.input", no_input)
    monkeypatch.setattr(
        runner,
        "_fetch_source_bundle",
        lambda *_args, **_kwargs: {
            "content_type": "text/html",
            "raw": "<html><body>content</body></html>",
            "main_text": "content",
            "full_text": "content",
            "analysis_text": "content",
        },
    )

    runner.run(session.session_id, auto=True, auto_full_collection="all")
    assert manager.load_state(session.session_id).current_phase == 8
    session_dir = sessions_dir / session.session_id
    assert (session_dir / "FINAL_REPORT.md").exists()
    assert (session_dir / "images_to_generate.md").exists()
    assert (session_dir / "Youtube_Script.md").exists()
    assert (session_dir / "06_full_sources" / "001.md").exists()


def test_compile_and_drill_outputs(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus=None)
    session_dir = sessions_dir / session.session_id
    (session_dir / "04_master_notebook.md").write_text("# Notebook\nContent", encoding="utf-8")

    fake_client = FakeGrokClient()

    def client_factory(_: WorkflowContext) -> FakeGrokClient:
        return fake_client

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console, client_factory=client_factory)

    runner.run(session.session_id, command="compile", compile_type="auto-hypergraph")
    kb_dir = session_dir / "knowledge_base"
    assert (kb_dir / "hypergraph.json").exists()
    assert (kb_dir / "auto_types" / "auto_hypergraph.json").exists()
    assert (kb_dir / "core_concepts.json").exists()

    runner.run(session.session_id, command="drill", drill_mode="backward")
    assert (kb_dir / "drill_pack.md").exists()
    assert (kb_dir / "drill_questions.json").exists()


def test_fetch_source_bundle_times_out_fast(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus=None)

    def slow_get(*_args: object, **_kwargs: object) -> Any:
        raise requests.exceptions.Timeout("timeout")

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console, http_get=slow_get)

    with pytest.raises(TimeoutError):
        runner._fetch_source_bundle("https://example.com", timeout_s=10)


def test_load_curated_sources_accepts_fenced_json(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus=None)
    session_dir = sessions_dir / session.session_id
    (session_dir / "02_curated_sources.json").write_text(
        "```json\n[{\"title\":\"T\",\"url\":\"https://example.com\",\"type\":\"blog\"}]\n```",
        encoding="utf-8",
    )

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console)
    ctx = WorkflowContext(
        state=manager.load_state(session.session_id),
        session_dir=session_dir,
        run_dir=tmp_path / "run",
        prompts_dir=tmp_path / "prompts",
    )
    sources = runner._load_curated_sources(ctx)
    assert len(sources) == 1
    assert sources[0].get("url") == "https://example.com"


def test_phase6_skips_when_curated_sources_missing(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus=None)
    session_dir = sessions_dir / session.session_id
    for p in (session_dir / "01_discovery_table.md", session_dir / "02_curated_sources.json"):
        if p.exists():
            p.unlink()

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console)
    ctx = WorkflowContext(
        state=manager.load_state(session.session_id),
        session_dir=session_dir,
        run_dir=tmp_path / "run2",
        prompts_dir=tmp_path / "prompts",
    )
    runner._phase6_full_collection(ctx, selection="none")
    assert manager.load_state(session.session_id).current_phase == 7


def test_phase3_extraction_skips_timed_out_chunk(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus=None)
    session_dir = sessions_dir / session.session_id
    manager.write_json(
        session_dir / "02_curated_sources.json",
        [{"title": "Example", "url": "https://example.com", "type": "blog"}],
    )

    class TimeoutExtractionClient(FakeGrokClient):
        def chat_text(self, *, system: str, user: str, **kwargs: Any) -> str:
            if "detailed extraction plan" in user.lower():
                return "# Plan\n1. x"
            if "extract detailed, evidence-preserving notes" in user.lower():
                raise GrokTimeoutError("timed out")
            return super().chat_text(system=system, user=user, **kwargs)

    def client_factory(_: WorkflowContext) -> TimeoutExtractionClient:
        return TimeoutExtractionClient()

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console, client_factory=client_factory)
    ctx = WorkflowContext(
        state=manager.load_state(session.session_id),
        session_dir=session_dir,
        run_dir=tmp_path / "run3",
        prompts_dir=Path("c:\\Project\\research_agent\\grok-research-agent\\grok_research_agent\\prompts"),
    )
    runner._fetch_source_bundle = lambda *_args, **_kwargs: {  # type: ignore[method-assign]
        "content_type": "text/html",
        "raw": "<html><body>content</body></html>",
        "main_text": "content",
        "full_text": "content",
        "analysis_text": "content",
    }
    runner._phase3_extraction(ctx)
    assert (session_dir / "03_extracted_index.txt").exists()


def test_generate_youtube_script_command(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic="Test Topic", focus=None)
    session_dir = sessions_dir / session.session_id
    (session_dir / "FINAL_REPORT.md").write_text("# Report\n\n## Executive Summary\nx\n", encoding="utf-8")

    fake_client = FakeGrokClient()

    def client_factory(_: WorkflowContext) -> FakeGrokClient:
        return fake_client

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console, client_factory=client_factory)
    runner.run(session.session_id, command="youtube-script")
    assert (session_dir / "Youtube_Script.md").exists()


@pytest.mark.parametrize("topic", ["agent skill", "agent harness", "multi-agent", "agentic rag"])
def test_end_to_end_topics_with_compiler_outputs(tmp_path: Path, monkeypatch: Any, topic: str) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    session = manager.create_session(topic=topic, focus="definitions")
    session_dir = sessions_dir / session.session_id

    curated = [
        {
            "title": f"Example for {topic}",
            "url": "https://example.com",
            "type": "blog",
            "why_relevant": "x",
            "credibility": 3,
            "priority": "High",
        }
    ]

    fake_client = FakeGrokClient([f"# Scope\nTopic: {topic}\nOK"], curated=curated)

    def client_factory(_: WorkflowContext) -> FakeGrokClient:
        return fake_client

    console = Console(file=None)
    runner = WorkflowRunner(session_manager=manager, console=console, client_factory=client_factory)

    inputs = _input_iter(["yes", "all", "approve", "approve", "none"])
    monkeypatch.setattr("builtins.input", lambda *_args, **_kwargs: next(inputs))
    monkeypatch.setattr(
        runner,
        "_fetch_source_bundle",
        lambda *_args, **_kwargs: {
            "content_type": "text/html",
            "raw": "<html><body>content</body></html>",
            "main_text": "content",
            "full_text": "content",
            "analysis_text": "content",
        },
    )

    for _ in range(8):
        runner.run(session.session_id)

    assert manager.load_state(session.session_id).current_phase == 8
    assert (session_dir / "FINAL_REPORT.md").exists()
    assert (session_dir / "images_to_generate.md").exists()
    final_report = (session_dir / "FINAL_REPORT.md").read_text(encoding="utf-8")
    assert "## Executive Summary" in final_report
    assert "## Source Catalog" in final_report
    assert "## Evidence, Examples, and Case Studies" in final_report

    runner.run(session.session_id, command="compile", compile_type="auto-hypergraph")
    kb_dir = session_dir / "knowledge_base"
    assert (kb_dir / "hypergraph.json").exists()
    assert (kb_dir / "core_concepts.json").exists()
    assert (kb_dir / "auto_types" / "auto_hypergraph.json").exists()

    runner.run(session.session_id, command="drill", drill_mode="backward")
    assert (kb_dir / "drill_pack.md").exists()
    assert (kb_dir / "drill_questions.json").exists()

    runner.run(session.session_id, command="show")
    assert (kb_dir / "hypergraph.mmd").exists()
