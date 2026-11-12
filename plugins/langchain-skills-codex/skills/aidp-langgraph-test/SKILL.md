---
name: aidp-langgraph-test
description: "Plan, run and review layered tests for Oracle AIDP LangGraph agents. Use when tuning nodes or prompts, diagnosing tool/retrieval failures, testing partial paths and recovery, or closing native TEST acceptance before Agent Hub."
---

# AIDP Agent Flow Test

This is an original Codex adaptation guide, not an upstream LangChain skill.
It supplies an evaluation method alongside the plugin's local CLI runner.
Reuse an existing project harness when it already exposes the needed boundary;
read [the executable contract](../aidp-agent-flow-langgraph/references/local-development.md)
for the new runner. Use the project's existing requirements and acceptance checklist. A plugin-maintenance task does not authorize cloud tests.

For repeated-answer quality, first use [semantic quality and calibration](references/semantic-quality.md).
The executable quality commands evaluate frozen answers through the existing
campaign/model. Keep mechanical completion, semantic criteria, calibration and
native acceptance separate; there is no universal numeric similarity threshold.

## Choose the first useful test

Read [the evaluation method](references/evaluation-method.md) when designing
an experiment, revising a test plan or diagnosing a repeated failure. Select
the sections relevant to the change rather than running every layer by default.

For prompt changes, use [prompt diagnosis](../aidp-agent-flow-langgraph/references/prompt-diagnosis.md)
to inspect the assembled input and actual output consumer, freeze the comparison,
and select a reproduction, positive control and held-out check for the criterion.
Codex must execute that guide's autonomous correction loop during an authorized
development task: apply the supported fix and validate it, rather than returning
only a proposed change. A failed candidate does not itself end the task; preserve
its evidence and continue with the next informative hypothesis within current limits.

| Suspected failure | First useful surface |
| --- | --- |
| Parsing, dates, schema, authorization or budget rules | Focused deterministic regression with the failing payload. |
| Query, connector, retrieval or unreadable source | Bounded tool check with the actual supported contract and inspected results. |
| Model interpretation, planning, assessment or drafting | Real configured OCI model with fixed, versioned inputs and a semantic rubric. |
| Routing, clarification, memory, interruption or recovery | Partial graph with explicit preconditions, observed nodes and checkpoint/effect assertions. |
| Integrated candidate | Native TEST against the verified served revision and the affected acceptance cases. |
| Client rendering and shared access | Final client acceptance after the required TEST gates and authorized publication. |

Local synthetic models test graph mechanics; they do not establish real-model
reasoning. A valid JSON response, ACTIVE deployment or completed stream is not
an accepted research answer. Check the intended outcome and the path actually
executed.

For repeated routing, clarification, coverage or delivery failures, apply
[the routing review](../aidp-agent-flow-langgraph/references/routing-review.md)
to choose predicates and effects to assert. Reuse the partial-graph method below;
a valid final answer alone does not prove the intended branch or absence of effects.

When a node passes but integration fails, or a change crosses authorization,
model, persistence or cancellation boundaries, read
[boundary tests](../aidp-agent-flow-langgraph/references/boundary-tests.md).
It provides discriminating injections for the actual adapters; these project
regressions are not automatically run or certified by the plugin.

## Measurement or correction

Apply [the working modes and evaluator-readiness checks](references/evaluation-method.md#working-mode-and-evaluator-readiness)
before admitting a broad run. A benchmark measures one frozen candidate; a
correction targets one demonstrated cause. Record the mode and transition in the
existing checklist, not in a second plan. Honor an explicit full-corpus request;
do not quietly tune the agent within that measurement or restart it after a patch.

When a local gain fails to transfer, trace the real upstream input and downstream
consumer using [the retrieval handoff checks](references/evaluation-method.md#trace-retrieval-handoffs-before-another-full-run).
Do not treat a relevant snippet, HTTP 200, a safe abstention or a passed selector
as evidence that the user's research question was answered.

## Iteration rule

Start with one bounded hypothesis and a reproducible failure. Freeze relevant
inputs, define the pass criteria, make a coherent correction, and compare with
the baseline and nearby counterexamples. Expand to the affected integration
checks once the smaller experiment is informative. Run the repository's required
preflight/postflight and release checks at their prescribed boundaries; do not
replace them with this guide or repeat a passed suite without a new reason.

Keep accepted cases closed unless an affected change or new evidence justifies
reopening them. Record blocked and untested cases separately. Reuse the current
checklist instead of creating another project plan. Prioritize usefulness,
grounding, coverage and recovery; measure latency and cost without imposing
an arbitrary response-time target.

Track one current capability and its next acceptance criterion in that checklist.
Start with a positive control and the reproduced failure at the responsible
boundary. A reliable refusal or recovery does not replace the positive capability.
If repeated trials add no evidence, change the experiment rather than resending
the full flow. Separate necessary blockers from independent follow-up work.
At each closure, report the criterion met, evidence, remaining barrier and next
smallest check; a rising test count is not a progress measure.

Maintain [node validation progress](../aidp-agent-flow-langgraph/references/node-progress.md)
when developing or evaluating an agent. Reuse an existing `node-progress.json`,
or prepare its complete node inventory and criteria against the current checklist
before counting progress. The CLI rebuilds its JSON/Markdown table from receipts;
local passes do not grant TEST acceptance. Include never-tested nodes and report
stale evidence, regressions and blockers rather than estimating percentages in prose.

Use the existing [campaign policy and ledger](../aidp-agent-flow-langgraph/references/campaigns.md)
for CLI tests and native invocations. State a hypothesis, select the smallest
informative case and preserve its attempt/result. Repeated identical trials need
a declared rationale and remaining quota. Stop paid work at an unresolved attempt,
exhausted paid limit or new external authorization boundary; reconcile rather than
retry blindly. Zero-call recorded fixtures may continue after terminal uncertainty
under the campaign rules, preserving reservations and attempt/repetition bounds.
Do not request another spending extension merely to run those fixtures.
The CLI enforces these admission controls, not the truth of the semantic rubric.

Apply [campaign authority and renewal](../aidp-agent-flow-langgraph/references/campaigns.md#campaign-authority-and-renewal)
before interrupting TEST for an expiring operational declaration. Reuse authorized
renewals, verify their recorded scope and keep business-consent expiry tests
independent. A renewed campaign declaration does not make an expired action valid.

## Managed-runtime boundaries

- Preserve the installed LangGraph/LangChain/aidputils versions, Oracle lifecycle,
  configured model, secrets and managed memory. Verify capabilities before using
  a newer upstream API. This skill installs no dependencies or tracing service.
  Compare local and observed native versions before accepting compatibility;
  missing native evidence remains unknown. Oracle's documented LangGraph support
  is not a certification of an agent or of this plugin.
- Use [aidp-agent-flow-langgraph](../aidp-agent-flow-langgraph/SKILL.md)
  for the development lifecycle and live operations; use the installed official Oracle skills or the project's
  verified CLI/API contracts. Browser handles visual acceptance and operations
  without a verified automation contract, under the project's capture policy.
- Replay model evaluation from immutable evidence with external effects disabled.
  Do not mutate live checkpoints, publish evaluation drafts as research, or restart
  an uncertain paid operation. Recovery checks retain the real ledger and identity
  when that is the behavior under test.
- Preserve existing authorization and publication boundaries. TEST acceptance,
  production publication and Agent Hub/client acceptance are different results.
  Honor valid existing authorization; this guide adds no approval ceremony.

## Report the evidence

Use the existing case ID and record the hypothesis, tested layer, source/prompt/
model/input revisions, observed path and outcome, evidence references, tool/model
calls, known or unknown cost, verdict and next smallest check. State whether a
result is deterministic, model-only, native integration or visual acceptance.
Do not claim exhaustive coverage or a factual accuracy rate from unlabeled
questions. Model judges need a defined rubric and review; critical receipts,
identity, scope and numerical checks remain deterministic.

## Executable evidence in 0.4.8

Read [preparation, diagnosis and versioned evidence](../aidp-agent-flow-langgraph/references/evaluation-048.md) before a new corpus or engine adoption. Prefer the smallest discriminating node/path test, then its affected integration; preserve the frozen measurement set.
