# Reusable evaluation program (DRAFT 2026-10-02)

Proposed policy process, not a paid schedule, implemented executor or model recommendation. [Vision](VISION.md) sets the destination; [HANDOFF](HANDOFF.md) separates current evidence and implementation gaps. This document does not change shipped preferences.

Routing owns the evaluation configurations, scenarios, graders, reuse rules and promotion policy. The maintained offline implementation is [`../evals/`](../evals/README.md), with a reusable library and thin Click CLI; it is not another consumer example. Generic execution bricks remain in the separate evaluation library as optional development dependencies, not runtime routing-hook imports.

## 1. What is measured

Measure configurations, not model names in isolation: actual backend, delivered model revision, native effort, root/controller, tools/context, bundle/provider/dispatch versions, environment, task family and grader. Compatibility, controlled worker-role performance and whole-matrix workflow effects are distinct questions. Equal effort labels are not equal compute; a provider family is not a billing connection.

Outcomes remain separate: functional quality and critical defects, successful completion, fidelity/role exposure, failure/missingness, duration, subject-tree cost, evaluation cost and generated-application cost. Preserve unknown cost/revision/grade; never silently zero-fill. Record every scheduled cell and attempt, not only survivors. A fallback that did not exercise the intended model cannot establish that model's effect.

## 2. Hard scenarios from real work, without private fixtures

Failure mechanisms can motivate newly authored fixtures, but protected inputs, source mappings and transcript content are not publishable task data. The following are **new synthetic task proposals**, not calibrated benchmarks:

| Family | Candidate role signal | Synthetic challenge and falsifier |
| --- | --- | --- |
| Responsive geometry | vision, ui-coding | Correct numerical dimensions but independent fixed elements overlap or use the wrong containing box; hidden viewport/control combinations must render correctly. Arithmetic alone cannot pass. |
| Stateful provider handoff | coding, reasoning, fast | Fake providers support incompatible tool schemas; shared state survives A→B→A incorrectly. A recording transport checks every request, not initial setup. |
| Non-vacuous verification | critique, general, coding, fast | Reverting the fix also removes its regression; zero selected tests looks green. Require retained test, correct failing reason and genuine fixed pass. |
| Selective privacy / trusted identity | security-audit, critique, writing | Invented secrets mixed with useful criticism; synthetic message identities include spoofed display names. Grade residual sensitivity and over-removal separately. |
| Observation-window reasoning | reasoning, research, fast | Censored timestamps, cross-thread replies and a source that cannot observe outbound messages. Unavailable evidence must not become confident absence. |
| Quantitative brief and rendering | writing, research, critique, vision | Generated logs have different units and three exposure classes; independently computed totals and rendered layout must agree. Illustration cannot be relabeled measurement. |

Role labels are hypotheses until actual role requests, calls and artifacts prove exposure. Agent names do not establish model_role. Related task variants must remain clustered rather than counted as independent observations. Evidence about an original failure does not qualify a newly built fixture automatically.

Cancellation-safe persistence, serialization-boundary repair and recovery-worker lifecycle are **provisional task ideas**, not admitted fixtures: they need reproduced defects and executed qualification. Creative/image-gen coverage remains a gap; visual multiple-choice or computer-use scores cannot substitute for creation quality or UI-coding.

### Admission and hardness gates

Before a scenario can influence preferences, pass **two separate gates**:
1. **Privacy and rights clearance:** extract only a generic causal failure specification in authorized private storage. Independently invent a different domain, organization structure, content, names, timelines, numerical inputs and artifacts. Remove identifying combinations and recognizable business architecture, not just individual PII strings. Keep the private-to-synthetic mapping private; review the resulting fixture as a stranger. Token replacement in a transcript is insufficient.
2. **Challenge and grader qualification:** preserve the causal decision problem, uncertainty, state transitions and adversarial edge cases without requiring the original failure to recur. Validate licenses/reference access and positive/negative/malformed grader cases, including a genuinely discriminating good/bad artifact pair. Non-vacuous execution is mandatory.
3. Calibrate actual configurations across relevant models/providers on development variants; inspect observed pass/failure distributions, critical defects, ceilings/floors and disagreement. Do not prescribe a weak-model failure rate or count privacy clearance as evidence of difficulty.
4. Freeze generator/task/fixture/grader versions and lineage-aware development/holdout splits. Keep hidden keys and private holdout variants out of subject context and public source.
5. Qualify role exposure and measurement/budget/lifecycle adapters before comparisons; admit no quality conclusion from an offline planner or synthetic receipt.

For example, an observation-limit challenge can become a fabricated greenhouse sensor-maintenance study instead of a messaging workflow: missing return telemetry cannot establish that a repair never happened, and right-censored windows must remain uncertain. Generate new dates, distributions and answer keys rather than preserving actual counts or operational thresholds. The example is a mechanism specification, not a cleared fixture or evaluated task.

### Operational privacy clearance

The distiller and fixture author are separate execution contexts. The author must never have received the private records, including through inherited conversation or shared retrieval context. Before authoring, an authorized privacy reviewer approves the abstract specification for the restricted handoff; original purpose and business details are not passed through merely because identifiers were removed.

The completed fixture then receives an independent stranger/nonrecognition review and rights check. Record private receipts naming the responsible reviewer, exact artifact revision, forbidden disclosures considered, decision and unresolved risks. Clearance is `approved`, `rejected` or `unqualified`; no approved result exists until those checks finish. A public release records only a separate approved release reference and its limitations, never the original record-to-fixture map. Uncertain recognizability, rights or an exception to the privacy policy goes to the steward; routine execution of the already authorized safe process is not another blanket approval gate.

Difficulty must distinguish useful behavior at current capability levels without turning every case into an impossible trick. Strong/weak/adversarial reference artifacts calibrate graders; real model observations calibrate task hardness. Public exposure can contaminate tasks, so preserve a frozen regression core and rotate fresh hidden families under an explicit rule.

## 3. Public source portfolio

Fetch pinned assets only after rights, setup and grader checks. These inspected revisions are research candidates, not ready execution adapters. Original versus modified grading/budgets are separate metric names; no internal constrained run is called leaderboard-equivalent.

| Source and inspected code revision | Useful signal | Required caveats / admission |
| --- | --- | --- |
| [Terminal-Bench 4.0.0](https://github.com/harbor-framework/terminal-bench/tree/452bf305c6daa62fc59061d22133a7cbc7c1572e) | coding, terminal operations, artifact execution | Current suite is continuous; some tasks allow eight hours/GPU/multiple containers. Use bounded CPU internal profiles. Review incorporated images/projects/licenses. |
| [Terminal-Bench 2.1](https://github.com/harbor-framework/terminal-bench-2-1/tree/7131e4375048a0e408a8fb404b5f499d726b695b) | frozen historical execution anchor | Apache-2.0 declaration; task/environment drift and public solutions. Not the same suite as TB4. |
| [tau2-bench repository, v1.0.1](https://github.com/sierra-research/tau2-bench/tree/fc0055dc4e0a316c3f83133267fbd6faaa770992) | stateful policy/tool use and communication | Now tau3-branded; MIT declaration. Pin user simulator. End state alone misses intermediate unsafe mutations; banking across changed revisions is incomparable. |
| [BrowseComp reference](https://github.com/openai/simple-evals/blob/652c89d0ca9df547706735883097e9537d40dc47/browsecomp_eval.py) | difficult persistent browsing | MIT code; no plaintext dataset redistribution requested by publisher. Inspected parser returns `correct: yes` but scoring compares `yes`: adapter blocked until positive/bad/parser tests and explicit correction. Data asset hash unresolved, no answers acquired. |
| [LiveCodeBench](https://github.com/LiveCodeBench/LiveCodeBench/tree/28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24) | algorithmic coding/reasoning | Code MIT; inspected v6 data through April 2025 is not fresh 2026 evidence. Data license ambiguous; remote-code/pickle acquisition needs isolated audit. |
| [OSWorld-Verified source](https://github.com/xlang-ai/OSWorld/tree/b138d348256078fa634fc3b73567a7337c793e6b) | real computer-use workflows | Apache code; VM/app/document rights separate. Account-free local apps; pin action/observation interface, resolution and step limits. Not UI-coding proof. |
| [CyberSecEval4 source](https://github.com/meta-llama/PurpleLlama/tree/172c1074069eb88ec834124272c1b1c4f8893445/CybersecurityBenchmarks) | defensive vulnerability repair and injection resilience | Benchmark subdirectory MIT, not weight licenses. Defensive allowlist only. AutoPatch sample guidance is about 500 GB; deep optional evaluation, not lightweight default. |
| [MMMU-Pro code](https://github.com/MMMU-Benchmark/MMMU/tree/268471d0d488258990025331c7528359c324aa25) | visual/multimodal reasoning | Apache declarations with source copyright caveats. Official parser may random-guess on failure; reproduce/report or version a fail-closed metric. Not creative output quality. |

Data pins for acquisition manifests: LiveCodeBench `livecodebench/code_generation_lite@0fe84c3912ea0c4d4a78037083943e8f0c4dd505`; MMMU `MMMU/MMMU_Pro@563f3e84bb3b90893083a1f039cfa13077f2302b`. Public access is not permission to vendor source imagery or publish hidden answers. Audit every adapter's code/data notices and oracle separation. Unknown rights or missing hashes block acquisition/redistribution as appropriate.

Writing/creative/design quality needs new non-personal briefs, observable rubrics, blinded order-balanced judgments and a human bias check. Benchmark topic names are not direct role tests. Existing broad agent tasks are useful calibration scaffolds, not sufficient hard coverage for every role.

## 4. Reuse ledger, not a new leaderboard

An append-only **evidence index proposal**, not a frozen conformance ledger, separates:
- subject conditions and actual delivered revision/call tree;
- assessment conditions and criterion evidence;
- accounting conditions and rate provenance;
- publication class and permissions.

The full comparability envelope is private, because connections, endpoint identity, prompts and raw lineage may be sensitive. Its lookup ID is opaque/random and its mapping remains private. A public allowlisted `subject_class` is weaker: public code/task/config revisions and safe native settings only. It **cannot prove exact comparability**. Do not publish private envelope IDs or hashes of low-entropy identities/secret-bearing config. A release may mint a separate public evidence ID after export review; public claims state the assurance and reproduction limits.

Define a preregistered **eligibility projection** of the envelope: assigned task/version, environment, allowed tools, root/controller, protocol, native settings, budget and assessment conditions, excluding the declared treatment. Keep observed call trees, chosen tool sequences, completion/failure, costs and latency in the outcome record, not equality requirements. These can be consequences of changing the model; requiring equality would discard meaningful differences and bias results toward survivors.

Actual delivered model/binding and trace completeness verify treatment and measurement, not equality of behavior. Classify wrong-target/protocol violations separately. Preserve all assigned cells for whole-policy/intention-to-treat reporting; any per-protocol subset must be predeclared with excluded counts and missing-outcome bounds. Never decide reuse eligibility from a favorable score or successful execution.

An exact-comparable label requires revision/generation-level delivered-model evidence and unchanged relevant binding identity, not an alias string alone. Provider-invisible or unresolved served revisions remain historical/uncertain reuse; contemporaneous trials may still report conditional comparisons with that limitation. Do not confuse a strategy's semantic generation with the provider's delivered model revision.

| Reuse disposition | Allowed use | Not implied |
| --- | --- | --- |
| Exact-comparable | Equal preregistered assigned conditions except declared treatment, qualified task/grader and validated delivered identity | Identical observed call tree/outcome/cost, or public class/hash equality proves equivalence |
| Regradable | Retained artifacts support the revised grader; all relevant arms regraded with old/new rubrics retained | A new execution, latency observation or solved task |
| Accounting-only | Complete retained usage repriced using cited rates/currency/units and revision | Fresh measured spend or API-equivalent subscription cost |
| Historical/context-only | Background evidence when task/runtime or exposure identity changed | Current promotion evidence |
| Invalid/unverifiable | Audit/fault diagnosis with missing/corrupt traces, grades or identity explicit | A quality winner or zero-filled score |

Regrading requires sufficient artifacts and legitimate retained reference access. Missing artifacts cannot be reconstructed by a judge's guess. Changed tool behavior or prompt/context needs fresh execution, not relabeling old grades. Public exports cannot independently verify private endpoint/account equivalence; say so.

## 5. Light new-model cycle

A targeted cycle, not a full rerun of all historical models:
1. Identify affected roles/capabilities and classify every prior result's reuse eligibility.
2. Plan candidate versus incumbent on qualified frozen families plus a small untouched rotating portion. Keep root/backend/runtime fixed and verify actual delivered model/effort.
3. Reuse unchanged eligible historical cells for context, but run a contemporaneous incumbent anchor to detect service/provider drift.
4. Apply predeclared pairing, replication/escalation and stop rules with one total budget. Ambiguous/flaky/safety-critical comparisons escalate symmetrically; never selectively retry losing arms.
5. Report regressions, missingness, critical defects and uncertainty. Screening nominates configurations; it does not automatically promote a matrix change.

Predeclare the incumbent-anchor check and its consequence per family using observed calibration variability. If the fresh anchor materially disagrees with retained evidence or its identity/fidelity cannot be established, mark the family's reused cells historical for the current decision and escalate or repeat the paired comparison symmetrically. Insufficient anchor observations mean uncertain reuse, not automatic stability. Do not select a favorable historical band after seeing the new candidate.

No universal task count is prescribed. Select a small pack that actually discriminates at the target role/caliber. Repeat observations are within-family stochasticity, not new task populations. Prices, aliases and silent provider revisions may drift even with the same model string.

Each recommendation packet must expose per-role evidence status: `calibrated`, `provisional` or `none`, with qualified family references, actual exposure, version and limitations. A role with no qualified family enters through scenario/grader qualification and deeper calibration, not a light refresh that pretends a baseline exists. One qualified family permits targeted screening but does not by itself justify promotion or broad role coverage. These are proposed evidence metadata, not additions to shipped matrix YAML.

## 6. Deeper recalibration

| Trigger | Required reevaluation |
| --- | --- |
| New model series/context/effort/tool behavior or unknown alias change | Candidate/incumbent affected-role screening; uncertain delivery revision treated explicitly |
| Bundle/module/provider/orchestrator/tool/context/dispatch update | Compatibility contracts plus live affected-role/workflow tasks; do not reuse model-only results blindly |
| New role/matrix/workload or missing modalities | Qualify new direct scenarios and ordinary workflow exposure, then holdout confirmation |
| Task saturation/floor, leakage, grader or benchmark revision | Fresh families, strong/weak grader calibration, versioned bridge; preserve historical core |
| Model and environment changed together | Controlled old/new bridge or factorial conditions where feasible; otherwise label causal attribution unavailable |
| Broad regression or decision-changing uncertainty | Broader eligible configurations, independent families, preregistered margins/power and sufficient repeats |

A saturation trigger is preregistered using observed score distributions, grader room and reliability, not hindsight after a desired model wins. No fixed '20 tasks' or '16 probes' establishes statistical sufficiency. Select candidates on development families; reserve untouched confirmation families and workload weights. Whole-matrix interactions and strict inheritance need end-to-end confirmation before deployment.

## 7. Isolation and publication

Acquisition, subject execution and assessment have separate environments and credentials. No personal HOME/browser/key-store/workspace mounts; use new synthetic/account-free assets and pinned dependencies/images. Restrict network egress, unmetered generated-application calls and benchmark-answer retrieval. Disable automatic telemetry, public uploads and trajectory submission where frameworks default to them. Grade hidden references only in assessor-side storage, not alongside solver-visible prompts.

Store raw captures, configs, artifacts, screenshots and source maps privately outside source repos. Declare retention/deletion policy separately; this program does not authorize deleting source-server records. Record every external resource at creation and reconcile teardown/absence. Cancellation is not proof remote work or spend stopped. Whole-tree subject/controller/assessment/retry costs and global lifecycle limits must be supported before paid work; concurrent DTU limits are not LLM-call caps.

Commit only public mechanisms/specs, newly authored synthetic development fixtures, versioned fetch/adapters, safe env-name configs, tests, approved schemas and allowlisted summaries. Keep private session/account/connection/host IDs, paths, endpoints, prompts, raw answers, hidden keys, and secret/private-content-derived fingerprints out of source and exports. A publicly visible GitHub alias is usable only for necessary attribution to a verified public source; it grants no permission for associated private identities.

Exports need schema allowlists, private-shape/secret scans, locally derived identity checks, small-cell/unique-example review and fresh-context stranger review. Fail closed before source commits, public CI artifacts, dashboards or links. Regex redaction alone cannot establish absence of PII. Do not publish a private fixture in a hashed disguise. In-repo tests use fabricated identities, never a static deny-list of actual private names.

## 8. Current boundary and next acceptance

No runner, archive, adapters or recurring paid jobs are implemented by this proposal. The maintained routing [`evals/`](../evals/README.md) tooling verifies an offline contract only; it rejects preset-bearing and non-primary OpenAI leaf treatments. Its historical synthetic sample and task/grader locks are preserved, including known rubric defects. Every CLI command requires an explicit `--benchmark-root`; the independent offline CI job checks out public evaluation assets at the sample's pinned revision without executing upstream scripts or installing its runtime. A recommendation consumer contract is deferred until a real result consumer and discriminating fixtures exist; this program must not create a fake pass ledger.

Next acceptance: independently authored hard synthetic task/grader pairs; approved external acquisition/license manifests; versioned normalized telemetry and reuse comparisons; instrumented isolated baseline and paired calibration; measurable budget/cleanup behavior. Then approve the targeted cycle or deeper study. Evidence packets propose policy diffs; they do not silently edit defaults.

### Separate Anchors development slice (2026-10-06)

The executable [Anchors interval-repair adapter](../evals/README.md#foundation-hosted-anchors-interval-repair)
is separate from offline v1 and the original restricted smoke. It loads/pins
real Anchors before an explicit task/tool/telemetry ablation, uses stock delegate
and a real nonrecursive builder, and preserves configured endpoint and native
settings under intercepted transport. Its controller code reuses the existing
append-only ledger, quote/usage semantics, injection mount and transport custody.
Observe-only cost has no dollar stop by default; missing prices remain unknown.
Finite request/token/body/time limits remain mandatory.

The new mathematical repair family and public controls have no private-source
mapping. The grader is objective, separately supplied private cases are never
solver inputs, and retained regression must be assertion-red on original code
and green on repaired code with nonempty selection. Controller receipt tests
are not executed-assessor qualification or hostile-code tamper resistance.

Discovery accesses the selected provider instance, snapshots exact latest
bounded family/tier/modality IDs with explicit live/fallback/manual/failed
provenance, and makes no historic sweep or matrix edit. Versioned reuse compares
assigned source/task/grader/runtime/root/tools/settings/budgets and delivered
model/binding identity, never favorable outcomes. A contemporaneous incumbent
anchor remains mandatory; changed candidates receive fresh cells. One family
and deterministic two-cycle tests do not establish promotion or service stability.

Parent-owned remaining gates: tester-provisioned isolated source installation;
external credential authority and independently enforced solver egress;
actual good/bad/malformed/hanging assessor runs with cleanup; configured catalog
discovery followed by the live current-model pair. Source/mock proofs are not
those checks. No DTUs, paid calls, credentials, generic platform, shipping
matrix changes or user-local evaluation product are supplied by this slice.
