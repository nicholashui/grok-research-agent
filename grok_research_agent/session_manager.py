import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "session"


class SessionState(BaseModel):
    session_id: str
    topic: str
    focus: str | None = None
    created_at: str
    grok_model: str
    current_phase: int = 0
    run_history: list[str] = Field(default_factory=list)
    updated_at: str


@dataclass(frozen=True)
class SessionPaths:
    session_dir: Path
    state_path: Path
    runs_dir: Path


class SessionManager:
    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _default_model(self) -> str:
        return "grok-3"

    def create_session(self, topic: str, focus: str | None) -> SessionState:
        date = datetime.now().strftime("%Y%m%d")
        base = f"{_slugify(topic)}-{date}"
        session_id = base
        idx = 2
        while (self.sessions_dir / session_id).exists():
            session_id = f"{base}-{idx}"
            idx += 1

        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=False)
        (session_dir / "runs").mkdir(parents=True, exist_ok=True)

        state = SessionState(
            session_id=session_id,
            topic=topic,
            focus=focus,
            created_at=self._now_iso(),
            grok_model=self._default_model(),
            current_phase=0,
            run_history=[],
            updated_at=self._now_iso(),
        )
        self.save_state(state)
        return state

    def session_paths(self, session_id: str) -> SessionPaths:
        session_dir = self.sessions_dir / session_id
        return SessionPaths(
            session_dir=session_dir,
            state_path=session_dir / "session.json",
            runs_dir=session_dir / "runs",
        )

    def load_state(self, session_id: str) -> SessionState:
        paths = self.session_paths(session_id)
        raw = json.loads(paths.state_path.read_text(encoding="utf-8"))
        return SessionState.model_validate(raw)

    def save_state(self, state: SessionState) -> None:
        paths = self.session_paths(state.session_id)
        paths.session_dir.mkdir(parents=True, exist_ok=True)
        paths.runs_dir.mkdir(parents=True, exist_ok=True)
        state.updated_at = self._now_iso()  # type: ignore[misc]
        paths.state_path.write_text(
            json.dumps(state.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def create_run_dir(self, session_id: str) -> Path:
        paths = self.session_paths(session_id)
        for _ in range(1000):
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            run_dir = paths.runs_dir / run_id
            try:
                run_dir.mkdir(parents=True, exist_ok=False)
                return run_dir
            except FileExistsError:
                continue
        raise RuntimeError("Unable to create unique run directory")

    def list_sessions(self) -> list[str]:
        sessions: list[str] = []
        for p in sorted(self.sessions_dir.glob("*")):
            if not p.is_dir():
                continue
            if (p / "session.json").exists():
                sessions.append(p.name)
        return sessions

    def read_json(self, path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
