"""Tests for per-session sync state."""

from pathlib import Path

from claude_evernote_sync.state import SessionRecord, SyncState, load_state, save_state


def test_empty_state_has_no_records() -> None:
    state = SyncState()
    assert state.record_for("any") is None
    assert state.synced_for("any") == set()


def test_mark_synced_creates_record_with_title() -> None:
    state = SyncState()
    state.mark_synced("s1", ["u1", "u2"], title="Topic - repo - s1abc")
    record = state.record_for("s1")
    assert record is not None
    assert record.synced_uuids == {"u1", "u2"}
    assert record.title == "Topic - repo - s1abc"


def test_mark_synced_is_additive() -> None:
    state = SyncState()
    state.mark_synced("s1", ["u1"], title="locked")
    state.mark_synced("s1", ["u2", "u3"], title="ignored-on-update")
    assert state.synced_for("s1") == {"u1", "u2", "u3"}


def test_mark_synced_does_not_change_title_on_repeat() -> None:
    """The title is locked at first sync — subsequent calls don't retitle."""
    state = SyncState()
    state.mark_synced("s1", ["u1"], title="first-title")
    state.mark_synced("s1", ["u2"], title="DIFFERENT")
    record = state.record_for("s1")
    assert record is not None
    assert record.title == "first-title"


def test_separate_sessions_isolated() -> None:
    state = SyncState()
    state.mark_synced("s1", ["u1"], title="A")
    state.mark_synced("s2", ["u2"], title="B")
    assert state.synced_for("s1") == {"u1"}
    assert state.synced_for("s2") == {"u2"}


def test_is_first_sync_for_new_session() -> None:
    state = SyncState()
    assert state.is_first_sync("s1")


def test_is_first_sync_false_after_marking() -> None:
    state = SyncState()
    state.mark_synced("s1", [], title="locked")
    assert not state.is_first_sync("s1")


def test_load_state_missing_file_returns_empty(tmp_path: Path) -> None:
    state = load_state(tmp_path / "missing.json")
    assert state.sessions == {}


def test_load_state_with_wrong_version_returns_empty(tmp_path: Path) -> None:
    """v1 state files (the old (date, bucket) schema) are silently discarded.

    Users with existing v1 state will see their lookback window re-synced as
    per-session notes; the old daily-rollup notes already in Evernote remain
    untouched as a read-only archive.
    """
    import json

    p = tmp_path / "state.json"
    p.write_text(json.dumps({"version": 1, "groups": {"2026-05-15|x": ["u1"]}}))
    state = load_state(p)
    assert state.sessions == {}


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    state = SyncState()
    state.mark_synced("s1", ["u1", "u2"], title="Topic A")
    state.mark_synced("s2", ["u3"], title="Topic B")
    save_state(state, p)
    loaded = load_state(p)
    assert loaded.synced_for("s1") == {"u1", "u2"}
    assert loaded.synced_for("s2") == {"u3"}
    record1 = loaded.record_for("s1")
    assert record1 is not None
    assert record1.title == "Topic A"


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dir" / "state.json"
    save_state(SyncState(), p)
    assert p.exists()


def test_save_payload_includes_version(tmp_path: Path) -> None:
    import json

    p = tmp_path / "state.json"
    save_state(SyncState(), p)
    payload = json.loads(p.read_text())
    assert payload["version"] == 2


def test_session_record_default_is_empty() -> None:
    record = SessionRecord()
    assert record.synced_uuids == set()
    assert record.title == ""
