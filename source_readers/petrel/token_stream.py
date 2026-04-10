from __future__ import annotations

from pathlib import Path


MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

NOISE_WORDS = {
    "TABLES",
    "NODES",
    "IN",
    "EACH",
    "DEFAULTS",
    "TO",
    "THE",
    "WHOLE",
    "GRID",
    "BOX",
    "FROM",
    "AT",
    "AND",
    "OR",
    "WITH",
}


def strip_comment(line):
    idx = line.find("--")
    if idx >= 0:
        line = line[:idx]
    line = line.strip()
    if line and all(char in "=-*+#" for char in line):
        return ""
    return line


def tokenize_petrel_file(filepath):
    filepath = Path(filepath)
    tokens = []
    with open(filepath, encoding="utf-8", errors="ignore") as handle:
        for lineno, raw in enumerate(handle, 1):
            line = strip_comment(raw)
            if not line:
                continue
            line = line.replace(",", " ")
            idx = 0
            while idx < len(line):
                char = line[idx]
                if char in (" ", "\t", "\r"):
                    idx += 1
                elif char == "'":
                    end = line.find("'", idx + 1)
                    if end < 0:
                        end = len(line) - 1
                    tokens.append((lineno, line[idx : end + 1]))
                    idx = end + 1
                elif char == "/":
                    tokens.append((lineno, "/"))
                    idx += 1
                else:
                    end = idx + 1
                    while end < len(line) and line[end] not in (" ", "\t", "\r", "/", "'"):
                        end += 1
                    tokens.append((lineno, line[idx:end]))
                    idx = end
    return tokens
