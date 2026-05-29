"""Tests for embedded JSONL summary extraction and cross-file matching."""

from pathlib import Path

from claude_evernote_sync.parser import parse_jsonl_file
from claude_evernote_sync.summary import (
    AiTitleRecord,
    SummaryRecord,
    attach_ai_titles,
    attach_cross_file_summaries,
    attach_subagent_descriptions,
    extract_ai_title_records,
    extract_summary_records,
    is_subagent_path,
    read_subagent_description,
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


def test_ai_title_record_dataclass() -> None:
    rec = AiTitleRecord(session_id="abc", title="Refactor user auth")
    assert rec.session_id == "abc"
    assert rec.title == "Refactor user auth"


def test_extract_ai_title_records(tmp_path: Path) -> None:
    lines = [
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s1","message":{"role":"user","content":"hi"}}',
        '{"type":"ai-title","aiTitle":"My Topic","sessionId":"s1"}',
    ]
    p = tmp_path / "with_title.jsonl"
    p.write_text("\n".join(lines))
    records = extract_ai_title_records(p)
    assert len(records) == 1
    assert records[0].session_id == "s1"
    assert records[0].title == "My Topic"


def test_extract_ai_title_drops_records_missing_fields(tmp_path: Path) -> None:
    lines = [
        '{"type":"ai-title","aiTitle":"missing session id"}',
        '{"type":"ai-title","sessionId":"s2"}',
        '{"type":"ai-title","aiTitle":"valid","sessionId":"s3"}',
    ]
    p = tmp_path / "partial.jsonl"
    p.write_text("\n".join(lines))
    records = extract_ai_title_records(p)
    assert len(records) == 1
    assert records[0].session_id == "s3"


def test_attach_ai_titles_by_session_id(tmp_path: Path) -> None:
    """ai-title records key on sessionId directly (no leafUuid contamination).

    In production Claude Code writes JSONL files named <sessionId>.jsonl,
    so Session.session_id (derived from the filename) equals the sessionId
    field on each record.
    """
    lines = [
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"my-session","message":{"role":"user","content":"hi"}}',
        '{"type":"ai-title","aiTitle":"Research X","sessionId":"my-session"}',
    ]
    p = tmp_path / "my-session.jsonl"
    p.write_text("\n".join(lines))
    session = parse_jsonl_file(p)
    assert session is not None
    attach_ai_titles([session], extract_ai_title_records(p))
    assert session.summary == "Research X"


def test_attach_ai_titles_last_wins_when_duplicated(tmp_path: Path) -> None:
    """Claude Code writes the same ai-title repeatedly; the last (latest) wins."""
    lines = [
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"dup","message":{"role":"user","content":"hi"}}',
        '{"type":"ai-title","aiTitle":"initial topic","sessionId":"dup"}',
        '{"type":"ai-title","aiTitle":"refined topic","sessionId":"dup"}',
    ]
    p = tmp_path / "dup.jsonl"
    p.write_text("\n".join(lines))
    session = parse_jsonl_file(p)
    assert session is not None
    attach_ai_titles([session], extract_ai_title_records(p))
    assert session.summary == "refined topic"


def test_attach_ai_titles_overrides_existing_summary(tmp_path: Path) -> None:
    """ai-title is treated as more authoritative than a cross-file summary
    record (sessionId keying is unambiguous; leafUuid matching is best-effort)."""
    lines = [
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"s","message":{"role":"user","content":"hi"}}',
    ]
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(lines))
    session = parse_jsonl_file(p)
    assert session is not None
    session.summary = "from-summary-record"
    attach_ai_titles([session], [AiTitleRecord(session_id="s", title="from-ai-title")])
    assert session.summary == "from-ai-title"


def test_attach_ai_titles_ignores_unknown_session() -> None:
    """An ai-title record for a session we don't have is silently dropped."""
    attach_ai_titles([], [AiTitleRecord(session_id="ghost", title="orphan")])


def test_is_subagent_path() -> None:
    assert is_subagent_path(Path("/x/SESSION/subagents/agent-a.jsonl"))
    assert not is_subagent_path(Path("/x/SESSION/regular.jsonl"))


def test_read_subagent_description(tmp_path: Path) -> None:
    sub = tmp_path / "SESSION" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-a.jsonl").write_text("{}")
    (sub / "agent-a.meta.json").write_text(
        '{"agentType":"general-purpose","description":"Audit pooling"}'
    )
    assert read_subagent_description(sub / "agent-a.jsonl") == "Audit pooling"


def test_read_subagent_description_non_subagent(tmp_path: Path) -> None:
    p = tmp_path / "regular.jsonl"
    p.write_text("{}")
    assert read_subagent_description(p) is None


def test_read_subagent_description_missing_meta(tmp_path: Path) -> None:
    sub = tmp_path / "subagents"
    sub.mkdir()
    (sub / "agent-b.jsonl").write_text("{}")
    assert read_subagent_description(sub / "agent-b.jsonl") is None


def test_read_subagent_description_invalid_meta_json(tmp_path: Path) -> None:
    sub = tmp_path / "subagents"
    sub.mkdir()
    (sub / "agent-d.jsonl").write_text("{}")
    (sub / "agent-d.meta.json").write_text("not valid json {")
    assert read_subagent_description(sub / "agent-d.jsonl") is None


def test_attach_subagent_descriptions_sets_summary(tmp_path: Path) -> None:
    sub = tmp_path / "subagents"
    sub.mkdir()
    p = sub / "agent-c.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"agent-c","message":{"role":"user","content":"do audit"}}'
    )
    (sub / "agent-c.meta.json").write_text('{"description":"Audit caches"}')
    session = parse_jsonl_file(p)
    assert session is not None
    attach_subagent_descriptions([session], [p])
    assert session.summary == "Audit caches"


def test_attach_subagent_descriptions_leaves_non_subagent_untouched(tmp_path: Path) -> None:
    p = tmp_path / "regular.jsonl"
    p.write_text(
        '{"type":"user","uuid":"u1","timestamp":"2026-05-15T10:00:00.000Z",'
        '"cwd":"/x","sessionId":"regular","message":{"role":"user","content":"hi"}}'
    )
    session = parse_jsonl_file(p)
    assert session is not None
    attach_subagent_descriptions([session], [p])
    assert session.summary is None
