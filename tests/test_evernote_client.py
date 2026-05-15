"""Tests for the Evernote client (mocked - no real API calls)."""

from unittest.mock import MagicMock

import pytest

from claude_evernote_sync.evernote_client import EvernoteSync


def _make_notebook(guid: str, name: str) -> MagicMock:
    nb = MagicMock()
    nb.guid = guid
    nb.name = name
    return nb


def _make_note_metadata(guid: str, title: str) -> MagicMock:
    meta = MagicMock()
    meta.guid = guid
    meta.title = title
    return meta


@pytest.fixture
def sync() -> EvernoteSync:
    instance = EvernoteSync.__new__(EvernoteSync)
    instance.token = "fake-token"
    instance.note_store = MagicMock()
    return instance


def test_get_or_create_notebook_returns_existing_guid(sync: EvernoteSync) -> None:
    existing = _make_notebook("nb-1", "Claude Sessions")
    sync.note_store.listNotebooks.return_value = [_make_notebook("nb-0", "Other"), existing]
    guid = sync.get_or_create_notebook("Claude Sessions")
    assert guid == "nb-1"
    sync.note_store.createNotebook.assert_not_called()


def test_get_or_create_notebook_creates_when_missing(sync: EvernoteSync) -> None:
    sync.note_store.listNotebooks.return_value = []
    created = _make_notebook("new-guid", "Claude Sessions")
    sync.note_store.createNotebook.return_value = created
    guid = sync.get_or_create_notebook("Claude Sessions")
    assert guid == "new-guid"
    sync.note_store.createNotebook.assert_called_once()


def test_find_note_by_title_returns_matching_guid(sync: EvernoteSync) -> None:
    metadata = MagicMock()
    metadata.notes = [
        _make_note_metadata("note-other", "Some other note"),
        _make_note_metadata("note-1", "Claude Sessions — myrepo — 2026-05-15"),
    ]
    sync.note_store.findNotesMetadata.return_value = metadata
    guid = sync.find_note_by_title("nb-1", "Claude Sessions — myrepo — 2026-05-15")
    assert guid == "note-1"


def test_find_note_by_title_returns_none_when_absent(sync: EvernoteSync) -> None:
    metadata = MagicMock()
    metadata.notes = []
    sync.note_store.findNotesMetadata.return_value = metadata
    guid = sync.find_note_by_title("nb-1", "Nonexistent")
    assert guid is None


def test_find_note_by_title_passes_notebook_filter(sync: EvernoteSync) -> None:
    metadata = MagicMock()
    metadata.notes = []
    sync.note_store.findNotesMetadata.return_value = metadata
    sync.find_note_by_title("nb-xyz", "Some title")
    args, _ = sync.note_store.findNotesMetadata.call_args
    note_filter = args[1]
    assert note_filter.notebookGuid == "nb-xyz"


def test_upsert_note_creates_when_new(sync: EvernoteSync) -> None:
    sync.note_store.findNotesMetadata.return_value = MagicMock(notes=[])
    sync.note_store.createNote.return_value = MagicMock(guid="created-guid")
    guid = sync.upsert_note("nb-1", "Title", "<en-note>body</en-note>")
    assert guid == "created-guid"
    sync.note_store.createNote.assert_called_once()
    sync.note_store.updateNote.assert_not_called()


def test_upsert_note_updates_when_exists(sync: EvernoteSync) -> None:
    metadata = MagicMock()
    metadata.notes = [_make_note_metadata("existing-guid", "Title")]
    sync.note_store.findNotesMetadata.return_value = metadata
    sync.note_store.updateNote.return_value = MagicMock(guid="existing-guid")
    guid = sync.upsert_note("nb-1", "Title", "<en-note>updated</en-note>")
    assert guid == "existing-guid"
    sync.note_store.updateNote.assert_called_once()
    sync.note_store.createNote.assert_not_called()


def test_upsert_note_passes_content(sync: EvernoteSync) -> None:
    sync.note_store.findNotesMetadata.return_value = MagicMock(notes=[])
    sync.note_store.createNote.return_value = MagicMock(guid="g")
    sync.upsert_note("nb-1", "Title", "<en-note>X</en-note>")
    args, _ = sync.note_store.createNote.call_args
    note = args[1]
    assert note.title == "Title"
    assert note.content == "<en-note>X</en-note>"
    assert note.notebookGuid == "nb-1"


def test_upsert_note_update_carries_guid(sync: EvernoteSync) -> None:
    metadata = MagicMock()
    metadata.notes = [_make_note_metadata("existing-guid", "Title")]
    sync.note_store.findNotesMetadata.return_value = metadata
    sync.note_store.updateNote.return_value = MagicMock(guid="existing-guid")
    sync.upsert_note("nb-1", "Title", "<en-note>X</en-note>")
    args, _ = sync.note_store.updateNote.call_args
    note = args[1]
    assert note.guid == "existing-guid"
