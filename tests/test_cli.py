from pathlib import Path

from grok_research_agent.cli import main
from grok_research_agent.session_manager import SessionManager


def test_cli_list_sessions(tmp_path: Path, capsys: object) -> None:
    sessions_dir = tmp_path / "sessions"
    manager = SessionManager(sessions_dir=sessions_dir)
    s = manager.create_session(topic="Topic", focus=None)

    rc = main(["list-sessions", "--sessions-dir", str(sessions_dir)])
    assert rc == 0
    out = capsys.readouterr().out
    assert s.session_id in out

