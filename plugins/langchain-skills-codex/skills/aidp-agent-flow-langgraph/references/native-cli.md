# Native CLI acceptance contract

Use these commands after local cases pass, with the project's selected protected
OCI profile. The package contains scoped implementations; every mutating lifecycle
command plans by default and requires `--apply` to submit. Installing/loading a
skill submits nothing. No command starts compute, provisions tables, grants IAM,
rotates credentials or changes another agent.

## Project binding

In addition to endpoint/platform/workspace, configure `[native] remote_root`,
`display_name`, `compute_key` and, when adopting an existing agent, `agent_key`.
Use a canonical `/Workspace/.../agent` folder owned by the selected project.
The entry folder and descendants form the package. Keep tests, `.oci` and local
artifacts outside it. Reuse compatible ACTIVE compute; verify its runtime before
selecting dependency versions. Do not restart shared compute to prepare a test.

```text
aidp-agent-flow --project <project> --json native sync
aidp-agent-flow --project <project> --json native sync --apply
aidp-agent-flow --project <project> --json native ensure-agent --apply
aidp-agent-flow --project <project> --json native test-init --apply
aidp-agent-flow --project <project> --json native status
aidp-agent-flow --project <project> --json native session-create --apply
```

File upload acknowledgements may echo the uploaded bytes (including Python text)
with a non-JSON content type. Evaluator 0.4.13 treats FILE acknowledgements as bounded
bytes and confirms the saved hash by GET; JSON metadata is not required for file
write success. An older uncertain file intent can reconcile against those exact
bytes without uploading it again. Other lifecycle response contracts remain JSON.

`sync` reads back exact bytes and refuses source changes when another agent owns
the folder. An unchanged shared package can be inspected without writing.
`ensure-agent` creates a CODE agent or verifies the explicitly bound identity;
it does not repair foreign/mismatched bindings. Unknown remote extra files are
not deleted: inspect them before treating the folder as an exclusive package.

## Inspect an existing installation before changing paths

```text
aidp-agent-flow --project <project> --json native inspect-binding
```

This read-only diagnostic requires the selected agent identity and matching CODE
type/compute. It reports actual versus configured bindings even when paths differ,
then reads TEST through its explicit legacy selector and production through GA.
It sends GET requests only, creates no operation journal and neither reconciles
old writes nor grants TEST acceptance. `status` keeps its strict binding checks.
Capture this result in the project's private evidence before any migration.

Keep these locations distinct: `pathInfo` locates the agent metadata in the
workspace; `entryFilePath` and `dependenciesFilePath` select executable inputs.
Oracle's UpdateAgent request accepts the latter fields, but not `pathInfo`.
Moving a workspace object uses the separate MoveObject contract. A matching
folder name, a `FOLDER` listing or the presence of source files does not identify
a workspace object positively correlated with the selected agent. A CODE agent
is not guaranteed to appear as an `AGENT_LAKE_FLOW` workspace object. This command
does not discover such an object and reports `metadata_object_verified=false`;
metadata relocation remains unverified. This does not prevent the separate,
explicit executable-input rebinding operation below.

For an authorized migration, preserve the exact agent/compute identities,
production snapshot, installer recovery and pending effect records. Use the
project's versioned migration mechanism with backups, concurrency control and
readback of the supported operation. Reconcile an uncertain submission before
retrying. Never recreate an agent, move an ordinary folder as a substitute, or
delete a receipt to bypass ownership checks. Refresh the existing TEST candidate
only after its bindings and exact package are verified; inspect the served
revision and affected functionality afterward. Installation-specific receipts,
resource identifiers and secrets remain project-owned, outside the plugin.

Sources: [Oracle UpdateAgent](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-agents-agentkey-put.html),
[Oracle MoveObject](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-actions-moveobject-post.html),
and [Oracle agent operations](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-operations.html).
These contracts guide inspection; successful metadata reads do not validate a
move or certify live streaming.

## Workspace control-folder handoff

Keep workspace-object movement separate from CODE metadata and executable-input
rebinding. For the verified target, MoveObject `toPath` is an **existing destination
folder with a trailing slash**; it is not the final renamed path. The target
returned HTTP 400 without that folder URI marker, including when metadata already
showed the folder. A trailing-slash request succeeded and preserved the child name.
Create/verify the owned container first, then move each selected immediate
child into it, preserving the child's name. Do not infer that MoveObject renames a
folder or updates a CODE agent's `pathInfo`.

An installer coordinator pins its complete bounded control inventory, persists a
pending child before submitting and confirms source absence plus exact destination
hashes. Move recovery directories first and the authoritative installer receipt
last. A lost reply is reconciled by those observations, without repeating an
uncertain move. Only a recorded definite rejection allows correcting that request.
Keep exclusion of older hooks after retiring their receipt; otherwise an old
installer may recreate it. Project-specific control journals and restoration stay
with that project's versioned installer, not a guessed universal receipt schema.

This is a contract lesson verified during integration, not evidence that all
projects or new tenants have passed migration. Native technical verification and
semantic quality acceptance remain separate.

Sources: [CreateWorkspaceObject binary response](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-objects-post.html)
and [MoveObject request](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-actions-moveobject-post.html).
The working folder URI was established by actual rejection and successful
readback on the target; the public description alone did not establish its syntax
or rename semantics. Reverify an unsupported target instead of declaring support
from a mock transport.

## Rebind executable inputs without recreating the agent

Version 0.4.17 adds the reusable `native rebind` command and explicit staging
`native sync --for-rebind`. These use documented UpdateAgent fields; they do not
move agent metadata, delete old source, create another agent or grant TEST credit.
The implementation has offline transport/recovery regressions. A read-only plan
against a target is not a live mutation or native acceptance of that contract.

Keep `[native] remote_root` as the destination code folder and inspect the
observed metadata location before staging. TEST and publication require that
CODE metadata and code share that root. Rebinding executable paths cannot move
`pathInfo`. If the metadata location differs, use the explicit development
replacement procedure below; do not apply rebind and expect TEST refresh to
complete. Rebind is for supported executable binding corrections with aligned
metadata, not a metadata relocation.

For aligned metadata, preserve the current config and inspect the binding first:

```text
aidp-agent-flow --project <project> --json native inspect-binding
aidp-agent-flow --project <project> --json native rebind
aidp-agent-flow --project <project> --json native sync --for-rebind
aidp-agent-flow --project <project> --json native sync --for-rebind --apply
aidp-agent-flow --project <project> --json native rebind --apply --expected-binding <binding_sha256>
aidp-agent-flow --project <project> --json native status
aidp-agent-flow --project <project> --json native test-refresh --apply
```

The rebind plan reports actual/target bindings, package fingerprint, ETag presence
and `binding_sha256`. Reuse that hash only while its bindings, package and observed
deployment snapshots still match. Staging creates only absent files or accepts
identical ones; it refuses conflicting destination bytes, the prior code tree,
foreign metadata/code ownership, ACTIVE production and currently CREATING
deployments. It leaves old files available for recovery. Normal sync continues
to verify metadata and executable-file ownership after metadata/code separation.

Apply requires exact agent/type/name/compute/metadata identity, complete package
byte readback and an observed ETag by default. A durable intent saves the prior and desired
binding before the conditional PUT, which contains only entry/dependency paths.
Readback checks identity, package bytes and unchanged production. TEST credit is
invalidated durably before closing the intent; recovery can finish those writes
idempotently. An already-completed PUT whose reply was lost is reconciled from
readback without resubmission. An unresolved outcome that is still at the prior
binding blocks another write; do not erase its journal or assume failure.

When a target omits ETag, evaluator 0.4.12 provides the explicit per-operation
`native rebind --apply --expected-binding <hash> --allow-no-etag` mode. This is
not an additional permission request: an authorized project coordinator may select
it as part of its existing migration. Prefer a valid ETag whenever returned;
malformed ETags still fail. Without one, the operation re-reads the agent binding
and observed record version, checks deployments again, journals the absence of
atomic concurrency control and verifies the result. The version field is never
fabricated into an ETag. A read-to-write race remains; readback is not a CAS lock.
Serialize project operations with their existing lock, preserve recovery evidence
and report this mode explicitly. Missing ETag alone does not prove that AIDP cannot
update an agent: Oracle documents if-match as optional. Lost-write uncertainty
still requires reconciliation rather than another PUT.

Agent ETags do not lock deployment operations. TEST snapshots in the plan are
observations, not a cross-service lock; final TEST acceptance is always false.
Refresh/reconcile the selected TEST and verify its actually served candidate.
Do not start concurrent operations on the same agent. No automatic rollback is
provided: retain the prior binding receipt and untouched source, and plan any
restore against its verified original package.

A project with its own installer/maintenance receipts must coordinate those
records through its versioned migration mechanism before applying this command.
The plugin journal is not a substitute for a project's installer recovery or
control-folder migration. Plan first; do not bypass those project guards. The
supported command is executable-input rebinding, not a generic CODE metadata
move or a full installation-layout converter.

For explicit restoration after a terminal failed TEST, `native test-refresh
--apply --recover-failed` permits the existing FAILED deployment to use the same
redeploy route. It does not permit CREATING/unknown states, create an agent, reset
a session, bypass pending-write reconciliation or grant acceptance. This branch
has offline transport tests; the service response still determines live support.
Async-operation cancellation is not an additional deployment enum. A project
coordinator must select and verify the exact backed-up package before restoring.

## TEST, publication and iteration

The supported target uses **GA 20260430** for objects, CODE agents, metadata,
session reads and publication, and **legacy 20240831** for high-code TEST actions
and session creation. These are separate contracts. A new target must expose
these operations; a successful metadata read does not certify the entire cycle.

First TEST uses workspace `actions/redeployAgentFlow` with an explicit TEST
selector. Refresh uses the separately verified nested agent-flow redeploy route.
Neither command substitutes a GA production request with a guessed TEST field.
`status` reconciles async operations and scoped deployment readback. Wait for the
recorded operation to succeed and the current TEST to become ACTIVE before invoking.
Do not poll by repeatedly submitting.

A question file is project-relative JSON with only a stable `id` and `question`:

```json
{"id":"accepted-case","question":"A bounded question from the acceptance matrix"}
```

```text
aidp-agent-flow --project <project> --json native invoke --surface TEST --question-file tests/native-case.json --expect "required fact" --apply --hypothesis "Verify the candidate response"
aidp-agent-flow --project <project> --json native publish
aidp-agent-flow --project <project> --json native publish --apply
aidp-agent-flow --project <project> --json native status
aidp-agent-flow --project <project> --json native invoke --surface PROD --question-file tests/native-case.json --expect "required fact" --apply --hypothesis "Check the published revision"
```

TEST invocation uses the helper's validated session or explicit `--session`.
When the target API omits a session state, preserve its verified agent/compute/
endpoint binding and report readiness as unreported. Do not infer expiration or
create a duplicate session. A requested invocation still requires an ACTIVE TEST
deployment and a bounded response; a known inactive/failed session is refused.
Expected fragments are assertions, never model input. The gateway/agent/surface
and TEST session are verified before a single POST. SSE and response sizes are
bounded, nested errors fail, and final output is not duplicated from cumulative
events. A response requires an explicit stream completion marker; an EOF-only
partial answer remains uncertain even when it contains the expected text.
Native gateway region is checked against the AIDP endpoint/platform, independently
of the selected inference model's region. Answers/events remain in protected
artifacts; stdout contains verdicts.
Socket/read deadlines are finite; use an outer process deadline when a hard
wall-clock limit is required. A transport/stream uncertainty needs reconciliation.

Publication requires a reconciled ACTIVE TEST receipt for the exact package and
the functional acceptance gate in [node progress](node-progress.md). All mapped
nodes need current local/TEST criteria, the agent needs integrated TEST acceptance,
and blockers or configured unresolved campaigns stop publication. A technical
receipt alone cannot satisfy that gate. The accepted native receipts must match
the actual TEST snapshot read by the lifecycle command, including on an otherwise
up-to-date publish. Authorization and `--apply` remain separate requirements.

Native invocations use a [campaign](campaigns.md) policy and hypothesis. The package
hash is only attributed when the reconciled snapshot matches the actual deployment
before and after the call. An unknown or changed association is exposed as
`package_binding_verified=false` and cannot receive functional TEST credit.
Initial deployment includes its name; **redeployment omits create-only
`displayName`**, avoiding the observed duplicate-name conflict. Known FAILED
operations are reconciled with scoped readback before a later explicit changed
request; no automatic mutation retry or journal deletion is provided.

For a change, keep case IDs and reviewed inputs stable, iterate locally, sync,
refresh TEST, verify the served revision and affected cases, and check that PROD
still serves the prior revision. Publish only after those gates, then verify PROD.
The same frozen case can run on a changed native deployment after a complete,
error-free prior response; its earlier receipt is archived. An uncertain prior
response or an unchanged deployment needs reconciliation before another start.
Registry is a separate step: read [the Registry contract](registry.md).

## Generated state

All generated evidence stays under ignored `.aidp-local/`: runs, native operation
receipts, invocations, model inventory and Registry state. Keep one project
acceptance matrix and derive progress from its results. Do not turn an ACTIVE
resource or completed request into a green quality verdict.

## Sources and limits

- [Oracle Agent Creation and TEST](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html).
- [Oracle Agent REST operations](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/api-agent.html).
- [GA redeployment](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-agents-agentkey-deployments-actions-redeploy-post.html).

The legacy TEST/Registry surfaces are target-verified integrations, not a claim
that every public GA SDK provides them. Stop on unsupported/auth failures and
record the actual gap; never replace these requests with guessed endpoints.

## Exact source layout and development replacement (0.4.22)

`native inspect-layout` is read-only. It compares the local package inventory,
file hashes, folders, executable binding and CODE metadata root with AIDP.
Both TEST initialization/refresh and production publication now require an exact
match before submission. Required files being present is insufficient: extra old
modules, nested legacy packages, empty obsolete folders and separate metadata roots
fail the gate. A layout pass is not semantic quality or native research acceptance.

For an explicitly authorized development replacement when metadata cannot be moved:

1. Use the installation's owning coordinator and existing campaign authorization.
   Preserve private receipts and exact source bytes locally before retirement.
2. Plan `native retire-agent`; apply with its `--expected-binding` hash and `--apply`.
   This journaled DeleteAgent targets only the selected CODE object, requires no
   production deployment or creating TEST, and does not delete compute/credentials.
   Agent and session identities may change only under explicit replacement scope.
3. In a separate project-owned context create the CODE at the intended source root
   with the existing compute (`native ensure-agent --apply`). An existing installer
   must coordinate new identity/session receipt adoption; do not edit keys manually.
4. `native prune-tree --definition <project-relative-json> [--apply]` removes one
   obsolete child subtree. Definition is `{"tree":"/Workspace/.../agents/old",
   "hashes":{"old.py":"<sha256>"}}`. Hashes must match every remaining file;
   unknown/drifted content blocks deletion. Empty inventories permit only verified
   empty obsolete folders. Current package files and foreign agent overlaps block.
   Exact bytes are backed up locally, deletes journaled and absence read back; lost
   replies reconcile without repeating a submitted delete. DeleteWorkspaceObject
   may be asynchronous: wait for absence rather than treating acceptance as removal.
5. Inspect the exact layout, initialize TEST, create a new TEST session and probe
   the served revision. Commit the owning installer's new identities only after
   verified TEST. Invalidate earlier acceptance. Do not leave old code in the
   executable source root as a recovery strategy or call that a clean deployment.

CreateAgent documents pathInfo; UpdateAgent does not accept it. MoveWorkspaceObject
documents FILE/FOLDER kinds and is not evidence of supported CODE metadata movement.
No operation here grants production replacement authorization. Publication retains
its existing TEST and functional review gates as well as the new layout gate.

Sources: [CreateAgent](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-agents-post.html),
[DeleteAgent](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-agents-agentkey-delete.html),
[DeleteWorkspaceObject](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-objects-objectpath-delete.html).

## Native client events with diagnostic tracing (0.4.26)

The verified target can attach large diagnostic `spans` and `resources` to
`output_text` content and add typed `trace` content beside a small public message.
The native CLI separates the transport bound (32 MiB total, 4 MiB per frame) from
captured client events (2 MiB). These are operational limits, not quality metrics.
The existing deadline, event count, event-name and answer bounds remain enforced.
Capture accounting includes JSON, control and DONE frames.

Only the observed diagnostic attributes and typed trace parts are excluded from
client events. Public text, source tags inside that text, completion markers and
genuine error parts retain their checks. Full diagnostic tracing is not retained
in the invocation receipt and is not a public progress capsule. The invocation
still requires explicit completion and a useful asserted answer to pass. A bounded
failure remains failed; it never causes an automatic retry or a second paid start.
Reconcile or cancel an uncertain request before a distinct attempt.

## Complete transcripts and durable deployment receipts (0.4.27)

The public answer/transcript bound is 128 KiB characters. Some verified agents
emit cumulative newline-delimited public progress packets in one `output_text`;
that transcript is longer than its final report. This operational bound does not
approve long prose or change the agent's prompts. Preserve the selected project's
protocol reducer to extract its final response. If answer extraction fails after
an explicit completion marker, the receipt retains that observed completion while
the invocation still fails. Never relabel the original failed trial as successful.
Recover a completed durable request with its same request ID and session before
starting another research run; reconcile and verify that no paid effect repeats.

Deployment reconciliation persists the canonical package/snapshot receipt before
closing its intent, so interrupted local persistence can resume without another
deploy POST. For a project with an owning installer, use its existing distributed
lock around CLI deployment and the subsequent owner observation. Retain that lock
if submission remains uncertain, reconcile the exact native intent and release
only when its side effects and owner state are known. Preserve historic receipts;
a fresh observer must not masquerade as an earlier submission. Do not invent an
adoption record when exercising the actual CLI TEST refresh suffices to validate
the requested deployment route. Publication and Registry registration are separate
commands, followed by the actual Agent Hub client test.

## Guarded updates and repeated lifecycle operations

A project-owned installation must retain its owning journal, inventory, backups
and writer lock while using the CLI. Native sync/refresh receipts do not replace
that installer's commit. When PROD is present, use the project's explicitly
snapshot-preserving TEST maintenance adapter; do not bypass its guards, undeploy
PROD, fabricate owner receipts or silently adopt a different agent. Pin the full
PROD binding before writes and compare it through TEST verification and commit.
Oracle documents publication as a snapshot and redeployment as the update boundary:
https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-flow-deployment.html

For recoverable updates of existing files, `native sync --expected-inventory
<project-relative.json> --apply` admits a sealed definition with exactly `version:1`,
`package_sha256` of the desired complete package, and `files` mapping every package
path to one or two allowed SHA-256 values (before and target). The desired hash
must be included for every file. Unexpected or missing bytes fail before writes;
each changed file is checked again immediately before its upload and read back.
This is read-before-write/readback under the owner lock, not server-side CAS.
Protect/reconcile concurrent writers rather than claiming atomicity.

Accept `applied:false` only together with verified readback, the exact expected
package hash and, when requested, checked preconditions. A successful no-op is a
normal resume result. Up-to-date deploy plans also return their verified package
hash. TEST/PROD deployment intents bind the previous deployment snapshot, allowing
a later authorized A-to-B-to-A cycle without reusing its original submission.
File uploads can create a subsequent generation only after their earlier intent
is reconciled and current bytes require a write. Unknown/pending submissions keep
blocking new attempts; historical intents and retry tokens remain unchanged.


## Explicit long research deadline (0.4.30)

`native invoke --timeout` accepts a finite value from 1 to 1800 seconds; its default
remains 90 seconds. Select the budget before the experiment, for example 600 for
a measured multi-source investigation. The invocation receipt and campaign identity
retain that control. Frame/total/capture/answer bounds, finite socket timeouts and
the monotonic elapsed check remain active; no timeout causes an automatic retry.
This is not an exact wall-clock cutoff while a socket read is blocked. A consumer
timeout does not prove the remote work stopped: reconcile its request and effects
before another invocation. Do not relabel a failed original receipt as accepted.

## Invocation admission preflight

The campaign CLI validates the question, frozen case identity, prior receipt,
surface, timeout, endpoint and TEST session before reserving a paid attempt.
This preflight may perform signed metadata GETs but sends no research POST and
does not claim the invocation. Invocation rechecks these conditions and performs
the existing exclusive claim after admission. A race or later failure can still
require reconciliation; errors after a possible POST never imply zero usage.
No old receipt, reservation or campaign approval is rewritten by this change.
