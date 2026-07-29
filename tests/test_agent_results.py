"""Tests for pulling sub-agent findings out of task-notification records."""

from claude_evernote_sync.agent_results import (
    demote_headings,
    extract_agent_results,
    is_task_notification,
)

NOTIFICATION = """<task-notification>
<task-id>a8c5036012d6be372</task-id>
<tool-use-id>toolu_01EzNx</tool-use-id>
<output-file>/tmp/tasks/a8c5036012d6be372.output</output-file>
<status>completed</status>
<summary>Agent "Research microbiome-regain causality" finished</summary>
<note>A task-notification fires each time this agent stops.</note>
<result>## BRIEF
One link is **strong**, two are speculative.</result>
</task-notification>"""


def test_extract_agent_results_keyed_by_tool_use_id() -> None:
    record = {"type": "user", "message": {"role": "user", "content": NOTIFICATION}}
    assert extract_agent_results(record) == {
        "toolu_01EzNx": "## BRIEF\nOne link is **strong**, two are speculative."
    }


def test_extract_agent_results_finds_notifications_at_any_depth() -> None:
    """The same notification is written into queue-operation and attachment
    records too, whose shapes differ from a conversation message."""
    record = {"type": "attachment", "attachment": {"content": [{"text": NOTIFICATION}]}}
    assert "toolu_01EzNx" in extract_agent_results(record)


def test_extract_agent_results_keeps_longest_when_duplicated() -> None:
    """One agent notifies through several record types; a truncated copy must
    not overwrite the full report."""
    short = NOTIFICATION.replace("## BRIEF\nOne link is **strong**, two are speculative.", "trunc")
    record = {"a": short, "b": NOTIFICATION}
    assert extract_agent_results(record)["toolu_01EzNx"] != "trunc"


def test_extract_agent_results_ignores_records_without_notifications() -> None:
    assert extract_agent_results({"type": "user", "message": {"content": "hello"}}) == {}


def test_extract_agent_results_skips_notification_without_result() -> None:
    pending = NOTIFICATION.replace("<status>completed</status>", "<status>running</status>")
    pending = pending[: pending.index("<result>")] + "</task-notification>"
    assert extract_agent_results({"a": pending}) == {}


def test_is_task_notification_detects_the_wrapper() -> None:
    assert is_task_notification(NOTIFICATION)
    assert not is_task_notification("a normal user message")


def test_demote_headings_pushes_every_level_down_one() -> None:
    assert demote_headings("# A\n## B\n### C") == "## A\n### B\n#### C"


def test_demote_headings_leaves_non_headings_alone() -> None:
    assert demote_headings("a #hashtag and #4 issue\ntext") == "a #hashtag and #4 issue\ntext"
