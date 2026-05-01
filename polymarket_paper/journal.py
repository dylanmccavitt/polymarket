from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


REQUIRED_LOGS = (
    "markets.jsonl",
    "books.jsonl",
    "quotes.jsonl",
    "fills.jsonl",
    "arb_alerts.jsonl",
    "risk_events.jsonl",
)


def ensure_run_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name in REQUIRED_LOGS:
        (path / name).touch(exist_ok=True)
    return path


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError as exc:
                rows.append(
                    {
                        "type": "parse_error",
                        "file": str(path),
                        "line": line_number,
                        "error": str(exc),
                    }
                )
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows
