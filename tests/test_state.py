"""Tests for sync state."""

from pathlib import Path

from claude_evernote_sync.state import SyncState, load_state, save_state


def test_empty_state_returns_empty_set() -> None:
    state = SyncState()
    assert state.synced_for(("2026-05-15", "x")) == set()


def test_mark_synced_adds_uuids() -> None:
    state = SyncState()
    state.mark_synced(("2026-05-15", "x"), ["u1", "u2"])
    assert state.synced_for(("2026-05-15", "x")) == {"u1", "u2"}


def test_mark_synced_is_additive() -> None:
    state = SyncState()
    state.mark_synced(("2026-05-15", "x"), ["u1"])
    state.mark_synced(("2026-05-15", "x"), ["u2", "u3"])
    assert state.synced_for(("2026-05-15", "x")) == {"u1", "u2", "u3"}


def test_separate_groups_isolated() -> None:
    state = SyncState()
    state.mark_synced(("2026-05-15", "x"), ["u1"])
    state.mark_synced(("2026-05-15", "y"), ["u2"])
    assert state.synced_for(("2026-05-15", "x")) == {"u1"}
    assert state.synced_for(("2026-05-15", "y")) == {"u2"}


def test_is_first_sync_for_new_group() -> None:
    state = SyncState()
    assert state.is_first_sync(("2026-05-15", "x"))


def test_is_first_sync_false_after_marking() -> None:
    state = SyncState()
    state.mark_synced(("2026-05-15", "x"), [])
    assert not state.is_first_sync(("2026-05-15", "x"))


def test_load_state_missing_file_returns_empty(tmp_path: Path) -> None:
    state = load_state(tmp_path / "missing.json")
    assert state.groups == {}


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "state.json"
    state = SyncState()
    state.mark_synced(("2026-05-15", "x"), ["u1", "u2"])
    state.mark_synced(("2026-05-15", "y"), ["u3"])
    save_state(state, p)
    loaded = load_state(p)
    assert loaded.synced_for(("2026-05-15", "x")) == {"u1", "u2"}
    assert loaded.synced_for(("2026-05-15", "y")) == {"u3"}


def test_save_creates_parent_dir(tmp_path: Path) -> None:
    p = tmp_path / "nested" / "dir" / "state.json"
    save_state(SyncState(), p)
    assert p.exists()


def test_save_payload_includes_version(tmp_path: Path) -> None:
    import json
    p = tmp_path / "state.json"
    save_state(SyncState(), p)
    payload = json.loads(p.read_text())
    assert payload["version"] == 1
