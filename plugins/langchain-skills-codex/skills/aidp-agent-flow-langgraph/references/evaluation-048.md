# Executable preparation and evidence in 0.4.8

Apply this cycle to new or existing agents, single-file or modular. Do not add
MCP, retrieval, a supervisor or persistence unless the task requires them. Keep
one existing acceptance checklist and distinguish component correctness from
useful integrated behavior. A source/model/environment change is an intervention;
do not repair against the held-out measurement corpus after every question.

## Prepare before spending executions

Use the campaign's pinned executable in every example below (shown as
`aidp-agent-flow` for readability):

```text
aidp-agent-flow --project <project> --json test --cases tests/cases.json --case focused --plan
aidp-agent-flow --project <project> --json test --cases tests/cases.json --case focused --hypothesis "The selected evidence survives normalization"
aidp-agent-flow --project <project> --json experiment diagnose --receipt .aidp-local/runs/<receipt>.json
```

All selected case contracts are validated before reserving or running the first
case. `model_responses` must be a bounded list of strings, never a plain string
or chat-message object. Recorded MCP/retrieval/table records use the existing
service contract, including intentionally recorded failures. Exhausting model
fixtures remains a fixture defect even if project code catches the exception.

`--plan` checks cases, package, project interpreter and current campaign capacity.
It creates no reservation, worker or agent invocation. It predicts a batch using
full configured call/cost ceilings and assumes earlier cases terminate; the next
admission is still checked under the campaign lock. A forecast is advisory, not a
reservation, billing verification, successful factory import, provider health
check or native acceptance. The execution hypothesis/evidence are checked at
admission. It never expands limits or clears unknown consumption.

## Diagnose before modifying prompts

Use `failure_code`, `failure_category`, `failure_stage`, attempted `model_calls`
and `completed_model_responses` to choose the next discriminating check:

| Failure | Next work |
| --- | --- |
| Fixture/preparation | Repair recorded data, factory or environment offline |
| Provider invocation | Inspect dated provider evidence; do not infer quota, credit or prompt failure from 429 alone |
| Tool/model contract | Check adapter arguments, completion and recorded expectations |
| Execution | Inspect the failed boundary and route |
| Assertion | Compare the earliest behavioral divergence against the original requirement |
| Timeout/worker protocol | Reconcile uncertain execution before a paid retry |

These are mechanical diagnostics, not a semantic root-cause oracle. A caught
provider failure with a valid fallback can still be an intended outcome; it needs
the project's explicit assertions. A transport success or token count cannot
replace factual or task-level acceptance. Do not retry an unchanged hypothesis
merely because the last attempt failed.

## Partial paths and state boundaries

Use `node`, or `start_after`/`stop_before`, to isolate a failure. The factory must
use the supplied checkpointer for partial paths. The receipt distinguishes
`requested_stop_before`, `terminal_before_requested`, `dynamic_interrupt`,
`other_frontier`, `completed`, `node_completed` and `error`. An expected answer
already present in the seeded state does not prove a path was executed. An
unexpected terminal branch or interrupt cannot pass a requested stop boundary.

Set `trace_boundaries: true` on a reviewed case to collect bounded hashes and
sizes for input, completed node updates and output. The optional trace stores no
values; hashes are private evidence, not anonymization. Fields larger than the
trace bounds or unsupported objects are explicitly omitted. Traces cover graph
updates, not every internal tool/model handoff. If evidence is lost inside one
node, add a focused project assertion at that consumer. Do not split working
nodes simply to populate a dashboard.

Intervals are wall time between stream events, not per-node compute time or LLM
latency, especially with concurrency. Use adapter telemetry to attribute costs
or latency when needed. `clock_at` injects a timezone-aware fixed clock through
`runtime["clock"]` for business expiry tests only. It does not replace provider,
authorization, campaign or timeout clocks.

## Versioned evidence and scope

Receipts bind executable Python files, declared environment files and observed
versions of supported local packages. This is deliberately not a fingerprint of
every transitive dependency, private external dataset or hosted runtime. Record
the case's evidence and verify native compatibility separately. An unavailable
environment observation blocks local admission and cannot earn current local acceptance.
Native invocation receipts label
this identity as the local test harness, not the AIDP runtime.

Old receipts remain historical. Engine adoption preserves their bytes, budgets
and unresolved reservations; it does not turn them into fresh acceptance. The
native duplicate protection is unchanged: a completed case on the same native
deployment is not automatically invoked again after engine adoption. Plan a new
explicit reviewed case identity or candidate revision for required revalidation;
never overwrite or relabel the old receipt, and never evade uncertain operations.

Use [version 2 scope decisions](node-progress.md) for authorized exclusions.
Reports expose active, excluded and inventoried totals. Existing criterion IDs
are retained across version 2 revisions; exclusion needs a reason and authority
reference. Excluded criteria do not receive PASS, appear in history and block
publication under the current conservative policy. Redefining the releasable
product needs an explicit reviewed release contract, not a denominator trick.

## Existing agents and clean reproduction

Use `project adopt` only to add the local contract; inventory remote identity,
package paths and shared resources before any authorized remote edit. Preserve
behavior, prompts, credentials and data. Replay one supported path before a
refactor. Then test the failed boundary, a counterexample, its consumer and the
affected integration, followed by frozen measurement and AIDP TEST.

Before native promotion, check the package from a clean checkout or directory
using locked dependencies. Separate tracked public fixtures from private imported
evidence and document how the latter is supplied. Missing private data must be an
explicit readiness failure, not a silent empty substitute. The plugin inspects
packaging and declared paths; it does not certify every external resource or
automatically reconstruct an existing agent's business logic.

## Basis and limits

- [LangGraph testing](https://docs.langchain.com/oss/python/langgraph/test): isolated graphs/checkpointers, node tests and partial execution; node invocation bypasses checkpoints.
- [Agent evaluations](https://www.anthropic.com/research/demystifying-evals-for-ai-agents): distinguish tasks, trials, graders, traces and actual outcomes.
- [Oracle agent creation](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html): native package/entry structure and supported runtime. The local regression environment uses LangGraph 1.0.1; this is not Oracle certification.

The CLI fields and admission forecast above are this plugin's engineering
contracts, not APIs specified by those vendors. Offline regression passing does
not certify model quality, live MCP services, AIDP TEST or production parity.
