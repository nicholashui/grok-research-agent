from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from rich.console import Console

from grok_research_agent.session_manager import SessionManager
from grok_research_agent.workflow_phases import WorkflowContext, WorkflowRunner


class FakeGrokClient:
    def __init__(self, replies: list[str]):
        self._replies = list(replies)

    def chat_text(self, *, system: str, user: str, **_: Any) -> str:
        if not self._replies:
            raise RuntimeError("No more fake replies")
        return self._replies.pop(0)

    def prompt_from_file(self, prompt_path: Path) -> str:
        return prompt_path.read_text(encoding="utf-8")

    def render_template(self, template: str, values: dict[str, Any]) -> str:
        text = template
        for k, v in values.items():
            text = text.replace("{{" + k + "}}", str(v))
        return text


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

    fake_replies = [
        "# Scope\nOK",  # phase 0
        "| Type | Title | URL | Why Relevant | Credibility (1-5) | Short TL;DR | Priority (High/Med/Low) |\n| - | - | - | - | - | - | - |",  # phase 1
        json.dumps(curated),  # phase 2 curated
        "# Gaps\nNone",  # phase 2 gap
        "# Plan\n1. Extract",  # phase 3 plan
        "## Key Definitions\nX\n## Notes\nY",  # phase 3 extraction
        "# Notebook\nMerged",  # phase 4
        "# Draft\n## References\n[1] https://example.com",  # phase 5
        "# Final\n## References\n[1] https://example.com\n## Glossary\n- X",  # phase 7 final
        "# Images\n- prompt 1",  # phase 7 images
    ]
    fake_client = FakeGrokClient(fake_replies)

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
    monkeypatch.setattr(runner, "_fetch_readable_text", lambda *_args, **_kwargs: "<html><body>content</body></html>")

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

