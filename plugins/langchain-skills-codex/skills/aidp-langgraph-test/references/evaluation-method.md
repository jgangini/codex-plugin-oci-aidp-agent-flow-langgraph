# Layered evaluation for AIDP LangGraph agents

Original adaptation guidance, initially researched on 2026-11-01. It applies to
new and existing AIDP LangGraph agents. Examples describe failure classes, not
project facts or additional acceptance requirements. The project owns its scope
and gates; choose checks from its capabilities rather than adopting every example.

Contents: experiment loop; layer selection; model evaluation; regression examples;
AIDP execution boundaries; closure and sources.

## Select the relevant capabilities

Start from the user's intended outcome, inputs, outputs, tools, state and allowed
effects. Use the simplest graph that fulfills those requirements. This guide
does not require a planner, supervisor, multiple agents, MCP, RAG, SQL tables,
long-term memory, write access or a particular number of Python files.

| Actual capability | Relevant evaluation focus |
| --- | --- |
| Classification, extraction or routing | Task fidelity, label/schema correctness, ambiguity handling and the branch actually taken. |
| Conversation or assistance | Useful answers, clarification only when material, session continuity and appropriate scope. |
| Search, research or RAG | Query/retrieval quality, coverage, provenance, supported claims and useful partial outcomes. Use retrieval handoff checks only where those stages exist. |
| Tools or delegated work | Argument/schema contracts, selection, returned errors, result consumption and bounded execution; MCP is one transport, not a required architecture. |
| Transactional actions | Authority at effect time, confirmation where required, idempotency, durable outcomes and recovery of uncertain effects. |
| Stateful or scheduled workflows | Checkpoint/resume behavior, ownership, timing, isolation and duplicate prevention for the capabilities actually implemented. |

Combine rows when the agent needs them. For a new agent, first establish one useful
vertical path from request to verified outcome, then expand the agreed acceptance
matrix. For an existing agent, preserve working behavior and diagnose the earliest
demonstrated defect. Neither approach permits publishing before its required TEST
acceptance. Example test roles are a selection aid, not a mandate to build unused
components, add approval steps or reduce the user's product scope.

## 1. Make each iteration answer a question

Start from a trace or failing input and identify the earliest demonstrated defect:
runtime/transport, tool contract, retrieval, model decision, state transition,
persistence or presentation. Separate observed facts from hypotheses. An irrelevant
search result is not automatically a prompt defect; a missing receipt is not a
reason to make the model report success.

For one coherent iteration:

1. Retain the failure and state what change should improve its observable outcome.
2. Identify the responsible boundary, input preconditions and expected behavior.
3. Select the smallest test that can distinguish the hypothesis from an alternative.
4. Capture the baseline; freeze applicable inputs and version the proposed change.
5. Apply the correction and test the reproduction plus relevant counterexamples.
6. Compare results under equivalent conditions; expand when the smaller test passes
   or proves that the defect belongs to a wider boundary.
7. At candidate closure, run required integration/architecture/package checks, then
   the affected native TEST acceptance. Preserve the served revision in evidence.
8. Update the project's existing checklist with the exact scope and remaining gate.

One hypothesis may require changes to several callers and tests. This is not a
one-line-change rule. Avoid simultaneously changing the model, source provider,
prompt and graph structure unless they are one necessary contract change; otherwise
the cause of an improvement or regression becomes unclear.

Use existing pytest/CLI helpers first. Add a reusable node-evaluation harness only
when the current runner cannot expose the needed boundary and repeated experiments
justify it. Do not build another orchestration platform to perform a small fix.

### Working mode and evaluator readiness

Choose the current mode in the existing checklist before running cases:

| Mode | Freeze | Completion and next action |
| --- | --- | --- |
| Measurement | Candidate, dataset, rubric, model/configuration and declared execution controls | Report the sampled outcomes and missing cases. Do not mix later candidates into the same score. A user-requested broad measurement may continue despite known functional failures, within its authorized admission rules. |
| Focused correction | Reproduction, expected behavior, comparison controls and captured inputs where relevant | Test one causal hypothesis, a useful positive, a nearby counterexample and a transfer case when generalization matters. Then check the affected native integration. These roles may overlap; do not mechanically run four suites for every change. |

A transition drains/reconciles in-flight operations, preserves the previous run
as partial if incomplete, and starts a separately identified comparison. It does
not reset the campaign, replace failed results or consume the remaining benchmark
questions for tuning. Resume a paused benchmark only with its frozen candidate;
a new candidate needs its own measurement identity. Honor current user steering
without adding an approval ceremony to an already authorized correction.

Before claiming a semantic success rate:

- Preserve the original user question as the authority. Compare derived briefs,
  search queries and judge inputs for added restrictions, lost entities, geography,
  time windows and requested relationships. Material ambiguity calls for a useful
  clarification; silently inventing a narrower task does not resolve it.
- Review the expected outcome on the small diagnostic set. Separate complete,
  useful partial, appropriate clarification, safe but unresolved, functional fail,
  technical fail and untested. A safety control can pass while usefulness fails.
- Calibrate semantic judges against reviewed positive and negative examples;
  inspect disagreements and preserve original verdict plus adjudication. Do not
  feed expected answers to generation or weaken the rubric to accept a candidate.
- Define the denominator and missing labels. Unreviewed answerability remains
  unknown; a failed capture does not prove the question impossible. Do not report
  "accuracy on answerable questions" without a reviewed answerability basis.
- A transfer case seen during tuning is no longer a blind holdout. Keep its ID
  and history; reserve a separate unseen set for subsequent generalization claims.

### Trace retrieval handoffs before another full run

Inspect the actual captured payload at each relevant handoff, rather than only
the final answer. Record the earliest demonstrated loss and its consumer:

| Boundary | Discriminating check |
| --- | --- |
| Request to query | Did the tool arguments retain entity/brand, market, requested relation and period? Is an alias or homonym unresolved? A correct planning paragraph does not prove the emitted query is correct. |
| Query to search results | Did the supported provider operation return relevant candidates? Separate tool failure, valid empty results and wrong-domain results. |
| Results to selected pages | Can the selector admit a promising page for reading without already demanding proof of the final claim in its snippet? Preserve rejection of unrelated candidates. |
| Selected URL to body | Did the reader retrieve the requested content rather than a title, navigation, recommendations, login or an inaccessible PDF? Inspect redirects and extraction; do not disable origin controls merely to obtain HTTP 200. |
| Body to evidence | Are source, entity, dates and relation preserved through truncation, filtering and deduplication? Discovery metadata and actual read content have different evidential scope. |
| Evidence to answer | Does assessment/draft repair receive the evidence, offending claim and feedback it must use? Check the final user-facing result, not only the internal decision. |

Use existing captured results for downstream diagnosis, with secrets removed and
original provenance retained. If fixed inputs pass but live integration fails,
compare live inputs before retuning the same node. A bounded real connector probe
is appropriate when the hypothesis concerns acquisition; fresh web results are
not an identical-input causal experiment. Evaluate useful integrated outcomes
separately even when a component's fixed-input score improves.

### Continue with an informative next step

Classify the failure before selecting the intervention. Exhausted recorded model
responses, missing fixtures, broken case selectors and runner setup failures are
test-preparation failures until evidence shows otherwise. Keep their failed
receipts, repair the harness/input and rerun offline; do not tune the agent's
prompt against an answer it never produced. A fixture response count is not a
provider call count. Report simulated calls, observed external calls, reserved
calls and unknown usage separately using the evidence available. Do not bypass
admission controls merely because the runner's generic recommendation is wrong.

After a failed candidate, record what the trial ruled out and choose the next
smallest test at the demonstrated boundary. Repeated runs that change no input,
hypothesis or diagnostic information need a stated stochastic-reliability reason;
otherwise inspect missing context, adapter behavior or the evaluator. Do not add
agents, raise reasoning effort, split large files or relax evidence/security
requirements merely because a run was slow. Use trace-supported intervention.

Maintain one active correction per shared candidate to preserve attribution;
independent work may proceed if it does not mutate the same evaluation controls.
Do not stop an authorized development task merely after producing a diagnostic
report or after a fixed number of failed hypotheses. Continue useful corrections
within scope, and expose an actual external blocker when one prevents progress.
Native-only defects may require native tests first; local-first is not a ban on
testing the platform where the failure exists.

## 2. Select layers by the defect

### Deterministic rules

Use local fixtures for payload parsing, source identity, dates, units, authorization,
budget reservation, citations and persistence invariants. Reproduce the real failure
shape, including mixed valid data and error envelopes. Test the emitted standalone
entry when packaging or imports change. Synthetic model outputs are appropriate
for routing and validator assertions; label that scope explicitly.

### Tool and retrieval checks

Before an expensive model loop, verify that the selected tool can perform the
requested operation. A search, a page reader, an account scraper and a numerical
series API have different contracts. Inspect admitted queries and returned data:
entity, geography, language, period, channel, unit and content availability.

Country/language/date filters are useful only when the actual provider supports
them; they do not guarantee relevance or factual publication dates. Grade retrieval
separately from the answer. Preserve search titles/snippets as attributed discovery
metadata; do not promote them into claims from an article that was never read.
Content truncation, redirects, empty pages and failed reads remain visible.

Reuse recorded tool output for downstream prompt experiments. A changed retrieval
contract may need a new bounded live probe within the existing authorization and
budget; repeating every capture for a wording change usually adds little evidence.

### Model nodes with fixed inputs

For the criterion-to-prompt contract and a bounded comparison, follow
[prompt diagnosis](../../aidp-agent-flow-langgraph/references/prompt-diagnosis.md).
Inspect assembled context and the consumer of each decision before attributing a
failure to wording; preserve useful positive behavior while repairing the failure.

Use the configured OCI model/adapter and fixed input evidence when testing semantic
behavior. Keep reference answers and expected labels out of the generation input.
Record prompt, model settings, schema, policy and evidence revisions. Calling a
model over recorded evidence is an evaluation, not a new capture or research run.
Do not insert those fixtures as real observations or count them as business demand.

| Responsibility | Evaluate |
| --- | --- |
| Understand | Preserve entity, objective, period and requested source; ask only material missing information. |
| Plan | Choose a supported operation that addresses a specific gap; avoid cosmetic searches without expected benefit. |
| Assess | Preserve support, contradiction, uncertainty and source independence, including documents in different batches. |
| Draft | Answer the question from admitted content; distinguish fact, inference and unknown; cite the actual supporting evidence. |
| Opportunities/confirmation | Respect eligibility, useful contribution, rejection, proposal revision and scope; a model response grants no authority. |

Grade schema/IDs/arithmetic with code. Review factual support against the supplied
source; a correct URL alone does not ground a claim. An LLM judge can assist with
semantic scoring, but calibrate it against reviewed examples and inspect disputes.
Do not let an unchecked judge define truth or repeatedly edit the rubric to pass.

### Partial graph and recovery

Define the starting state and required branch before invocation. Verify visited
nodes, state deltas, stop reason, model/tool calls and allowed external effects.
A test that clarifies before preparing a run has not tested clarification after
preparation, even if its final text looks correct.

Where supported, individual graph nodes and checkpoint-based partial execution
can isolate behavior. Direct node invocation bypasses the checkpointer. Use a fresh
test checkpoint for independent cases; deliberately preserve it for resume cases.
Never seed or edit a live managed checkpoint to skip authorization or a paid-start
boundary. A disposable in-memory test cannot certify Oracle-memory persistence.

Use a controllable clock or recorded adapter for local expiry/renewal hypotheses
when the design supports it, then validate the affected native boundary. Record
which temporal branch actually executed. Reading an already sealed receipt is
not a lost-acknowledgement recovery test; an expired source excluded from context
does not exercise source reobservation. Assert the intended branch, effect and
durable outcome before granting that recovery criterion.

For interruption/retry tests, inspect durable intents, receipts and final records,
not just the assistant's assertion. A timeout after a possible paid start requires
reconciliation of that identity before another start. Distinguish revocation of
new-capture permission from loss of access to historical data; apply the actual
project policy to each.

For a routing/closure change or repeated integrated failure, use the
[routing review](../../aidp-agent-flow-langgraph/references/routing-review.md)
for branch contracts, cross-batch gaps, factual draft repair and delivery boundaries.
Keep that diagnosis in the same checklist and choose only affected cases.

Use [boundary tests](../../aidp-agent-flow-langgraph/references/boundary-tests.md)
when the failure occurs between phases or adapters. Select the relevant clock,
effect, cancellation, message-completion, alternate-input or phase-coherence
case. Assert the real owner/adapter and durable outcome; a local helper's pass
does not cover a native callback that omits that helper. Preserve positive
controls and useful partial answers rather than defining all uncertainty as
failure.

### Native TEST and final client

Native acceptance proves the integration that isolated tests cannot: installed
runtime, actual model, tool authentication, managed memory and durable readback.
Verify the served source/configuration revision rather than relying on ACTIVE or
successful upload. Read outputs and the relevant trace/error evidence.

Close the full candidate against the agreed matrix after smaller experiments are
informative. Avoid rerunning the entire corpus after each prompt adjustment; retain
the required complete acceptance and repository checks at candidate/release gates.
Client rendering, A2UI, streaming presentation and shared access need their own
actual-client checks after the required TEST acceptance and authorized publication.
Schema-valid visualization output does not prove the client rendered it.

## 3. Curate examples that generalize

Start with a small reviewed set covering the affected capability, then expand from
observed failures. Include a valid positive case, the reproduction and meaningful
nearby counterexamples. Keep some questions/entities/phrasings held out from prompt
tuning. Freeze dataset revisions when comparing candidates; extend the dataset
without erasing the original failed result.

An illustrative project may start with roughly 5-10 examples for a critical
component; this is a recommendation, not a universal minimum or a claim of coverage.
Choose sample size and repeated trials according to variability, consequence and
cost. Keep repetitions explicit; a lucky pass is weak evidence of reliability.
Do not repeat paid effects merely to collect model trials.

| Observed failure class | Useful contrasting examples |
| --- | --- |
| Retrieval loses the intended entity/market | Exact entity vs homonym; relevant local source vs irrelevant result; filter supported vs unavailable. |
| URL or snippet treated as read content | Full body supports claim; title is only metadata; body truncated before the claim; conflicting body. |
| Dates conflated | Capture today with an old data year; publication unknown; current query window distinct from historical comparison. |
| Cross-batch contradiction missed | Same period/unit with conflicting values; different years that are not contradictory; affiliated republications. |
| Clarification tests the wrong branch | Missing information before preparation; prepared empty run; run with effects that cannot use that pause. |
| Partial/empty result overclaimed | Failed read vs valid empty response; limited traversal vs no global dependencies; proper limitation vs abandoned investigation. |
| Static reference called execution | Code mentions an asset; a task actually ran; execution outcome absent or stale. |
| Quality inferred from descriptions | Measured current quality; absent measurement; incomplete, stale or mismatched measurement. |
| Memory or scope mistaken | Same native session; new-session behavior under configured policy; two authorized users with separate histories. |

For a central-metadata agent, users may intentionally share the authorized metadata
view while keeping conversations separate. Do not impose per-asset delegation if
the approved design uses a central technical identity.

## 4. Measure what the experiment establishes

### Close capabilities rather than accumulating trials

Use the existing acceptance checklist as the control surface. For the current
case, record its capability, initial state, expected outcome, current stage,
evidence/revision and next unmet criterion. Keep local assertions, real-model
semantics, native integration and client acceptance as separate conclusions.
An isolated positive control does not close open discovery; an expected source
failure does not demonstrate successful research. Verify environment outcomes
(stored records, receipts, readback) as well as the answer and visited path.

Start a correction with the reproduced failure and a positive/nearby control.
Evaluate downstream reasoning on retained content instead of recapturing it.
If no new information emerges from repeated trials, revise the hypothesis or
choose a smaller discriminating test. Do not change acceptance criteria to fit
the answer. Fix blockers of the current closure; record independent enhancements
without opening them automatically. Keep accepted checks unless the changed
boundary or new evidence requires reopening them. Required candidate-wide and
release checks remain at their documented gates.

For evidence with expiry, test the ordering of slow I/O and short-lived reads
with the project's controllable clock when available. Check validity at the
boundary that uses it, including after I/O. A frozen semantic evaluation alone
does not certify this timing. Preserve consent, revision and freshness rules;
neither renewing permissions nor extending TTL is a default test fix.

The runner records complete-case/configuration/experiment fingerprints and safe
failure progress; use them to avoid comparing trials whose rubric, fixtures or
selection changed unnoticed. A timed-out process cannot promise complete progress
or terminated external work. SDK compatibility of an effort setting is also
different from its model's quality; see [model selection](../../aidp-agent-flow-langgraph/references/model-selection.md).

Record the case ID, hypothesis/layer, initial state, input hashes and provenance,
source/prompt/model/policy versions, expected assertions, observed branch/outcome,
evidence references, evaluator version, repetitions, tool/model calls and costs.
Missing cost remains unknown. Record cached outputs so they are not described as
new model execution or fresh retrieval.

Separate deterministic correctness, retrieval relevance/coverage, factual grounding,
answer usefulness, trajectory and recovery. Label each assertion accepted, failed,
blocked or untested, with scope. A partial report may truthfully satisfy a bounded
case while the positive research capability remains open. Test that capability
too; repeated abstention alone is not a useful research product.

Accuracy percentages need reviewed labels and a stated denominator. Unlabeled
question corpora are inputs, not ground truth. Keep critical invariant failures
visible rather than hiding them in an average score. Evaluate time and cost per
phase and time to useful diagnostic feedback; do not demand an arbitrary number
of seconds or trade away evidence checks to improve the clock.

Reuse an accepted result when its tested revision and conditions are unchanged.
Reopen it for an affected change, a new counterexample or unresolved concern, not
merely because another iteration began. Keep one requirements source and one
validation workflow; add evidence to the existing project record.

## 5. AIDP-specific execution boundaries

Run now uses workspace files; Playground/deployment use a packaged entry folder.
Verify dependencies, included files and served revision on the actual instance.
Upload, compute association, TEST refresh and production deployment are distinct.
Compare observed local/native versions with Oracle's documented support before
using current upstream APIs. In particular, Oracle documents LangGraph 1.0.1;
node-level `timeout=` and `error_handler=` require 1.2 or newer. A matching local
profile is dependency evidence, not native TEST acceptance or Oracle certification.
Never label an unobserved production runtime compatible by assuming it equals TEST.
Do not invent a CLI refresh selector when only the UI contract is verified.
Prefer supported CLI/API operations for repeatable tests and Browser for required
visual acceptance under the project's capture policy.

Preserve platform-managed dependencies, setup/invoke lifecycle, model parameters,
secret references, user/session scope and managed checkpointer. The conceptual
method does not require LangSmith cloud, a new database, automatic tracing,
additional agents or a framework upgrade. Live operations remain governed by the
project and the applicable AIDP development skill.

## 6. Sources and adaptation

Method revision verified against the primary sources below on 2026-11-04.
Working modes, handoff diagnostics and reporting rules are this plugin's
engineering adaptation, not claims that the vendors implement these controls.
LangGraph supports isolated-node and partial-graph tests; LangSmith distinguishes
single-step, trajectory and final-response evaluation. Anthropic recommends
reviewing tasks/graders and environment outcomes, including judge disagreements.
No hosted evaluator or additional runtime dependency is required here.


- [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts):
  versioned offline examples and experiments, with expected outputs kept outside
  application inputs. These concepts do not require adopting its hosted service.
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents):
  distinguish tasks, trials, traces and actual environment outcomes; combine
  deterministic checks with calibrated semantic review. No external grader or
  tracing destination is installed by this plugin.

Primary documentation consulted on 2026-11-01. Summaries and the layer-selection
policy above are original adaptation guidance, not a vendor certification or a
requirement to install the tools used in tutorials.

- [LangGraph tests](https://docs.langchain.com/oss/python/langgraph/test): individual nodes and partial execution, with checkpoint limitations.
- [LangChain complex-agent evaluation](https://docs.langchain.com/langsmith/evaluate-complex-agent): final answer, trajectory and single-step evaluation.
- [LangChain RAG evaluation](https://docs.langchain.com/langsmith/evaluate-rag-tutorial): retrieval quality and answer quality are different targets.
- [LangChain evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts): curated/versioned examples, held-out splits, grading and experiments.
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents): task/trial/outcome distinctions and repeated evaluation.
- [Oracle Agent Creation / Testing](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html): workspace vs packaged execution, TEST sessions and traces.
