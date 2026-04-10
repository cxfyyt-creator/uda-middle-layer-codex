from __future__ import annotations

import re
from pathlib import Path


TOKEN_RE = re.compile(r"'[^']*'|\"[^\"]*\"|\S+")
TITLE_KWS = {"*TITLE1", "*TITLE2", "*TITLE3"}
LINE_IGNORE_KWS = {
    "*RESULTS",
    "*WPRN",
    "*OUTPRN",
    "*WSRF",
    "*OUTSRF",
    "*MONITOR",
    "*GROUP",
    "*AIMWELL",
    "*AIMGROUP",
    "*OUTDIARY",
}
STARLESS_TOP_LEVEL_KWS = {"FILENAMES"}


def strip_comments(line):
    idx = line.find("**")
    return line[:idx].strip() if idx >= 0 else line.strip()


def is_kw(token):
    return token.startswith("*") and not token.startswith("**")


def load_cmg_tokens(filepath):
    filepath = Path(filepath)
    with open(filepath, encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()

    raw_lines = [line.rstrip("\r\n") for line in lines]
    tokens = []
    skip_next_text_line = False

    for lineno, raw in enumerate(lines, 1):
        line = strip_comments(raw)
        if not line:
            continue

        line_tokens = TOKEN_RE.findall(line)
        if not line_tokens:
            continue

        first = line_tokens[0].upper()
        normalized_first = first if first.startswith("*") else f"*{first}" if first.isalpha() else first

        if skip_next_text_line and not first.startswith("*"):
            skip_next_text_line = False
            continue

        if normalized_first in TITLE_KWS:
            skip_next_text_line = len(line_tokens) == 1
            continue

        if normalized_first in LINE_IGNORE_KWS or first == "RESULTS":
            continue

        for token in line_tokens:
            tokens.append((lineno, token))

    return raw_lines, tokens
