#!/usr/bin/env python3
"""Scan beads data for PII / secrets before it syncs to the git remote.

`bd dolt push` ships the issue DB to refs/dolt/data with bd's own transport,
bypassing git hooks — the gitleaks pre-commit hook never sees issue text,
memories, or interaction logs. This dev utility (not part of the package)
collects all of that and exits 1 when something personal- or secret-shaped
appears. Wired into pre-commit (always_run) and scripts/bd-push.sh.

Usage:
    uv run python scripts/beads_leak_scan.py            # scan live bd data
    uv run python scripts/beads_leak_scan.py FILE ...   # scan given files
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Identities that are already public on every git commit are not leaks.
ALLOWED_EMAIL = re.compile(r"@(users\.noreply\.github\.com|example\.(com|org|net))\b")

PATTERNS = {
    "email address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "US SSN": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # Gmail app passwords display as four 4-letter lowercase groups.
    "Gmail app password": re.compile(r"\b[a-z]{4} [a-z]{4} [a-z]{4} [a-z]{4}\b"),
    "card-length digit run": re.compile(r"\b\d{13,16}\b"),
    "secret assignment": re.compile(
        r"(?i)(password|passwd|api[_-]?key|auth[_-]?token|developer[_-]?token)"
        r"['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_\-/+=:]{8,}"
    ),
}


@dataclass
class Finding:
    source: str
    rule: str
    excerpt: str


def _excerpt(text: str, start: int, end: int) -> str:
    return text[max(0, start - 30) : end + 30].replace("\n", " ").strip()


def scan_text(source: str, text: str) -> list[Finding]:
    """All PII/secret pattern matches in one named blob of text."""
    findings = []
    for rule, pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            if rule == "email address" and ALLOWED_EMAIL.search(m.group()):
                continue
            findings.append(Finding(source, rule, _excerpt(text, m.start(), m.end())))
    return findings


def _bd_output(args: list[str]) -> str:
    proc = subprocess.run(["bd", *args], capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(f"warning: bd {args[0]} failed: {proc.stderr.strip()}", file=sys.stderr)
    return proc.stdout


def _collect_live() -> dict[str, str]:
    """Everything bd would sync: issues, memories (via prime), logs, config."""
    with tempfile.TemporaryDirectory() as tmp:
        export = Path(tmp) / "issues.jsonl"
        _bd_output(["export", "-o", str(export)])
        issues = export.read_text() if export.exists() else ""
    corpus = {"bd export": issues, "bd prime (memories)": _bd_output(["prime"])}
    for name in ("interactions.jsonl", "config.yaml"):
        path = Path(".beads") / name
        if path.exists():
            corpus[f".beads/{name}"] = path.read_text()
    return corpus


def _report(findings: list[Finding]) -> int:
    for f in findings:
        print(f"LEAK? [{f.rule}] in {f.source}: …{f.excerpt}…", file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} potential leak(s) found in beads data.", file=sys.stderr)
        return 1
    print("beads leak scan: clean")
    return 0


def main(argv: list[str]) -> int:
    if argv:
        corpus = {a: Path(a).read_text() for a in argv}
    elif shutil.which("bd") is None:
        # CI runners and external contributors don't have beads installed.
        print("beads leak scan: bd not installed — nothing to scan")
        return 0
    else:
        corpus = _collect_live()
    findings = [f for source, text in corpus.items() for f in scan_text(source, text)]
    return _report(findings)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
