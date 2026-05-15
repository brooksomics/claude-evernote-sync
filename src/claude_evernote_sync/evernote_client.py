"""Evernote NoteStore client wrapper for finding, creating, and updating notes."""

from __future__ import annotations

from typing import Any

from evernote.edam.notestore.NoteStore import Client as NoteStoreClient
from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec
from evernote.edam.type.ttypes import Note, Notebook
from evernote.edam.userstore.UserStore import Client as UserStoreClient
from thrift.protocol.TBinaryProtocol import TBinaryProtocol
from thrift.transport.THttpClient import THttpClient

USER_AGENT = "claude-evernote-sync/0.1"


def _make_client(url: str, klass: Any) -> Any:
    transport = THttpClient(url)
    transport.setCustomHeaders({"User-Agent": USER_AGENT})
    return klass(TBinaryProtocol(transport))


def _connect(token: str, host: str) -> Any:
    user_store = _make_client(f"https://{host}/edam/user", UserStoreClient)
    note_store_url = user_store.getNoteStoreUrl(token)
    return _make_client(note_store_url, NoteStoreClient)


class EvernoteSync:
    """High-level wrapper around the Evernote NoteStore API."""

    def __init__(self, token: str, host: str = "www.evernote.com") -> None:
        self.token = token
        self.note_store = _connect(token, host)

    def get_or_create_notebook(self, name: str) -> str:
        for nb in self.note_store.listNotebooks(self.token):
            if nb.name == name:
                return str(nb.guid)
        created = self.note_store.createNotebook(self.token, Notebook(name=name))
        return str(created.guid)

    def find_note_by_title(self, notebook_guid: str, title: str) -> str | None:
        note_filter = NoteFilter(notebookGuid=notebook_guid, words=f'intitle:"{title}"')
        spec = NotesMetadataResultSpec(includeTitle=True)
        result = self.note_store.findNotesMetadata(self.token, note_filter, 0, 50, spec)
        for note_meta in result.notes:
            if note_meta.title == title:
                return str(note_meta.guid)
        return None

    def upsert_note(self, notebook_guid: str, title: str, content: str) -> str:
        existing_guid = self.find_note_by_title(notebook_guid, title)
        note = Note(title=title, content=content, notebookGuid=notebook_guid)
        if existing_guid:
            note.guid = existing_guid
            updated = self.note_store.updateNote(self.token, note)
            return str(updated.guid)
        created = self.note_store.createNote(self.token, note)
        return str(created.guid)
