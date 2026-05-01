from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "polymarket_paper",)
_ORDER = "order"
_KEY = "key"
DANGEROUS_PATTERNS = (
    "_".join(("create", _ORDER)),
    "_".join(("post", _ORDER)),
    "_".join(("submit", _ORDER)),
    "_".join(("cancel", _ORDER)),
    "_".join(("private", _KEY)),
    "_".join(("wallet", _KEY)),
    "_".join(("signing", _KEY)),
    "/" + "auth" + "/",
    "/" + _ORDER + "s",
)


def scan() -> list[str]:
    findings: list[str] = []
    for directory in SCAN_DIRS:
        for path in directory.rglob("*.py"):
            if path.name == "guardrails.py":
                continue
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            for pattern in DANGEROUS_PATTERNS:
                if pattern in lowered:
                    findings.append(f"{path.relative_to(ROOT)} contains {pattern}")
    return findings


def main() -> None:
    findings = scan()
    if findings:
        raise SystemExit("Paper-only guardrail scan failed:\n" + "\n".join(findings))
    print("paper-only guardrail scan passed")


if __name__ == "__main__":
    main()
