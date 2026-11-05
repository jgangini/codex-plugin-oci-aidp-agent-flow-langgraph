# AIDP Agent Flow LangGraph

Local Codex plugin **0.4.8** with CLI/evaluator **0.4.8**, for developing Oracle AIDP LangGraph
agents through a reproducible local → native TEST → publication → Registry
cycle. The technical identity remains `langchain-skills-codex@local`.
This is an independent adaptation, not an official Oracle or LangChain plugin.

## Skills and installation

The first skills remain **AIDP Agent Bootstrap → AIDP Agent Flow LangGraph →
AIDP Agent Flow Test**, followed by Credential Store and five pinned upstream
framework skills. Nine entrypoints are maintained. Test and the five upstream
skills retain explicit invocation; bootstrap, development and credentials retain
normal discovery. Skill discovery grants no additional authorization.

Install the optional CLI in an explicitly versioned environment as described in
[command setup](skills/aidp-agent-flow-langgraph/references/local-development.md#command-setup-and-scope).
Check its absolute executable with `--version` from another directory. Plugin installation alone runs no bootstrap, hooks,
cloud operations or tracing destination. CLI dependencies include the official
OCI SDK and its explicitly declared HTTP transport. Project uv dependencies are
separate from AIDP-managed runtime libraries.

| Need | Entry point |
| --- | --- |
| New/existing local environment | [Bootstrap](skills/aidp-agent-bootstrap/SKILL.md) |
| Agent implementation and iteration | [Agent Flow LangGraph](skills/aidp-agent-flow-langgraph/SKILL.md) |
| Node/path/behavior evaluation | [Agent Flow Test](skills/aidp-langgraph-test/SKILL.md) |
| Node validation table and percentages | [Node progress](skills/aidp-agent-flow-langgraph/references/node-progress.md) |
| Bounded attempts, hypotheses and accumulated reservations | [Experiment campaigns](skills/aidp-agent-flow-langgraph/references/campaigns.md) |
| Regional OCI model inventory and selection | [Model selection](skills/aidp-agent-flow-langgraph/references/model-selection.md) |
| Runtime/service-account/token setup | [Credential Store](skills/aidp-runtime-credentials/SKILL.md) |
| Package, native TEST, sessions, publication and invocation | [Native CLI](skills/aidp-agent-flow-langgraph/references/native-cli.md) |
| Inspect/register/adopt an existing native agent | [Registry](skills/aidp-agent-flow-langgraph/references/registry.md) |

## Executable evaluation update 0.4.8

The engine now validates model/service fixtures before admission, verifies partial
execution frontiers, classifies failures, previews batch capacity with `test --plan`,
and binds receipts to executable and environment fingerprints. Optional bounded
hash traces and an injected test clock help reproduce data-loss and expiry defects.
Version 2 progress plans preserve scope history, retained criterion identities and
separate active/excluded denominators. Exclusion is never a PASS or a publication waiver.

See [0.4.8 workflow and adoption](skills/aidp-agent-flow-langgraph/references/evaluation-048.md).
No cloud validation or Oracle certification is inferred from local regressions.
Use a versioned CLI environment during active campaigns; installing new skills
must not replace their selected executable. Existing receipts remain historical;
engine adoption does not relabel them or reset reservations. Native receipt identity
also records the local harness environment, not observed native dependency parity.

## Previous development method update 0.4.7

That release changed the development and evaluation instructions; the executable
CLI/evaluator stayed at **0.4.6**, byte-for-byte, in that release. Plugin version and evaluator version
are separate identities. Installing these guides does not stale receipts, adopt
a new engine, change a campaign policy or grant publication approval.

The [evaluation method](skills/aidp-langgraph-test/references/evaluation-method.md)
now separates frozen measurement from focused correction, checks rubric readiness
against the original request, diagnoses retrieval at each handoff and requires
separate component and integrated outcomes. The
[progress guidance](skills/aidp-agent-flow-langgraph/references/node-progress.md#report-revision-transitions-without-restarting-development)
explains stale versus failed evidence and targeted revalidation without granting
automatic carry-forward. The [campaign guide](skills/aidp-agent-flow-langgraph/references/campaigns.md#keep-the-executor-stable-during-an-experiment)
covers project-pinned execution, safe pauses and quota forecasting.

These are instructions Codex applies using existing commands and project records,
not a new optimizer, scheduler, automatic pinning command or report schema.
No framework, Oracle runtime or agent model is upgraded by this release.

## Evidence and campaign update 0.4.6

Guide revision `0.4.6+guide.2` adds [campaign authority renewal](skills/aidp-agent-flow-langgraph/references/campaigns.md#campaign-authority-and-renewal):
Codex reuses existing authorization and manages explicitly authorized operational
renewals without repeated questions. Campaign authority, action-specific consent,
credentials and budgets retain their distinct limits. This is execution guidance,
not a new CLI renewal service; projects need a verified renewal contract.
For those guide-only revisions, CLI/evaluator code and identity stayed at **0.4.6**; no receipts were relabeled.

Guide revision `0.4.6+guide.1` explicitly assigns Codex the autonomous diagnosis →
correction → verification loop. It must apply supported fixes and continue useful
iteration within existing authorization, not stop at recommendations or ask for
approval after every failure. CLI/evaluator code, dependencies and identity remain
unchanged; this documentation-only revision does not stale evaluator-bound receipts.

Adds [prompt/context diagnosis](skills/aidp-agent-flow-langgraph/references/prompt-diagnosis.md),
read-only `experiment diagnose` and controlled `experiment compare` commands.
They reuse existing cases and receipts, report assertion gains/regressions and
changed controls, and never infer semantic acceptance from a successful transport.

The [progress table](skills/aidp-agent-flow-langgraph/references/node-progress.md)
now includes every criterion, optional gate/group labels, case mapping, evidence,
historical successes and precise freshness/configuration reasons. Integrated-agent
criteria have a separate denominator; G1/G2-style labels are not invented nodes.

[Campaign adoption](skills/aidp-agent-flow-langgraph/references/campaigns.md#adopt-an-updated-plugin-during-a-campaign)
records a verified current engine/policy/ledger snapshot without resetting limits
or history. Terminal usage uncertainty blocks paid work/publication while allowing
zero-call fixtures after active owners finish. Unknown or malformed states fail
closed. Project supplements still need their own compatibility checks.

## Runtime and boundary update 0.4.5

Adds [evidence-based routing review](skills/aidp-agent-flow-langgraph/references/routing-review.md)
for intent/clarification, source selection, global gaps, factual draft repair,
continuation and delivery. It is integrated into development and TEST guidance.
Adds [boundary tests](skills/aidp-agent-flow-langgraph/references/boundary-tests.md)
for effect-time authority, cancellation, adapter parity, equivalent inputs and
assessment/answer coherence. These are targeted project tests, not a universal
semantic detector. The new `runtime check` compares actual local dependencies
with Oracle's documented LangGraph 1.0.1 profile and optional candidate-bound
TEST/PROD observations. Read [runtime compatibility](skills/aidp-agent-flow-langgraph/references/runtime-compatibility.md)
for gates, evidence limits and upgrade behavior. No Oracle certification is claimed.

The local and generated native final-text adapters now share completion checks
and cancellation drainage; a generated native invocation cannot silently accept
a caught incomplete completion. Local workers close their owned SDK client.
Recorded zero-call fixtures can continue after terminal uncertain paid attempts
or exhausted paid quotas while retaining all reservations; active owners and
attempt/repetition bounds still block. Paid local/native calls retain their gates.

This release changes the CLI/evaluator. Previous receipts remain preserved, but
version-bound acceptance becomes stale under the new evaluator; revalidate the
applicable criteria before claiming current acceptance. No ledger, local patch,
business source, environment or hosted dependency is automatically migrated.

## Local iteration

`project init` creates a modular uv starter; `--no-sync` prepares files only.
`project adopt` adds configuration without rewriting business logic. Both
single-file and modular agents are supported. `doctor` checks offline readiness.
`test` invokes the same portable graph factory in the project's environment,
with fixture models or explicitly selected real OCI model cases. Individual
nodes and partial paths can be tested without refreshing AIDP.

Recorded MCP/RAG/table results isolate reasoning from repeated live calls.
They do not establish real-connector correctness. A factory must honor the
injected external-effects boundary; the worker is not an OS sandbox. Review
actual answers and evidence: JSON shape, a completed request or ACTIVE compute
are insufficient quality criteria. Existing project adapters, signers,
guardrails, memory and budget/idempotency ledgers remain authoritative.

Focused cases are validated before execution. Unexpected replay calls cannot
pass by being caught, missing paths are not null, and JSON assertion types remain
distinct. Private artifacts retain full-case/configuration fingerprints, redacted
case snapshots and safe completed-node/call diagnostics on errors. These records
support the existing acceptance checklist; they do not automatically accept native
TEST or replace semantic review. The generic local model adapter now transmits an
optional SDK-validated `reasoning_effort`; unsupported settings fail before calls.

`progress` maintains a table for every declared graph node, including untested
nodes. Its percentages use explicit weighted acceptance criteria, with local
evidence and reviewed native TEST acceptance in separate columns. New starters
include an example `node-progress.json`; existing projects install their own
reviewed map. Local tests refresh the table from revision-bound receipts; changed
or failed evidence reduces credit. This is validation coverage, not an automatic
estimate of business-project completion or development time.

All CLI test/invocation execution uses an explicit campaign policy and hypothesis.
New CLI projects start with a fixture-only policy; real/model-native attempts need
limits configured within existing authorization. Attempt admission reserves calls
and configured cost ceilings, bounds identical trials and blocks unresolved work.
Unknown cost stays unknown; the ledger is not a provider billing meter. SDK model
responses must be complete, and evidence binds to the evaluator version.

`models list` reads the actual regional inventory, capabilities, lifecycle and
retirement information without choosing a model. Availability is not a quality
ranking. Compare suitable candidates against the same reviewed cases before
changing an existing model; latency is one measured consequence, not the goal.

## Native workflow

The CLI implements scoped package sync with exact readback, CODE-agent creation
or explicit identity verification, first TEST initialization, TEST refresh,
status/reconciliation, TEST sessions, bounded gateway invocation and explicit
publication. Mutating lifecycle/invocation commands plan by default and need
`--apply`. A native command does not silently provision compute or tables.

These target-verified integrations deliberately distinguish public GA
`20260430/aiDataPlatforms` from legacy `20240831/dataLakes` TEST and Registry
surfaces. Unsupported targets stop with an explicit limitation. No Browser step
is required by the implemented acceptance path; client visual acceptance remains
separate. Use the official Oracle plugin for operations outside this package.

Write intents and stable retry identity are recorded before submission. Unknown
outcomes block another write. Async results require terminal operation status
and scoped resource readback. Initial deployment includes its name;
redeployment omits the create-only name. TEST refresh preserves production.
Publication requires the exact package's reconciled TEST receipt, current node
criteria and integrated agent acceptance in `node-progress.json`. The CLI blocks
missing/stale/failed acceptance, blockers and unresolved configured campaigns.
Native package evidence requires an exact reconciled deployment snapshot, including
a readback after invocation; an unknown association cannot gain TEST credit.

Registry inspection uses the canonical A2A `.well-known` card URL and preserves
its normalized interface. Registration is distinct from deploying an endpoint
or editing a card. It pins a separate Registry UUID, reviewed metadata and
payload before one POST, then verifies the returned version resource and ACTIVE
listing. Explicit adoption reuses a matching record instead of creating a
duplicate. Platform-managed AIDP authentication is retained; no OAuth setup or
permission grants are introduced. Registered ACTIVE is not a visual Agent Hub
chat acceptance result.
After ACTIVE readback, `registry hub-link` delivers the project's explicitly
configured Agent Hub portal URL. Recipients still need sign-in and agent access;
the command does not manufacture an agent-specific deep link or grant permissions.

Credential Store creates are similarly bounded and non-rotating. The runtime
layout is a five-pair SECRET_TOKEN, distinct from SERVICE_ACCOUNT. When GET
omits all values, a newly created ACTIVE resource is reported as pending native
verification rather than falsely claiming identity equality or creating it
again. Existing shared credentials are not silently adopted or overwritten.

## Project files

Keep `agent/` as the packaged source, `tests/` as reviewed cases and
`aidp-agent.toml` as nonsecret configuration. Generated runs, native receipts,
invocations, model inventory and Registry state stay under ignored
`.aidp-local/`. Protected OCI files/references stay under the project's existing
`.oci` convention and are excluded from Git and packages. Large Python files are
allowed; split responsibilities when it improves testing and ownership, not to
meet a line-count rule.

A live graph/task dashboard is a proposed subsequent feature. No localhost
server, animated UI or automatic live-node telemetry is installed by this
release. Its design prototype precedes implementation of real events.

## Evidence and limits

The maintenance suite covers real local LangGraph execution, SDK request types,
synthetic encrypted-key validation, package boundaries, guarded cloud intent,
TEST/PROD scope, Registry normalization and bounded SSE/error handling. Run:

```text
uv sync --dev --locked
uv run python -m unittest discover -s scripts/tests -q
```

An isolated synthetic support acceptance exercised real OCI inference, dedicated
Credential Store consumption, exact package upload, native TEST/session/invocation,
first TEST initialization entirely by API, initial publication, a changed policy
through local and native TEST while PROD retained its prior revision, corrected
redeployment and ACTIVE Registry registration/readback. This establishes the
bounded tested workflow, not every model, runtime, tool adapter or customer case.
No existing business-agent source or deployment was changed. Windows tests may
need the normal authorized filesystem execution context for protected temporary
files; do not weaken security assertions for sandbox-specific ACL failures.

Earlier global-tool releases recorded structural regression against the original
mostly-documentation baseline after adding executable modules. That historical
finding is not erased by publishing this repository. This public distribution
uses the copied 0.4.8 source as its packaging baseline; its gate measures changes
introduced here, not improvement over the earlier documentation-only plugin.
No custom Sentrux rules or Graphify graph are configured. See the repository's
Spanish development guide and release record for runnable checks and their scope.

## Provenance and maintained scope

Five upstream LangChain skills and their references remain unchanged at commit
`126c384d8552dcb476b226c244172186cc3f4328`; `upstream-files.json` records seven
original Markdown/reference hashes. MIT notices are retained in `LICENSE`.
Upstream: https://github.com/langchain-ai/langchain-skills.

The AIDP development guide was relocated from Migration Workbench's
`aidp-agent-development` and renamed `aidp-agent-flow-langgraph`. Its existing
references remain maintained. The migration plugin retains platform/migration
operations. The original AIDP skills and plugin reuse its existing icon and logo
unchanged, at the user's request. No business-project examples, source payloads,
cloud identities, private questions or live project status belong in this package.

Updating the plugin does not refresh instructions already loaded into another
chat. Use a fresh chat or explicitly load its updated skill. Updating these
skills does not upgrade libraries in native AIDP.
