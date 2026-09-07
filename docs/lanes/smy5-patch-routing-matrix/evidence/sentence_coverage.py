#!/usr/bin/env python3
"""ly85's second pass: SENTENCE-COVERAGE, not token coverage.

model_performance-ly85 (lane smy5-patch-wayfinder) found zc6t's checker is
token-only: every backticked command/path/identifier survived, so the file
scored missing_rules: [] while a plain-prose CONSTRAINT had in fact been
dropped. A "clean" row in fidelity-report.json means "no TOKEN missing", never
"nothing missing".

This lane's own first-pass checker had a NARROWER FORM OF THE SAME BLIND SPOT:
it selected rule sentences by KEYWORD (use/do not/never/always/must/...), so a
constraint phrased without any of those words would also have been invisible.

The pass: split stock into sentences; for each, require >= THRESHOLD of its
CONTENT words (stopwords removed) to appear somewhere in lean. Deterministic,
no model, no network, no spend.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

THRESHOLD = 0.60

STOP = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does",
    "for", "from", "has", "have", "in", "into", "is", "it", "its", "of", "on",
    "or", "not", "so", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "to", "up", "use", "used", "using", "was", "what",
    "when", "which", "will", "with", "you", "your",
}


def content_words(text: str) -> list[str]:
    words = re.findall(r"[a-z_][a-z0-9_\-]*", text.lower())
    return [w for w in words if w not in STOP and len(w) > 1]


def sentences(text: str) -> list[str]:
    # keep fenced payload -- a rule can live in a comment inside a fence
    text = text.replace("```yaml", " ").replace("```json", " ").replace("```", " ")
    text = "\n".join(ln for ln in text.splitlines() if not ln.startswith("#"))
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s+", " ", para).strip()
        if not para:
            continue
        out.extend(s.strip() for s in re.split(r"(?<=[.:])\s+", para) if s.strip())
    return out


def main() -> int:
    stock = Path(sys.argv[1]).read_text(encoding="utf-8")
    lean = Path(sys.argv[2]).read_text(encoding="utf-8")
    lean_words = set(content_words(lean))

    flagged = []
    print(f"threshold: {THRESHOLD:.0%} of content words must survive\n")
    for s in sentences(stock):
        cw = content_words(s)
        if not cw:
            continue
        hit = [w for w in cw if w in lean_words]
        cov = len(hit) / len(cw)
        missing = sorted(set(cw) - lean_words)
        mark = "OK " if cov >= THRESHOLD else "!! "
        print(f"{mark}cov={cov:.2f}  {s[:88]!r}")
        if missing:
            print(f"        unmatched: {missing}")
        if cov < THRESHOLD:
            flagged.append((cov, s, missing))

    print("\n=== RESULT ===")
    if flagged:
        print(f"{len(flagged)} sentence(s) below {THRESHOLD:.0%} coverage -- inspect each:")
        for cov, s, missing in flagged:
            print(f"  cov={cov:.2f}  {s!r}\n        unmatched: {missing}")
        return 1
    print(f"0 sentences below {THRESHOLD:.0%}. No plain-prose constraint was dropped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
