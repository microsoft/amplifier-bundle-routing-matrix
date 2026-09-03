#!/usr/bin/env python3
"""Adjudicate the ytg lane's pre-registered gates against the RUNLOGs.

Reads `<capture>/runs/<arm>/RUNLOG.jsonl` and decides each gate EXACTLY as
`docs/lanes/ytg-presets-revision/PREREGISTRATION.md` §3 states it -- the
thresholds are transcribed here as literals so a reader can diff the two.

No gate is computed from a threshold derived at analysis time. If a number
below does not appear in PREREGISTRATION.md, that is a bug in this file.

Usage: analyze_ytg.py <capture_root> [--json]
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

ARMS = ("cf", "ctl", "guard")


def load(cap: Path) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {a: [] for a in ARMS}
    for arm in ARMS:
        p = cap / "runs" / arm / "RUNLOG.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out[arm].append(json.loads(line))
            except Exception:
                pass
    return out


def rows(recs: list[dict[str, Any]], scn: str) -> list[dict[str, Any]]:
    return [r for r in recs if r.get("scenario") == scn]


def nums(rs: list[dict[str, Any]], key: str) -> list[float]:
    vals = []
    for r in rs:
        v = r.get(key)
        try:
            if v is not None:
                vals.append(float(v))
        except (TypeError, ValueError):
            pass
    return vals


def med(v: list[float]) -> float | None:
    return statistics.median(v) if v else None


def fmt(v: float | None, nd: int = 4) -> str:
    return "n/a" if v is None else f"{v:.{nd}f}"


def main() -> int:
    cap = Path(sys.argv[1])
    data = load(cap)
    report: dict[str, Any] = {"per_run": {}, "gates": {}}

    for arm in ARMS:
        for scn in ("s1", "s3"):
            rs = rows(data[arm], scn)
            if not rs:
                continue
            report["per_run"][f"{arm}-{scn}"] = [
                {
                    "run": r.get("run"),
                    "completion": r.get("completion"),
                    "cost_usd": r.get("cost_usd"),
                    "wall_s": r.get("wall_s"),
                    "host_wall_s": r.get("host_wall_s"),
                    "score": r.get("score"),
                    "llm_calls": r.get("llm_calls"),
                    "tree_sessions": r.get("tree_sessions"),
                    "cache_read_share_pct": r.get("cache_read_share_pct"),
                    "s1_anchors": r.get("s1_anchors"),
                    "models": r.get("models"),
                }
                for r in rs
            ]

    cf3, ctl3 = rows(data["cf"], "s3"), rows(data["ctl"], "s3")
    cf1, ctl1 = rows(data["cf"], "s1"), rows(data["ctl"], "s1")
    g3 = rows(data["guard"], "s3")

    # ---- G-CF1: S3 cost, median lower AND ranges non-overlapping -----------
    c_cf, c_ctl = nums(cf3, "cost_usd"), nums(ctl3, "cost_usd")
    if c_cf and c_ctl:
        lower = med(c_cf) < med(c_ctl)  # type: ignore[operator]
        sep = max(c_cf) < min(c_ctl)
        report["gates"]["G-CF1"] = {
            "verdict": "PASS" if (lower and sep) else "FAIL",
            "median_cf": med(c_cf),
            "median_ctl": med(c_ctl),
            "range_cf": [min(c_cf), max(c_cf)],
            "range_ctl": [min(c_ctl), max(c_ctl)],
            "median_lower": lower,
            "ranges_non_overlapping": sep,
            "n": [len(c_cf), len(c_ctl)],
            "note": "complete separation at n=2/side has p=1/6=0.167 under exchangeability",
        }
    else:
        report["gates"]["G-CF1"] = {"verdict": "NOT-MEASURED"}

    # ---- G-CF2: S3 wall, median <= control's ------------------------------
    w_cf, w_ctl = nums(cf3, "wall_s"), nums(ctl3, "wall_s")
    if w_cf and w_ctl:
        report["gates"]["G-CF2"] = {
            "verdict": "PASS" if med(w_cf) <= med(w_ctl) else "FAIL",  # type: ignore[operator]
            "median_cf": med(w_cf),
            "median_ctl": med(w_ctl),
            "range_cf": [min(w_cf), max(w_cf)],
            "range_ctl": [min(w_ctl), max(w_ctl)],
        }
    else:
        report["gates"]["G-CF2"] = {"verdict": "NOT-MEASURED"}

    # ---- G-CF3: quality FLOOR, median >= 75 and no run < 70 ---------------
    s_cf = nums(cf3, "score")
    if s_cf:
        report["gates"]["G-CF3"] = {
            "verdict": "PASS" if (med(s_cf) >= 75 and min(s_cf) >= 70) else "FAIL",  # type: ignore[operator]
            "median": med(s_cf),
            "min": min(s_cf),
            "all": s_cf,
            "thresholds": {"median_min": 75, "run_min": 70},
        }
    else:
        report["gates"]["G-CF3"] = {"verdict": "NOT-MEASURED"}

    # ---- G-CF4: S1 completion + cost lower --------------------------------
    if cf1 and ctl1:
        comp = all(r.get("completion") == "complete" for r in cf1)
        c1_cf, c1_ctl = nums(cf1, "cost_usd"), nums(ctl1, "cost_usd")
        lower = bool(c1_cf and c1_ctl and med(c1_cf) < med(c1_ctl))  # type: ignore[operator]
        report["gates"]["G-CF4"] = {
            "verdict": "PASS" if (comp and lower) else "FAIL",
            "cf_all_complete": comp,
            "cf_completions": [r.get("completion") for r in cf1],
            "ctl_completions": [r.get("completion") for r in ctl1],
            "median_cf": med(c1_cf),
            "median_ctl": med(c1_ctl),
            "range_cf": [min(c1_cf), max(c1_cf)] if c1_cf else None,
            "range_ctl": [min(c1_ctl), max(c1_ctl)] if c1_ctl else None,
            "cf_anchors": [r.get("s1_anchors") for r in cf1],
            "ctl_anchors": [r.get("s1_anchors") for r in ctl1],
        }
    else:
        report["gates"]["G-CF4"] = {"verdict": "NOT-MEASURED"}

    # ---- G-GUARD leg (c): live anthropic mapping --------------------------
    if g3:
        gs, gc = nums(g3, "score"), nums(g3, "cost_usd")
        comp = all(r.get("completion") == "complete" for r in g3)
        ok = bool(
            comp
            and gs
            and med(gs) >= 70  # type: ignore[operator]
            and min(gs) >= 38
            and gc
            and med(gc) <= 1.30  # type: ignore[operator]
        )
        report["gates"]["G-GUARD-c"] = {
            "verdict": "PASS" if ok else "FAIL",
            "completions": [r.get("completion") for r in g3],
            "scores": gs,
            "median_score": med(gs),
            "costs": gc,
            "median_cost": med(gc),
            "thresholds": {
                "median_score_min": 70,
                "run_score_min": 38,
                "median_cost_max": 1.30,
            },
            "baseline_haiku_high": {
                "median_cost": 0.8649,
                "median_wall_s": 362.2,
                "median_score": 78,
                "score_range_n10": [38, 88],
            },
        }
    else:
        report["gates"]["G-GUARD-c"] = {"verdict": "NOT-MEASURED"}

    # ---- SECONDARY, NOT A GATE: did the matrix bind at all? ----------------
    #
    # A routing matrix governs SUB-AGENT resolution. A run whose agent never
    # delegated (tree_sessions == 1) exercised no matrix decision at all: both
    # arms are then just "terra@medium doing its own work", and any cost
    # difference between them is run-to-run variance, not treatment. This block
    # exposes that directly. It is reported ALONGSIDE the gates and never
    # substituted for them -- the gates were pre-registered on all runs and are
    # decided on all runs.
    def mech(arm: str, scn: str) -> dict[str, Any]:
        rs = rows(data[arm], scn)
        out = []
        for r in rs:
            models = r.get("models") or {}
            cheap = sum(v for k, v in models.items() if "luna" in k or "mini" in k or "nano" in k)
            out.append(
                {
                    "run": r.get("run"),
                    "tree_sessions": r.get("tree_sessions"),
                    "delegated": (r.get("tree_sessions") or 0) >= 2,
                    "cheap_rung_calls": cheap,
                    "total_calls": r.get("llm_calls"),
                    "cost_usd": r.get("cost_usd"),
                    "wall_s": r.get("wall_s"),
                }
            )
        deleg = [o for o in out if o["delegated"]]
        return {
            "runs": out,
            "n_delegated": len(deleg),
            "n_total": len(out),
            "median_cost_delegated_runs": med([o["cost_usd"] for o in deleg if o["cost_usd"]]),
            "median_wall_delegated_runs": med([o["wall_s"] for o in deleg if o["wall_s"]]),
        }

    report["mechanism_check_SECONDARY"] = {
        f"{a}-{s}": mech(a, s)
        for a in ARMS
        for s in ("s1", "s3")
        if rows(data[a], s)
    }

    # ---- spend -------------------------------------------------------------
    total = 0.0
    for arm in ARMS:
        for r in data[arm]:
            try:
                total += float(r.get("cost_usd") or 0)
            except (TypeError, ValueError):
                pass
    report["measured_spend_usd"] = round(total, 4)

    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    for k, v in report["per_run"].items():
        print(f"\n== {k} ==")
        for r in v:
            print(
                f"  run {r['run']}: {r['completion']:12s} cost=${fmt(r['cost_usd'])} "
                f"wall={fmt(r['wall_s'], 1):>8s}s score={r['score']} "
                f"calls={r['llm_calls']} cache={r['cache_read_share_pct']}"
                + (f" anchors={r['s1_anchors']}" if r.get("s1_anchors") else "")
            )
    print("\n== GATES ==")
    for k, v in report["gates"].items():
        print(f"  {k}: {v['verdict']}")
        for kk, vv in v.items():
            if kk != "verdict":
                print(f"      {kk}: {vv}")
    print(f"\nmeasured spend this lane: ${report['measured_spend_usd']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
