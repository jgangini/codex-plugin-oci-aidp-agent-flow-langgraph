# Evidence-backed progress by node

The CLI maintains a node validation table, not an estimate of coding effort or a
claim of overall product completion. It does not run another test or contact OCI
to calculate progress. The existing project checklist remains the requirements
source; `node-progress.json` maps its criteria to test evidence.

## Establish the denominator once

Inventory every executable node, including nodes with no tests yet. Use actual
graph names; include subgraph nodes when the project's test adapter can identify
them. Never infer the complete inventory from a successful trace. Nodes without
criteria remain unplanned, with no numeric percentage. Unplanned observed nodes
must be reconciled before claiming scope coverage.

For new projects, `project init` includes a small example plan for `respond` and
creates the initial table. Replace its sample criteria with the real functional
rubric as the graph develops. For existing projects, prepare a reviewed JSON
definition in the project and install it without overwriting a maintained plan:

```text
aidp-agent-flow --project <project> --json progress init --definition tests/node-validation-definition.json
aidp-agent-flow --project <project> --json progress report
```

Example definition for one node (repeat the node entry for the actual inventory):

```json
{
  "version": 1,
  "requirements_ref": "docs/acceptance.md",
  "acceptance": [
    {
      "id": "integrated-research",
      "description": "The integrated TEST answer satisfies the research question, references and user isolation rubric.",
      "layer": "TEST",
      "case_id": "native-integrated-research",
      "weight": 1
    }
  ],
  "nodes": [
    {
      "id": "assess",
      "implementation": "declared",
      "criteria": [
        {
          "id": "contradiction-control",
          "description": "Detect incompatible observations for the same period and preserve both source IDs.",
          "gate": "G1",
          "group": "evidence-quality",
          "layer": "local",
          "case_id": "conflicting-evidence",
          "cases_file": "tests/reviewed-cases.json",
          "mode": "real",
          "scope": "node",
          "weight": 1
        },
        {
          "id": "native-contradiction",
          "description": "The native TEST response explains the contradiction with valid references and the correct user scope.",
          "layer": "TEST",
          "case_id": "native-conflicting-evidence",
          "weight": 1
        }
      ]
    }
  ]
}
```

The installed plan is `node-progress.json` at the project root. Keep it under
version control beside the authoritative checklist and case definitions. Use
`requirements_ref` as a reference to the existing authority, including an external
path or URL when needed; the plugin records that reference without opening it.
Case and evidence files must still stay inside the project. Use
stable IDs; do not remove failed criteria or adjust weights merely to raise a
percentage. `implementation` is a declaration of code status, not proof of
validation. A `blocker` is visible independently of the percentage.
Criteria may carry optional `gate` and `group` labels (nonempty strings of at most
128 characters). These are annotations on the existing requirement mapping, not
new executable nodes or separate acceptance authorities. Their meaning comes
from the project's checklist; the plugin assigns no fixed meaning to G1, G2 or
any other label. Gate and group summaries overlap and must not be added together.
When present, `scope` must be `node` or `integration` for either layer. TEST
criteria identify a native case using `case_id`; they must omit the local-only
`cases_file` field. Invalid metadata is rejected before derived reports are written.
When requirements change, revise the mapped criteria and cases. Changes to the
referenced checklist alone are not detected because its content is not loaded.
Unknown fields at plan, node, criterion or scope-decision level are rejected;
annotations such as `excluded`, `optional` or `skip` cannot silently change scope.

## Authorized scope changes (plan version 2)

Version 1 plans remain supported. To exclude a criterion, retain its complete
definition and migrate the plan to version 2 with a positive integer `revision`
and a `scope_decisions` list. Append an explicit decision for each criterion:

```json
{
  "revision": 1,
  "node_id": "assess",
  "criterion_id": "contradiction-control",
  "state": "excluded",
  "reason": "The release authority deferred this capability to the next release.",
  "authorization_ref": "docs/acceptance.md#scope-decision-17"
}
```

The example is one entry in `scope_decisions`, not a standalone plan. Retain the
existing `requirements_ref`, `nodes` and `acceptance` fields. Use `__agent__` for
an integrated acceptance criterion. `reason` and `authorization_ref` must be
nonempty bounded strings; the reference records the operator's authorization
claim and is not fetched or independently authenticated. Decisions require an
existing node/criterion pair, ordered positive revisions no later than the plan
revision, and no repeated pair within one revision. A version 2 plan without
scope changes uses `scope_decisions: []`.

The latest decision for a criterion sets its scope. To reactivate it, append a
new decision with `state: "active"`, a new reason and authorization reference.
After a version 2 plan has been reported, every change requires a greater plan
revision. Previously recorded decisions must remain an unchanged prefix;
new decisions must use a revision after the previously reported plan. Do not
delete earlier decisions or downgrade to version 1. Plan changes invalidate
current plan-bound evidence; reactivation never carries prior passes forward.
Version 2 inventory retains every previously reported node/criterion ID pair,
including integrated acceptance IDs. Migration from version 1 retains the last
reported version 1 inventory; earlier legacy edits remain supported. Removing
or renaming a criterion cannot bypass the scope decision requirement: retain
the original definition and explicitly exclude it. Definitions may be revised
under the same IDs with a greater plan revision and fresh matching evidence.
Migration rejects a last-report reference that does not resolve to a preserved
snapshot. If the report is absent, the latest dated legacy snapshot supplies
the migration baseline.

Reports preserve a private full-plan snapshot by SHA-256, including version 1
plans, before replacing the derived report. These snapshots preserve plans
actually reported; edits made before the first report cannot be reconstructed.
Keep the authoritative plan and its authorization references free of secrets.
Snapshots are bounded to 2000 files, 8 MiB per JSON file and 64 MiB total. The
report rejects malformed, linked or inconsistent snapshot history. At the limit,
archive reviewed project history as a unit instead of selectively deleting
decisions to bypass the history checks. This local audit trail is not tamper-proof.

An excluded criterion has state `excluded`, never `passed`, and no current
evidence credit. It remains visible with its reason, authorization and revision;
any historical pass remains explicitly historical. Next-criterion selection
skips exclusions. Every exclusion conservatively blocks publication, including
excluded agent acceptance criteria; this release implements no waiver of the
publication gate. Reactivate and validate the required criteria before publishing.

## How percentages are calculated

Each criterion has weight 1 unless the reviewed plan assigns another positive
weight. A node's validation percentage is the sum of approved current criterion
weights divided by its active required weights. Local and TEST columns calculate
their own ratios. The table also reports counts, so equal counts with different
weights are not mistaken for the same coverage. The structured coverage fields
`required`/`required_count` measure active scope, `excluded`/`excluded_count`
measure excluded scope, and `inventoried`/`inventoried_count` retain their total.
An empty active denominator has a null percentage, never 100%. A 100% active
percentage with exclusions is not publication readiness.

A local criterion requires a matching reviewed case, actual completion of the
mapped node and a passing runner result. Its configured `mode` distinguishes
fixture tests from real-model tests; real mode also requires a model invocation.
Real node criteria default to `scope: "node"` and require the case's `node` selector
to name that node, plus metadata of a complete model response. A global call count
from another node or a caught transport error supplies no reasoning credit.
For a model-backed whole/partial-path check, explicitly use `scope: "integration"`;
it certifies that integration criterion, not model-call attribution to each node.
Finishing a node, making a call or printing plausible text supplies no credit
without the criterion passing. Quality is limited to the reviewed assertions;
the plugin does not create a semantic rubric merely from a case name.

The runner refreshes the table after writing a test receipt. It records UTC
timestamps and the current plan hash in addition to case/configuration/package
hashes. The report uses current matching evidence and the latest relevant
verdict, preserving older receipts. A subsequent failure reopens the criterion.
Legacy receipts without the required identity do not gain automatic credit.
Local receipts and native reviews also bind to the current `evaluator_version`.
They additionally require matching `engine_sha256` and `environment_sha256` from
the execution identity helper, so changing engine code without changing its
version cannot reuse an old pass. The environment digest binds the helper's
declared dependency and observed-runtime evidence; it does not attest a remote
runtime. Missing identity fields leave legacy evidence historical, without
current credit. Native invocation receipts must match these identities before
a new review can accept them; reviews record both digests.
The identity also records `environment_observed`. Current local credit requires
this flag to be true both in the receipt and the current runtime observation;
an unavailable observation cannot grant credit merely because its unknown-state
hash matches. Reports surface `environment_observation_unavailable` and retain
prior passes as history. Native TEST review may use an explicitly unobserved
local harness because that observation does not attest the native runtime;
the separate required local criteria still block publication until validated.
An evaluator update conservatively makes previous verifications stale; do not
silently reuse approvals produced before a false-positive correction.
The report names the mismatched identity dimensions: evaluator, engine, environment, package,
configuration, plan, case and execution mode. Missing or invalid timestamps are
also reported. It shows the latest dated historical runner pass or accepted review
separately, with its receipt and original revision metadata. That recorded verdict
is not revalidated historical acceptance and earns no current credit. A historical
fixture pass is not displayed as a real-model reasoning pass for the same case ID.
If the derived-table refresh fails, the execution result and its receipt remain
available and the command reports that the table was not updated. Repair the
report with `progress report`; do not repeat a completed paid call to rebuild it.

Changes to the plan, configured case, configuration or packaged source invalidate
affected evidence conservatively. New node evidence records a criterion-specific binding so unrelated plan edits
can preserve that evidence when the complete criterion/node context and runtime
identity still match. Old receipts without the binding and final integrated
`__agent__` acceptance retain whole-plan matching. Changing
source outside the inspected deployment package requires the project to preserve
its own revision boundary. A hash of packaged files does not prove the identity
of arbitrary transitive imports or a remote deployment.

These rules may reduce a percentage after an edit. They avoid carrying an older
success forward as if it accepted the current revision. Run the informative
partial tests first; the table does not demand repeating the full suite on every
edit. An explicitly missing local case stays pending rather than blocking an
unrelated focused experiment.
Missing, duplicate, unreadable or malformed local case definitions and incorrect
direct-node selectors appear in `diagnostics.configuration_issues`, with the
node, criterion, case ID and declared case file. These mappings remain unaccepted;
the report does not invent cases or weaken the denominator. Repair the existing
case definition or mapping before testing that criterion. Schema-invalid plans
still fail validation instead of producing a partial approval report.

## Report revision transitions without restarting development

At candidate changes, summarize the following in the existing checklist, beside
the generated report rather than editing its derived values:

| Capability / criterion IDs | Prior revision and accepted evidence | Current evidence | Change impact | Next smallest check |
| --- | --- | --- | --- | --- |
| Use the actual requirement and stable IDs | Link the last accepted receipt with its original scope | Accepted, failed, stale or untested, with current receipt when present | Changed node/prompt, upstream input, shared dependency, adapter, model or plan; state unknown impact explicitly | Reproduction or affected partial path, then required native acceptance |

Distinguish a failed current observation from absent current evidence. Historical
acceptance is useful engineering history, but does not grant current credit.
Conservative package/plan invalidation can lower the formal percentage without
proving a behavior regression. Selective plan-only reuse uses the original immutable receipt and recorded
criterion binding; never copy receipt hashes or relabel revisions. Source, model,
configuration and executor changes remain invalidating. Reused node evidence is
explicitly marked with its original plan hash; final integrated acceptance remains
bound to the complete plan. An impact assessment prioritizes retests;
it does not bypass the implemented publication gate or required final acceptance.

Report current node criteria and integrated acceptance with separate counts and
denominators, the candidate/measurement ID and the main unresolved capability.
Also show the latest comparable before/after behavioral result, including useful
partial outcomes and regressions. Do not call a node-criteria percentage a project
completion percentage or add overlapping gate counts together.

Keep the current summary, blockers and next step coherent with the receipts.
Remove a resolved blocker only with evidence and preserve its historical record.
Label old summaries as historical with their revision; do not let an old heading
or an old blocker contradict the current report. Documentation-only repairs to
the authoritative checklist need not alter criterion definitions or their weights.
Batch related definition corrections before a candidate evaluation instead of
churning the plan hash during every test.

Report measured elapsed test time only at the granularity actually instrumented.
Separate model/tool execution, remote waiting, evidence review and maintenance
when known; otherwise label them unmeasured. Trial count and conversation duration
do not prove where engineering time was spent.

## Native TEST acceptance is explicit

Native invocation receipts keep technical completion separate from functional
acceptance. Inspect the result, references, permissions and actually served
revision against the criterion before recording a review:

```text
aidp-agent-flow --project <project> --json progress review-test --node assess --criterion native-contradiction --receipt .aidp-local/invocations/<receipt>.json --verdict accepted --note "Both observations are cited, the period is correct and the served revision was verified."
```

Use `--verdict rejected` for a functional failure even when the stream completed.
The command performs no cloud call. Accepted reviews require a matching native
TEST receipt and current package/target identity; PROD receipts and incomplete
technical results cannot grant acceptance. The review binds the receipt's bytes,
criterion, plan, package, configuration and evaluator. Native invocation receipts
must also come from the current evaluator and have a verified package/deployment
binding; unknown associations cannot be accepted. Later receipt changes or revision
changes make the review stale. A review is an explicit operator decision, not an
independent model judge or cryptographic attestation of the remote runtime.

Declare the whole agent's functional cases in the top-level `acceptance` list,
separately from node criteria. Record each integrated TEST review with the same
command using `--node __agent__` and that criterion's ID. This reserved identity
is not an executable graph node. The report exposes `agent_acceptance` and
`publication_ready`, in addition to the node table.

Publication requires every declared node to have accepted local and TEST criteria,
no blockers, exclusions or unplanned observed nodes, and all integrated agent cases accepted.
The lifecycle gate also verifies those TEST review snapshots against the actual
TEST snapshot read at publication and rejects unresolved configured campaigns.
The report's readiness alone is not live remote verification or authorization.

## Read the generated table

Derived artifacts are private, ignored project files:

- `.aidp-local/progress/report.json`: structured status, evidence references and
  percentage calculations for commands and future consumers.
- `.aidp-local/progress/table.md`: the readable node table.
- `.aidp-local/progress/reviews/`: preserved TEST review decisions.
- `.aidp-local/progress/plans/<sha256>.json`: immutable snapshots of reported plans,
  including original scope decisions and the plan's digest and reporting time.

The report separates implementation declaration, local validation, TEST
acceptance, overall validation, state and blockers. Its node summary is followed
by a criterion matrix containing each ID and description, optional gate/group,
layer, mode, scope, case/reference, current state and reason, current evidence and
latest historical pass. The requirements reference, current plan digest and
evaluator are visible above the matrix. Receipt contents and model answers are
not copied into the table.

The agent integration matrix has its own denominator; its criteria are never
folded into node coverage. Gate/group views likewise show node and agent
integration counts separately. The report exposes all unmet criteria, including
case configuration issues, instead of marking execution as completion. A blocked
node stays blocked even if most criteria passed. The weighted aggregate measures
only the listed validation scope; it is not a percentage of the whole business
project. Historical success, current local validation and reviewed native TEST
acceptance remain distinct even when an engine or plan edit makes every prior
receipt stale. Reporting performs no new tests, replays or cloud calls.

Update the existing checklist at capability closure and link the corresponding
receipt. The graph must satisfy its integration and user-facing requirements in
addition to these node checks. Duration currently belongs to whole test cases;
do not infer time spent developing or executing individual nodes from it.

Basis: [LangGraph node and partial tests](https://docs.langchain.com/oss/python/langgraph/test)
and [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts).

## Explicit functional publication policy (0.4.27)

Existing plans retain `strict_node_layers_v1`: local and native TEST evidence is
required for every inventoried node. This is this plugin's default policy, not a
universal requirement imposed by LangGraph. LangGraph documents [whole graph,
individual node and partial-path tests](https://docs.langchain.com/oss/python/langgraph/test).
Those patterns inform choosing relevant checks; they do not mandate our release gate.

When the accepted requirements explicitly separate functional publication from
later quality calibration, a version 2 plan may select
`publication_policy: "declared_requirements_v1"` with a nonempty
`publication_policy_reason` referring to those requirements. Preserve every
existing criterion ID and definition, scope decisions and historical evidence;
increment the plan revision when changing policy. Do not select this merely to
avoid a failed requirement or remove a criterion to pass publication.

This explicit policy requires all declared active local/TEST criteria to pass
with current identity, plus explicit native whole-agent integration acceptance.
Blockers, exclusions, stale/failed/pending evidence, unknown observed nodes and
unresolved campaign usage still block publication. The native snapshot is checked
again at publication. Nodes without criteria stay `unplanned`, with no percentage
or acceptance credit. `scope_complete` and semantic quality remain independent
of the functional publication gate. A policy change invalidates the old
plan-bound reviews; it does not transfer them to the new plan.
