#!/usr/bin/env python3
"""Re-verify lean-vs-stock fidelity for context/routing-instructions.md AT TODAY'S HEAD.

Does NOT inherit zc6t's fidelity table. It mechanically enumerates every atom in
the STOCK file that a reader could act on -- inline-code literals, fenced-block
payload lines, code-comment labels, and imperative rule sentences -- and reports
which are absent from the LEAN file.

An atom passes one of three ways, and the three are NOT interchangeable:

  verbatim            the exact stock string is in the lean file
  EQUIVALENCES        the surface form changed; a named lean substring carries
                      the same instruction. Listed one by one, reviewable.
  DROPPED_BY_DESIGN   the atom is genuinely gone. Each entry states WHY it is
                      not a rule/constraint/command/pointer. These are printed
                      loudly in the result -- never silently absorbed.

Anything else is a fidelity loss and exits non-zero.

Usage: fidelity_check.py <stock.md> <lean.md>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# (stock atom, lean substring carrying the same instruction)
EQUIVALENCES: list[tuple[str, str]] = [
    ("This session uses the routing matrix system for model selection.",
     "Model selection uses the routing matrix."),
    ("injected into your context every turn", "injected every turn"),
    ("Use those role names \u2014 they are authoritative.", "is authoritative"),
    # NOTE the referent widens: stock forbids relying on a list written "here"
    # (this file); lean forbids relying on a list written "elsewhere" (anywhere
    # but the live injection). Broader, not weaker -- lean carries no list.
    ("Role sets and descriptions differ per matrix; do not rely on any list written down here.",
     "role sets and descriptions differ per matrix; never rely on a list written down elsewhere"),
    ("Use `model_role` in agent frontmatter to declare what kind of model your agent needs:",
     "Agent frontmatter `model_role`"),
    ("Fallback chains are tried left-to-right.", "tried left-to-right"),
    ("Always end with `general` or `fast`.",
     "always end a chain with `general` or `fast`"),
    ("When delegating to sub-agents, you can override the model role:",
     "Delegators may override per call"),
    ("For detailed role definitions, decision flowchart, model tier grid, and fallback chain "
     "guidance, use `load_skill(skill_name='role-definitions')`.",
     "Role definitions, decision flowchart, model tier grid, fallback guidance: "
     "`load_skill(skill_name='role-definitions')`"),
    # the delegation example moves from a JSON object to the delegate() call form
    ('"agent": "foundation:explorer"', 'agent="foundation:explorer"'),
    ('"model_role": "vision"', 'model_role="vision"'),
    # the three frontmatter forms keep their payload; only fence + column
    # alignment + trailing label go
    ("# single role", "single (`model_role: coding`)"),
    ("# fallback chain (specific \u2192 general)",
     "fallback chain tried left-to-right specific \u2192 general"),
    ("# utility agent", "utility (`model_role: fast`)"),
]

# (stock atom, why its loss is not a fidelity loss)
DROPPED_BY_DESIGN: list[tuple[str, str]] = [
    ('"instruction": "Analyze these UI screenshots..."',
     "illustrative filler text for the example's instruction argument; carries no "
     "rule, constraint, command or pointer. Lean keeps the argument itself "
     "(instruction=\"\u2026\")."),
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().rstrip(",")


def inline_literals(text: str) -> list[str]:
    stripped = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return [m.group(1) for m in re.finditer(r"`([^`\n]+)`", stripped)]


def fenced_payload(text: str) -> list[str]:
    """Fenced-block lines, split into payload and trailing '# label' atoms."""
    out: list[str] = []
    for block in re.findall(r"```[a-z]*\n(.*?)```", text, flags=re.DOTALL):
        for line in block.splitlines():
            line = line.strip()
            if not line or line in {"{", "}"}:
                continue
            if "#" in line:
                payload, _, comment = line.partition("#")
                if payload.strip():
                    out.append(_norm(payload))
                out.append(_norm("#" + comment))
            else:
                out.append(_norm(line))
    return out


def rule_sentences(text: str) -> list[str]:
    """Instruction-bearing sentences. Fenced blocks are removed FIRST, so a
    sentence either side of a fence must not be glued across the gap -- split
    on blank lines before splitting on '. '."""
    prose = re.sub(r"```.*?```", "\n\n", text, flags=re.DOTALL)
    prose = "\n".join(ln for ln in prose.splitlines() if not ln.startswith("#"))
    sentences: list[str] = []
    for para in re.split(r"\n\s*\n", prose):
        para = _norm(para)
        if not para:
            continue
        sentences.extend(s.strip() for s in re.split(r"(?<=\.)\s+", para) if s.strip())
    keywords = ("use ", "Use ", "do not", "Do not", "never", "Never", "always",
                "Always", "must", "can ", "are tried", "end with", "authoritative")
    return [s for s in sentences if any(k in s for k in keywords)]


def covered(atom: str, lean: str) -> tuple[bool, str]:
    if atom in lean:
        return True, "verbatim"
    a = _norm(atom)
    if a in _norm(lean):
        return True, "verbatim (whitespace-normalised)"
    for stock_form, lean_form in EQUIVALENCES:
        if a == _norm(stock_form) and lean_form in lean:
            return True, f"equivalent -> {lean_form!r}"
    for stock_form, reason in DROPPED_BY_DESIGN:
        if a == _norm(stock_form):
            return True, f"DROPPED-BY-DESIGN -- {reason}"
    return False, "MISSING"


def main() -> int:
    stock = Path(sys.argv[1]).read_text(encoding="utf-8")
    lean = Path(sys.argv[2]).read_text(encoding="utf-8")

    groups = {
        "inline-code literal": inline_literals(stock),
        "fenced-block atom": fenced_payload(stock),
        "rule sentence": rule_sentences(stock),
    }

    missing: list[str] = []
    dropped: list[str] = []
    print(f"stock chars: {len(stock)}   lean chars: {len(lean)}   "
          f"saved: {len(stock) - len(lean)} ({(len(stock) - len(lean)) / len(stock):.2%})")
    for kind, atoms in groups.items():
        print(f"\n--- {kind} ({len(atoms)}) ---")
        for atom in atoms:
            ok, how = covered(atom, lean)
            print(f"{'OK ' if ok else '!! '}{atom!r}  ->  {how}")
            if not ok:
                missing.append(f"{kind}: {atom!r}")
            elif how.startswith("DROPPED-BY-DESIGN"):
                dropped.append(f"{kind}: {atom!r} -- {how}")

    print("\n=== RESULT ===")
    if dropped:
        print(f"{len(dropped)} atom(s) DROPPED BY DESIGN (declared, not silent):")
        for d in dropped:
            print("  *", d)
    if missing:
        print(f"\nFIDELITY LOSS -- {len(missing)} atom(s) in stock, absent from lean:")
        for m in missing:
            print("  -", m)
        return 1
    print("\n0 undeclared drops: every rule, constraint, command and pointer in stock "
          "survives in lean (verbatim, or via a declared equivalence).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
