#!/usr/bin/env python3
"""Fail closed on secrets and unsafe file types introduced by a PR."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath


SECRET_PATTERNS = {
    "OpenAI-style API key": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    "GitHub token": re.compile(r"\b(?:gh[opusr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
BLOCKED_NAMES = {".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519"}
BLOCKED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".keystore"}
BIDI_CONTROLS = re.compile("[\u202a-\u202e\u2066-\u2069]")
SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class AddedLine:
    path: str
    number: int | None
    text: str


def parse_added_lines(diff: str) -> list[AddedLine]:
    path = ""
    new_line: int | None = None
    added: list[AddedLine] = []
    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ b/"):
            path = raw_line[6:]
            continue
        if raw_line.startswith("@@"):
            match = re.search(r"\+(\d+)", raw_line)
            new_line = int(match.group(1)) if match else None
            continue
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            added.append(AddedLine(path, new_line, raw_line[1:]))
            if new_line is not None:
                new_line += 1
        elif raw_line.startswith(" ") and new_line is not None:
            new_line += 1
    return added


def scan_added_lines(lines: list[AddedLine]) -> list[str]:
    findings: list[str] = []
    for line in lines:
        location = f"{line.path}:{line.number or '?'}"
        if BIDI_CONTROLS.search(line.text):
            findings.append(f"{location}: bidirectional control character")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(line.text):
                findings.append(f"{location}: possible {label}")
    return findings


def changed_paths(base_sha: str, head_sha: str) -> list[str]:
    process = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_sha}...{head_sha}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in process.stdout.splitlines() if line]


def validate_changed_paths(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for path_text in paths:
        path = PurePosixPath(path_text)
        if path.name in BLOCKED_NAMES or path.suffix.lower() in BLOCKED_SUFFIXES:
            findings.append(f"{path_text}: credential-bearing filename is forbidden")
    return findings


def diff_text(base_sha: str, head_sha: str) -> str:
    process = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--unified=0",
            "--diff-filter=ACMR",
            f"{base_sha}...{head_sha}",
        ],
        check=True,
        capture_output=True,
        text=True,
        errors="replace",
    )
    return process.stdout


def symlink_findings(head_sha: str, changed: set[str]) -> list[str]:
    process = subprocess.run(
        ["git", "ls-tree", "-r", head_sha],
        check=True,
        capture_output=True,
        text=True,
    )
    findings = []
    for line in process.stdout.splitlines():
        metadata, _, path = line.partition("\t")
        mode = metadata.split(" ", 1)[0]
        if path in changed and mode == "120000":
            findings.append(f"{path}: symbolic links require human review")
    return findings


def require_sha(value: str, label: str) -> str:
    normalized = value.strip().lower()
    if not SAFE_SHA.fullmatch(normalized):
        raise ValueError(f"{label} must be a full SHA-1")
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    base_sha = require_sha(args.base, "base")
    head_sha = require_sha(args.head, "head")
    paths = changed_paths(base_sha, head_sha)
    findings = validate_changed_paths(paths)
    findings.extend(scan_added_lines(parse_added_lines(diff_text(base_sha, head_sha))))
    findings.extend(symlink_findings(head_sha, set(paths)))
    if findings:
        print("Security scan failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Security scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
