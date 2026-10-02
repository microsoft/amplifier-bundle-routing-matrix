# Independent design and implementation review

Scope: the evidence-driven matrix-improvement design and its bounded offline starter. This record describes technical findings and their resolutions, not reviewer configuration, private orchestration history, model-performance evidence or a promotion decision.

This is the original pre-relocation review record. The maintained routing-specific
implementation now lives in routing `evals/`, retaining the library and historical
sample bytes and all 93 original cases. Relocation adds 11 bounded regressions and
requires an explicit benchmark path; it does not ratify the broader method or
qualify live execution. Independent relocation/publication review is a separate gate.

## Design disposition

Independent reviews support the bounded offline method. A fixed root comes from session/settings, not the matrix general role. Unchanged fallback delivery retains task completion but cannot establish the changed model's effect. Methodological support does not qualify live execution or authorize paid work.

| Topic | Finding | Resolution |
| --- | --- | --- |
| Minimum deliverable | A stock runner is not automatically an instrumented evaluation platform | Three offline commands: plan, readiness, analyze. No run command; live execution unsupported. |
| Causal unit | A winner at one effort is conditional; whole-policy effects do not isolate individual model changes | Separate configuration estimands, retain promising candidates and test effort interactions. |
| Rubric validity | Unresolved references, stale criteria and unpenalized false positives can invalidate results | Audit and freeze repaired decision rubrics before unblinding; separate weighted scores from functional/critical outcomes. |
| Calibration and scale | Baseline-only calibration is insufficient; repeats are not independent task families | Instrumented baseline, paired calibration, then exploratory pilot. No population or automatic-promotion claim from five tasks. |
| Outcome versus measurement | Completed trials can contain extraction/grading errors; timeouts can be ungraded | Independent setup, subject outcome, fidelity, grading, cost and cleanup statuses. Missing grades remain missing. |
| Failure classification | Lifecycle stage alone does not identify the cause of a failure | Classify with evidence; controller/environment/provider faults remain distinct or unknown. |
| Provider scope | Whole matrices can legitimately invoke unchanged roles on other providers | Validate calls against the complete arm policy and explicit credential domain, not only one candidate provider. |
| Controller/judge fairness | Pinned model identities alone do not make interaction or assessment blind and isolated | Exact controlled-slice protocols, bounded interactive drivers, immutable artifacts and isolated cross-family assessment. |
| Treatment installation | The existing runner has no generic treatment-injection API | Future arms use pinned AgentSpec definitions and existing evaluation bricks; no invented injection interface. |
| Inheritance observability | Strict inherited effort/tier can erase a treatment | Starter rejects presets, explicit slice pins and fallback changes; future adapters reuse pinned post-clamp planning. |
| Spend and lifecycle | DTU concurrency and per-stage timeouts are not total spend controls | Meter the subject tree, controller, assessment, retries and application calls before live readiness. Unknown price is not zero. |

Tradeoff tolerances, workload/root scope, critical-failure policy, private output location and paid budgets remain human policy decisions.

## Implementation findings and corrections

A separate source review identified two scoring defects. Both were reproduced and fixed with discriminating regressions:

1. **Invalid critical status:** an invalid grade could assert a critical failure which reached the summary. Invalid grades now cannot establish critical pass/fail; permitted partial awards remain visible without becoming valid scores.
2. **Failure hidden by uncertainty:** a valid complete grade failing a necessary success threshold could remain unknown when critical status was unknown. Failed necessary thresholds now establish completion failure independently; satisfied thresholds with unknown critical status still remain unknown.

Before correction, the added cases produced three failures and one passing control. All passed afterward. The correction re-review supports the bounded offline contract, not adapter authenticity or live readiness.

## Original pre-relocation verification

- **93 offline tests passed**, with plugin autoload and pytest caching disabled.
- Ruff lint and formatting checks passed.
- Actual pinned `load_task` and `GraderConfig.from_yaml` matched five task IDs/timeouts, complete criterion identities/point bounds and evaluation weights. No evaluator setup or inference was needed.
- CLI `plan` exited 0 with 30 unique cells, 15 pairs and a 28.5-hour maximum subject-agent-stage allowance. That allowance is not a wall-time forecast or enforced budget.
- CLI `readiness` exited 1 with `plan_valid: true`, `execution_supported: false`, `ready: false` and the unresolved rubric-reference blocker.
- CLI `analyze` exited 0 on explicitly synthetic incomplete receipts. All 30 assigned cells remained visible, including 26 missing; a verified synthetic timeout counted as completion failure; unknown costs and unconfirmed cleanup remained explicit. No ranking or promotional result was emitted.

Publication review is separate from semantic and unit verification. Private reviewer configurations/receipts, raw captures and author-specific workspace layouts are excluded from this source record. The normalizer is not a general-purpose secret scrubber; production inputs require allowlisted redaction and private storage.

## Relocation verification

- **104 offline evaluation tests passed**, retaining the 93 original cases and
  adding 11 path/dependency/import/error regressions. They passed with all
  **858 routing tests** in one isolated process: **962 total, no skips**.
- Ruff **0.15.11**, scoped 88-column formatting and bundle structure passed.
- The reusable planner and historical sample manifest were byte-identical to
  their pre-relocation sources. Production routing code and model policies were
  unchanged by the move.
- Actual TaskSpec and GraderConfig loading matched the five pinned task IDs,
  timeouts and criterion bounds. External task-tree and rubric hashes passed.
- Direct CLI invocation from an unrelated directory matched the library plan.
  Readiness remained execution-unsupported with exit 1; missing
  `--benchmark-root` failed with exit 2, without implicit sibling discovery.
- Independent source/stranger review found no material relocation or publication
  blocker. These checks used no model calls or subject benchmark execution.

## Boundaries

The tooling checks consistency of normalized assertions. It does not authenticate an adapter, attest live call delivery, qualify benchmark rubrics, enforce budgets, contain provider dispatch or prove a model is better. Instrumentation and calibrated grading remain prerequisites to paid comparisons. No raw subject-benchmark output belongs in this source directory.
