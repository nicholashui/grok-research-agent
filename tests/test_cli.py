from pathlib import Path

from grok_research_agent.grok_client import GrokQuotaError
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


def test_cli_list_types(capsys: object) -> None:
    rc = main(["list-types"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "auto-hypergraph" in out


def test_cli_reports_quota_error(tmp_path: Path, capsys: object, monkeypatch: object) -> None:
    sessions_dir = tmp_path / "sessions"

    def boom(*_args: object, **_kwargs: object) -> None:
        raise GrokQuotaError("Grok API quota/credit error. Please top up credits.")

    monkeypatch.setattr("grok_research_agent.workflow_phases.WorkflowRunner.run", boom)
    rc = main(["resume", "--sessions-dir", str(sessions_dir), "--session-id", "abc"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "quota/credit" in out.lower()
