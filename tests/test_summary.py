"""Tests for embedded JSONL summary extraction and cross-file matching."""

from pathlib import Path

from claude_evernote_sync.parser import parse_jsonl_file
from claude_evernote_sync.summary import (
    SummaryRecord,
    attach_cross_file_summaries,
    extract_summary_records,
)


def test_summary_record_dataclass() -> None:
    rec = SummaryRecord(leaf_uuid="abc", summary="refactor function")
    assert rec.leaf_uuid == "abc"
    assert rec.summary == "refactor function"


def test_extract_summary_records_from_file(tmp_path: Path) -> None:
    lines = [
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s","message":{"role":"user","content":"hi"}}',
        '{"type":"summary","summary":"Refactor the function","leafUuid":"u1"}',
    ]
    p = tmp_path / "with_summary.jsonl"
    p.write_text("\n".join(lines))
    records = extract_summary_records(p)
    assert len(records) == 1
    assert records[0].leaf_uuid == "u1"
    assert records[0].summary == "Refactor the function"


def test_extract_summary_records_skips_malformed_lines(tmp_path: Path) -> None:
    lines = [
        "not json at all",
        '{"type":"summary","summary":"ok","leafUuid":"u9"}',
    ]
    p = tmp_path / "mixed.jsonl"
    p.write_text("\n".join(lines))
    records = extract_summary_records(p)
    assert len(records) == 1
    assert records[0].leaf_uuid == "u9"


def test_extract_summary_records_empty_for_file_without_summaries(tmp_path: Path) -> None:
    p = tmp_path / "no_summary.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s","message":{"role":"user","content":"hi"}}'
    )
    assert extract_summary_records(p) == []


def test_extract_summary_records_drops_records_missing_required_fields(
    tmp_path: Path,
) -> None:
    lines = [
        '{"type":"summary","summary":"missing leafUuid"}',
        '{"type":"summary","leafUuid":"u1"}',
        '{"type":"summary","summary":"valid","leafUuid":"u2"}',
    ]
    p = tmp_path / "partial.jsonl"
    p.write_text("\n".join(lines))
    records = extract_summary_records(p)
    assert len(records) == 1
    assert records[0].leaf_uuid == "u2"


def test_attach_summary_in_file(tmp_path: Path) -> None:
    """Summary whose leafUuid matches one of THIS session's message uuids
    gets attached to this session."""
    lines = [
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s","message":{"role":"user","content":"hi"}}',
        '{"type":"summary","summary":"Greeting session","leafUuid":"u1"}',
    ]
    p = tmp_path / "ok.jsonl"
    p.write_text("\n".join(lines))
    session = parse_jsonl_file(p)
    summaries = extract_summary_records(p)
    assert session is not None
    attach_cross_file_summaries([session], summaries)
    assert session.summary == "Greeting session"


def test_attach_summary_cross_file(tmp_path: Path) -> None:
    """Summary in file A whose leafUuid matches a message in session B
    gets attached to session B — handles Claude Code's cross-session
    contamination (issue #2597)."""
    a_path = tmp_path / "a.jsonl"
    a_path.write_text(
        '{"type":"user","uuid":"a-msg","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"a","message":{"role":"user","content":"first"}}\n'
        '{"type":"summary","summary":"This belongs to B","leafUuid":"b-msg"}'
    )
    b_path = tmp_path / "b.jsonl"
    b_path.write_text(
        '{"type":"user","uuid":"b-msg","timestamp":"2026-05-15T11:00:00.000Z",'
        '"cwd":"/x","sessionId":"b","message":{"role":"user","content":"second"}}'
    )
    s_a = parse_jsonl_file(a_path)
    s_b = parse_jsonl_file(b_path)
    assert s_a is not None and s_b is not None
    all_summaries = extract_summary_records(a_path) + extract_summary_records(b_path)
    attach_cross_file_summaries([s_a, s_b], all_summaries)
    assert s_b.summary == "This belongs to B"
    assert s_a.summary is None


def test_attach_summary_orphan_leaf_uuid(tmp_path: Path) -> None:
    """A summary whose leafUuid doesn't match any known message is dropped silently."""
    p = tmp_path / "orphan.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s","message":{"role":"user","content":"hi"}}\n'
        '{"type":"summary","summary":"For unknown session","leafUuid":"nobody"}'
    )
    session = parse_jsonl_file(p)
    assert session is not None
    attach_cross_file_summaries([session], extract_summary_records(p))
    assert session.summary is None


def test_attach_summary_does_not_overwrite_existing(tmp_path: Path) -> None:
    """If a session already has a summary, a second matching record is ignored."""
    p = tmp_path / "two.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s","message":{"role":"user","content":"hi"}}\n'
        '{"type":"summary","summary":"first","leafUuid":"u1"}\n'
        '{"type":"summary","summary":"second","leafUuid":"u1"}'
    )
    session = parse_jsonl_file(p)
    assert session is not None
    attach_cross_file_summaries([session], extract_summary_records(p))
    assert session.summary == "first"
