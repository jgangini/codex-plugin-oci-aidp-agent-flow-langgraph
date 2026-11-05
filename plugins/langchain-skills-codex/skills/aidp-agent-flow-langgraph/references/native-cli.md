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

`sync` reads back exact bytes and refuses source changes when another agent owns
the folder. An unchanged shared package can be inspected without writing.
`ensure-agent` creates a CODE agent or verifies the explicitly bound identity;
it does not repair foreign/mismatched bindings. Unknown remote extra files are
not deleted: inspect them before treating the folder as an exclusive package.

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
