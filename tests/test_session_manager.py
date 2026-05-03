from pathlib import Path

from grok_research_agent.session_manager import SessionManager


def test_create_session_is_unique(tmp_path: Path) -> None:
    manager = SessionManager(sessions_dir=tmp_path / "sessions")
    s1 = manager.create_session(topic="Same Topic", focus=None)
    s2 = manager.create_session(topic="Same Topic", focus=None)
    assert s1.session_id != s2.session_id
    assert s2.session_id.startswith(s1.session_id)


def test_load_and_save_state_roundtrip(tmp_path: Path) -> None:
    manager = SessionManager(sessions_dir=tmp_path / "sessions")
    s1 = manager.create_session(topic="Roundtrip", focus="x")
    state = manager.load_state(s1.session_id)
    state.current_phase = 3
    manager.save_state(state)
    state2 = manager.load_state(s1.session_id)
    assert state2.current_phase == 3


def test_create_session_with_very_long_topic(tmp_path: Path) -> None:
    manager = SessionManager(sessions_dir=tmp_path / "sessions")
    topic = "Design and implement a comprehensive Video Agent system " * 200
    s1 = manager.create_session(topic=topic, focus=None)
    assert len(s1.session_id) <= 120
    assert (tmp_path / "sessions" / s1.session_id).exists()
