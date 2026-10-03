# Evidence-driven routing matrices — design v3

Status: independent methodological review supports the revised offline design. Separate implementation review found two scoring defects; their reproduced cases and corrections are recorded in REVIEW.md. The broader method is a proposal, not a locked contract or a model ranking. Maintained offline tooling lives in this routing bundle's `evals/`; relocation performs no subject benchmark or shipped-policy change.

## Purpose

Improve actual Amplifier outcomes under each matrix's distinct purpose: balanced trades quality, cost and latency; quality prioritizes task quality within explicit resource limits; economy saves cost subject to quality/critical-slice floors; provider-specific matrices optimize within actual backend availability and caller intent. Catalog freshness is a compatibility filter, never a quality score. Explicit caller choices remain constraints.

The unit evaluated is a configuration: backend/mount, model, native effort, tool support, context envelope and routing policy. Equal effort labels across providers are not equal compute. A fixed-setting winner is conditional on that setting, not the universally best model.

## Three evidence layers

1. **Compatibility and fidelity.** Preserve existing offline resolution/provider/intent tests. Capture winning matrix source/hash, actual backend/model, requested versus sent effort, root/child lineage, role requests, retries and fallback choices. Missing or ignored knobs are explicit. A delegate receipt alone is not sent-effort evidence.
2. **Controlled role slices.** Exact task delivery to one named worker role, deterministic clarification/stop protocol where feasible, pinned tools/controller, no recursive delegation unless explicitly part of the slice. Screen 2–3 configurations for one role, keep nondominated/close candidates, then selectively test alternative native efforts. Do not discard a promising model solely because one effort setting lost. Direct-role results establish worker behavior only.
3. **Whole-policy confirmation.** Ordinary delegation, fixed root/controller configuration and sources, candidate matrix change only. Preserve all scheduled outcomes and report changed-role exposure. No exposure => no changed-role attribution, but retain the whole-policy outcome. Calls falling back to an unchanged candidate also mean the intended treatment was not delivered: retain completion, exclude model-effect attribution, and report arm-specific missingness. Individually good role changes must be tested together for interactions. Balanced vs openai changes strict inheritance as well as selections; that is a whole-policy effect, not a model-only comparison.

Each manifest names the estimand: `model` substitution within a backend at fixed native effort; `effort` within one model; `backend_config` substitution (backend/model/native settings together); or `whole_policy`. First starter supports model and effort substitutions only. Backend/whole-policy experiments require their own follow-on validation; reject rather than mislabel them. Root Sol 6.1/high is fixed through the subject's session/settings configuration, not the matrix's `general` role, so results would be conditional on that root. The future adapter must verify actual root requests match that declared configuration.

## Task portfolio and pilot

Use five existing tasks from evaluation revision `7c3646796eea2b042bbe6ffb2de3906d31daa381`: `pdf-hr-q2`, `code-discrepancy-docs-knack`, `cpsc_recall_monitor`, `news_research_tool`, and `markdown_deck_converter`. These are a candidate calibration portfolio, not five already-qualified causal tasks.

| Task | Signal | Required repair/qualification |
|---|---|---|
| pdf-hr-q2 | bounded extraction, factual correctness | frozen hidden reference, functional success definition, ceiling check |
| code-discrepancy-docs-knack | repo-grounded critique | unresolved placeholder; supported-findings precision/recall, explicit false-positive policy |
| cpsc_recall_monitor | executable tool building | stable retrieval fixtures and record recall/precision, not only plausible URLs |
| news_research_tool | research/coding integration | remove model-recency scoring; replace stale date rules; control application API spend/retrieval |
| markdown_deck_converter | editable artifact production | isolated functional execution, actual editability assertions |

Offline rubric audit blocks unresolved `{{...}}` references; flags time-sensitive years/recency/live URL checks and model-choice scoring. Recall tasks need an explicit false-positive policy. Flags require a recorded disposition and repaired rubric hash, not automatic zero-weighting or regex rewriting. Preserve upstream benchmark scores separately from versioned decision rubrics. Before any paid comparison, freeze task instructions, fixture tree, profile, grader criteria/bounds, success definition and critical-failure policy. Include primary functional endpoint and hidden reference provenance; do not admit an arbitrary aggregate score.

Calibrate strong/weak/adversarial outputs and injection handling before experimental grading. Separate objective execution receipts from blind qualitative assessment. Judges receive identity-scrubbed artifacts/receipts, not unrestricted subject settings/credentials/logs. Grade immutable copies or fresh execution sandboxes; concurrent graders must not mutate one shared subject DTU. Arm labels/models/cost are withheld. Validate blinding and order effects, allow judge disagreement and targeted human audit; prompt text alone is not enforcement. Residual leakage risk is recorded. Use cross-family evaluation or two-family adjudication when subject and primary judge share a family; objective checkers need no LLM judge.

### Staged paid work (not started)

A. One serial baseline instrumentation smoke on an objectively gradable offline task.
B. One paired A/B calibration with verified role exposure, identical rubric and controller protocol. Stop for grading/fidelity gaps.
C. Only after those checks and a budget decision: up to five qualified tasks × two arms × three repeats = 30 exploratory subject trials. Example candidate: coding Sol 6.1/high versus Astra 6/high on OpenAI API, other matrix/root settings fixed. This does not pick Astra as a winner. Unqualified tasks stay exploratory or are replaced with a documented new task revision. Randomize arm order within task/repeat blocks; start with two DTUs, move to four only after capacity evidence.

The portfolio's per-task agent-stage timeout allowances sum to 4.75 hours per arm/repetition; 30 cells have 28.5 maximum subject agent-hours, excluding setup/controller/extraction/judging/cleanup. At two concurrent workers, 14.25 hours is the idealized subject-stage ceiling with balanced scheduling—not an elapsed-time forecast or hard lifecycle limit. Real cost/time estimates come from calibration, with evaluator/application costs separate. No invented USD estimate.

These tasks do not qualify all 13 roles. Build a coverage table from actual invoked roles. For each uncovered role, add challenging direct scenarios before promotion: writing with grounded claims/audience constraints; research citation entailment; security hidden-vulnerability recall plus false positives; incident recovery preserving data/rollback; rendered UI accessibility/craft; actual image input/visual grounding; real image output for capable backends. Begin 1–3 high-signal scenarios, expand if evidence cannot discriminate. Native image generation and text/SVG fallback are separate outcomes. Task count alone never establishes sufficient evidence.

## Maintained offline implementation

Location: `evals/` in the routing repository. Routing owns its configurations, scenarios, graders, reuse rules and promotion policy. Generic execution bricks remain in the separate evaluation library as optional development dependencies, never production-hook imports. Relocation preserves the original library and historical sample bytes, including declared source/task/grader locks; these are not current-HEAD attestations. No runtime routing code or generic library API changes.

One reusable Python library `evidence.py`, thin Click `cli.py`, synthetic sample manifest, synthetic evidence fixtures, documentation and offline deterministic tests. Every command requires an explicit local `--benchmark-root PATH`, with no discovery/download; see README for pinned public asset acquisition and offline CI. Commands:
- `plan`: validate locked experiment inputs, one-dimensional treatment, task/rubric/fixture hashes and produce a reproducible balanced-order schedule plus readiness blockers. This never launches anything.
- `readiness`: show plan validity versus execution capability separately. Execution is explicitly **unsupported in this version**, even when offline checks pass.
- `analyze`: reconcile normalized attempt evidence to all scheduled cells, validate IDs/hashes/criteria/statuses, report per-task paired descriptive effects and missingness. No population claims, automatic rankings or promotion.

Interfaces: `plan(manifest, benchmark_root) -> RunPlan`; `readiness(plan) -> ReadinessReport`; `analyze(plan, evidence) -> AnalysisReport`. Reuse evaluation library task loaders for an offline integration check. Do not pull in expensive evaluator/runtime initialization just to plan. Supply an integration blueprint for library bricks, not a fake money-spending `run` command. The independent CI job validates offline contracts using pinned public assets only, not model execution or deployment. No raw production event parser, dashboard, executor, percentile tail claims, golden image or budget-enforcement implementation. A results dashboard is available as a later output once real results exist.

Manifest includes schema/version, hypothesis/estimand, native configuration, two complete arm matrices and hashes, source SHA lock, root/backend topology, pinned driver/judge/extractor identity, task IDs/splits and file tree hashes, target criteria/success/critical rules, repetitions, seed and intended token/time/spend ceilings. Secret values are never accepted; only credential variable names. Candidate changes are validated as one model leaf OR one effort leaf; all other fields including root and provider topology must match. Whole-policy treatment has different requirements and is not smuggled into this validator.

Inheritance observability is a hard planning gate. The current starter accepts only preset-free matrices and a primary exact-model OpenAI candidate for the changed role; it rejects matrices carrying delegation presets, explicit slice pins, inherited root knobs, or changed fallback positions as unsupported. This intentionally avoids reimplementing routing semantics. A future inheritance-aware adapter must reuse the pinned routing planner to derive matrix + root + caller-context **post-clamp** expectations: inherited effort can erase an effort-leaf treatment and a tier ceiling can erase a model-leaf treatment. It must reject observationally equivalent arms before spending and verify calls against post-clamp expectations rather than raw YAML leaves. Regression examples must include strict OpenAI effort override and above-caller-rung clamping. The example balanced coding substitution is preset-free, so it remains supported.

Synthetic fixture scores are explicitly synthetic; analysis marks them non-promotional. Changing a locked source/task/rubric or the schedule invalidates evidence rather than silently regrading.

## Normalized evidence and endpoint eligibility

Maintain independent fields for setup status, subject outcome, treatment evidence, grading validity, cost coverage and cleanup. Do not infer causality or model failure from the last library lifecycle stage alone: errors in `running_agent` may be controller/provider/environment faults. The adapter must provide a classified failure with receipts; ambiguous failures remain unknown. AIUser conclusion is driver status, not ground truth.

- Verified subject timeout/failure counts as failed completion even without a criterion grade. Criteria remain not assessed/missing, not fabricated zeros. Valid partial grading is reported separately.
- Extractor/grader error or incomplete/bounds-invalid rubric => grading invalid; it cannot become a numeric quality win or loss or an established critical pass/fail. A valid complete grade that fails a required success threshold establishes completion failure even if another critical assessment remains unknown.
- Unknown cost blocks USD comparisons, not an otherwise valid quality comparison. Subscription cost is never presumed zero.
- Missing trace/treatment fidelity blocks attribution. Report arm-specific missingness and conservative completion bounds instead of silently dropping losing runs.
- Cleanup failure blocks operational readiness, not already-observed quality outcomes.
- Compare paired task/repeat cells, not arbitrary available records. All scheduled cells appear, including missing/invalid/failed ones.
- Immutable attempt IDs/call IDs, all attempts and costs retained. For this starter, a scheduled cell must have exactly one attempt; multiple attempts block that cell until a preregistered retry policy is implemented. Never select a best attempt or charge only successful retries. Preserve raw evidence outside source control.

Normalized receipts include the exact manifest/schedule, matrix/task/rubric hashes, scheduled cell, outcome evidence IDs, actual subject call configs and required role exposure, complete criterion IDs/bounds/awards, critical pass/fail/unknown, elapsed, itemized measured/unknown costs, and cleanup. External adapters remain a trust boundary; offline validation of an asserted receipt is NOT proof a real call occurred. That trust boundary is a live calibration acceptance item.

Report completion counts/rates with unknown bounds; grade differences only for both-valid criterion-complete pairs with missing-pair counts; observed durations median/max; cost totals only when covered, coverage counts always. Retain model/provider subject failures and classify infrastructure/controller failures separately. Do not report p95 from three observations. Failure/missing rates per arm accompany every score comparison.

## Future live adapter blueprint

Use the existing `TaskSpec`, `AgentSpec`, `TrialSpec`, DTU, installer, AIUser, Extractor and Grader as bricks. Existing `run_trial` owns lifecycle and offers no telemetry hooks; a thin wrapper cannot guarantee the required evidence. Compose a small routing-specific orchestrator or narrowly adapt the existing lifecycle after instrumentation requirements are fixed; avoid forking generic execution logic prematurely.

An arm becomes an `AgentSpec` install definition writing the pinned matrix/settings inside its DTU. Pin CLI/Core/Foundation/routing/providers/evaluator sources; no `@main` or historical stock Opus default in experimental installs. Specify exact secret-env allowlist per subject stratum, separated from evaluator credentials. Whole matrices may intentionally use multiple providers: do NOT reject every non-target call; check each call against the arm's complete unchanged/candidate routing plan. API↔subscription effects remain distinct backend strata.

Controlled slices use exact driver protocol. Interactive whole-policy trials freeze an arm-blind controller policy, bounded turns and recorded interventions; results include that interaction. Evaluator sessions run in an isolated execution environment/DTU, never by launching host Amplifier with a scratch AMPLIFIER_HOME (shared editable installation is not isolated by that variable).

Trace adapters capture request/response/call-ID evidence, parentage and role origin, attempts, effective config, usage/cache/reasoning tokens, timing and pricing provenance using version-specific safe allowlists. Use AI extraction for unconstrained deliverables and bounded deterministic parsing for known telemetry contracts. Never load raw unbounded events into model context. Never overwrite/delete traces while deriving summaries. Test redaction and tree accounting including hidden descendants, repeated call IDs, timeout and partial-response events. Preserve task output before timeout teardown where possible; timeout cancellation is not proof remote spend stopped.

Use fresh subject environment per trial and identity-scrubbed assessment environment. Apply whole-lifecycle timeouts and honest call/token/spend controls, accounting controller+subject descendants+evaluator fan-out+generated applications+retries. Two DTUs is not two model calls. Deny unmetered application egress in causal runs; keep separate live robustness trials if needed. Hard USD caps require supported enforcement or conservative active-worker reservations, never post-hoc totals. Unknown prices require an approved token ceiling/unknown-cost policy. Parsed-but-inert routing preset limits are not controls.

Outputs require an explicit, private git-ignored workspace-root directory outside source repositories, suggested layout `.amplifier/evaluation/routing-matrices/<sortable timestamp>/`. Do not publish raw prompts, outputs, secrets or private paths. Every DTU/image/Gitea resource must be registered immediately and teardown/absence reconciled. Live adapter acceptance includes manifest tracking, secret isolation, trace/grade completeness, cancellation uncertainty and cleanup fault injection. Relocation creates no live resources.

## Statistics and promotion

The pilot is descriptive. Five tasks with repetitions are five distinct tasks, not fifteen independent population samples; no task-cluster interval or noninferiority verdict from this small heterogeneous set. Use per-task paired differences, within-task variability and a defect list to plan confirmation. Retain a Pareto set of promising configurations rather than invent one quality/cost composite winner.

Select one candidate using development data, freeze it, then test untouched held-out task families with a preregistered endpoint, workload weights, practical margin, critical-slice floors, sample size/power and stop rule. Size follows pilot variance and meaningful effect, not a ritual '20 tasks'. Include model × effort interactions and multi-role interactions in follow-up where evidence warrants them. Confirmation coverage must match the role/root/backend claims. Zero observed critical defects is not proof zero true defect rate. Judge disagreement, ceilings/floors and drift can make a result inconclusive.

Promotion requires compatibility/intent preservation, task-quality evidence, acceptable critical-slice results and an explicit quality/cost/latency tradeoff for the matrix philosophy. Numeric tolerances (e.g. quality loss or desired savings) remain steward policy choices in confirmation preregistration, not universal defaults. Insufficient evidence => retain current policy. No auto-update/automerge and no unapproved recurring paid evaluation.

## Next decisions and deliverables

Initial delivery: offline contract and tests. Later: instrumented smoke → paired calibration → approved exploratory pilot → role/effort screening → heldout whole-policy confirmation → evidence-backed matrix PR. Each proposed diff includes task/role/backend coverage, exact config, validity/missingness, per-task results, costs and limitations, plus re-evaluation trigger (catalog/provider/tool/rubric/workload drift).

Only these human choices remain before paid work: target workload/root scope, graded critical-failure policy and acceptable tradeoffs, output location and spend/time envelope. Recommendation: API-only fixed-root first pilot, two objectively gradable repaired tasks first, with remaining three as qualified expansion—not a 13-role sweep.
