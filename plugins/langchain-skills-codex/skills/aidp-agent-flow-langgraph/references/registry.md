# Register a published AIDP agent through CLI

Registry registration is separate from native publication and agent-card editing.
Use the selected project's existing native binding and protected OCI identity.
This helper supports a local AIDP agent with an ACTIVE production deployment;
external agents, OAuth onboarding, permissions changes and activation changes
are outside this implementation.

```powershell
aidp-agent-flow --project <project> registry list --limit 100
aidp-agent-flow --project <project> registry inspect
aidp-agent-flow --project <project> registry register --metadata <reviewed.json>
aidp-agent-flow --project <project> registry register --metadata <reviewed.json> --apply
aidp-agent-flow --project <project> registry status
```

The default register command plans. Explicit `--apply` submits one registration.
Use existing session authorization; do not request duplicate permission when the
user has already authorized that destination and candidate. Listing and status
are signed GETs. Inspect is an observational POST that retrieves the current
published card and saves its normalized contract as an immutable local artifact.
It does not register or publish an agent.

## Review metadata

The review file contains only `version`, `display_name`, `description`, `tags`,
`labels`, `registry_metadata` and an optional empty `blueprint`. Example:

```json
{
  "version": "1.0.0",
  "display_name": "Synthetic support acceptance",
  "description": "Answers the reviewed synthetic support cases.",
  "tags": ["acceptance"],
  "labels": {},
  "registry_metadata": {
    "schema": "oasf.record@0.7.0",
    "record": {"authors": [], "domains": [], "skills": [], "locators": []}
  },
  "blueprint": {}
}
```

The helper computes native agent/workspace/compute bindings. The caller cannot
supply these identities, an interface contract or authentication material in the
review file. The native agent, entry/dependencies and compute are checked through
the existing lifecycle adapter. Exactly one ACTIVE GA production deployment is
required. Its HTTPS gateway endpoint must match the selected native agent.

Registration and persisted readback use exactly three additional metadata keys:
`agent_flow_key`, `compute_id`, `workspace_key`. The inspection request separately
uses `cluster_key` and `compute_id`; its duplicate cluster alias is not persisted
by Registry registration. All three persisted values must still match exactly.

The Registry inspection endpoint requires the canonical card URL:

```text
https://gateway.aidp.{region}.oci.oraclecloud.com/agentendpoint/{native-agent-key}/a2a/.well-known/agent-card.json
```

Preserve the returned `interface_contract` directly. Do not wrap the entire
inspection response inside it: that extra nesting caused the observed AC-0001
registration failure. An inspection requiring external authentication is refused.
`auth_key: "none"` is emitted only for this native AIDP kind after inspection
returns `auth: null`. This means authentication remains managed by the platform;
it does not make a published card or agent anonymous or grant OAuth access.

## Durable identity and readback

Before registration, the helper pins a separate Registry UUID, retry token,
target/native binding, version, reviewed metadata hash and normalized interface
hash under protected `.aidp-local/registry/`. That UUID differs from the native
agent key. Registration intent is recorded before the HTTP request. There is no
automatic retry or new-UUID fallback after timeout, HTTP error, unknown response,
changed metadata or uncertain submission.

After HTTP 200, the helper follows only the returned relative version URI in the
exact selected platform/Registry UUID/version namespace. It also reads the
bounded Registry collection and requires matching ACTIVE/latest version, native
agent/workspace/compute identity and the exact inspected contract. A plausible
response or an existing display name alone is insufficient. Collection reads
fail on truncation, changed totals, repeated identities or invalid pagination;
the bounds are twenty pages and 2,000 records. Summaries exclude credentials,
cards, permissions and raw provider errors.

For an existing registration, explicitly select its Registry key:

```powershell
aidp-agent-flow --project <project> registry adopt --registry-key <registry-uuid>
```

Adopt performs cloud GETs and writes only a protected local binding after active
version/native identity/card verification. It cannot replace a different pinned
Registry key. It can reconcile the same pinned uncertain registration when
readback proves the original intent; it never repeats the POST. An unowned name
collision requires this explicit adoption rather than duplicate creation.
After a legitimate same-agent redeployment, status refuses the old deployment
binding. Run `registry inspect` for that current publication, then explicitly
adopt the same Registry key again. This can update only the deployment identity
and revision: platform, workspace, native agent, compute, gateway and card URL
must remain unchanged, and the freshly inspected card must exactly match the
registered contract. Card or identity drift requires separate reviewed work;
re-adoption never submits another registration.
Status readback does not establish an Agent Hub conversation, orchestration,
OAuth consent, permissions changes or sharing acceptance; test those separately
when authorized.

## Deliver the verified Agent Hub portal link

After registration, return a clickable portal link to the user. Configure the
already verified working portal URL explicitly under `[native]`:

```toml
[native]
agent_hub_url = "https://<identifier>agenthub.datalake.oci.oraclecloud.com/static/ah/"
```

Then run `aidp-agent-flow --project <project> registry hub-link`. The helper first
checks the current ACTIVE Registry registration and native binding through
`status()`. It returns the configured URL only after that readback succeeds.
It does not infer a portal hostname from the platform OCID or the agent gateway,
fetch a page, launch Browser or manufacture an agent-specific chat deep link.

Supported portal paths are `/` and `/static/ah/`. A verified login-routing
fragment may contain exactly one nonempty `tenant` and `domain` value, as in
`/#?tenant=<tenant>&domain=<domain>`. Queries, other fragment parameters, foreign
hosts, ports and userinfo are refused. Do not place credentials in this setting.
The returned link identifies the Agent Hub portal, not anonymous or public agent
access. Recipients still need the appropriate OCI sign-in, tenant/domain access
and agent permissions. Portal link delivery does not verify a client invocation
or an Agent Hub conversation.

## Verified service surface and sources

The implementation uses legacy `/20240831/dataLakes/{platform}/agent-registry/v1`:
GET `/agents` with `limit`/`offset`; POST `/agents/inspect-a2a`; and POST
`/agents/{registry-key}/register`. Collection responses have `agents`, `limit`,
`offset`, `total`. Version reads use `/agents/{key}/versions/{version}`; bare
GET `/agents/{key}` was not supported in the accepted target. These operations
were accepted on an isolated synthetic native agent through signed CLI/API calls.
They are not claimed as GA `20260430/aiDataPlatforms` Registry endpoints.

- [Oracle published agent-card documentation](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-flow-deployment.html)
  documents authenticated card discovery and the separate published-card scope.
- [Oracle GA REST endpoint index](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/rest-endpoints.html)
  documents deployment/card operations; card updates are not Registry registration.
  supplied the observed Registry routes and inspection envelope.
  explains the rejected wrapper and why the normalized contract must be preserved.

No customer identifiers, captured authentication headers or other agents' card
content from that investigation belong in generated projects or reusable code.

## Resolve navigation separately from destination acceptance

`registry portal-link` validates and returns the already verified configured
`native.agent_hub_url` without querying Registry, requiring a production endpoint,
or claiming that the selected agent is available. Reuse a verified deployment
output or project resolver to configure that URL; do not navigate the administrative
UI repeatedly to discover it. Never persist sign-in redirect tokens as portal URLs.
Browser is used for the requested client conversation, not repetitive registration.

`registry readiness` checks the selected native identity and published endpoint,
then the pinned ACTIVE Registry binding. A missing publication or registration
returns `passed: false`, blockers and a nonzero CLI exit status. Transport errors,
ambiguous publications and stale/foreign bindings remain errors. A successful
result covers Registry readiness only; it always leaves the client conversation
unverified. The portal URL, ACTIVE TEST, and a completed file upload are insufficient.

When the requested publication destination is Agent Hub, close these boundaries
in order: existing candidate TEST acceptance; explicitly authorized publication;
terminal deployment reconciliation; card inspection; registration or adoption;
ACTIVE binding readback; and the actual authorized client conversation. Preserve
the existing TEST, campaign and publication gates. Do not report destination success
after a plan, submitted/pending operation, portal-link delivery or registration alone.
Use the existing publish/inspect/register/adopt operations rather than new API routes.

After a same-agent redeployment, re-inspect and adopt only when the existing
identity and normalized card still match. A clean CODE replacement creates a new
native identity: neither a previous registration nor its client acceptance transfers.
Reconcile any existing name collision; do not silently create a duplicate or reassign
an old Registry key to a new agent. Deploy Studio email navigation does not prove
that its hooks performed publication or registration; inspect the actual hook contract.

## Verify user-facing content, not only portal completion

A portal's Completed indicator proves transport/task closure, not business success.
Inspect the selected conversation's final domain result, references and failure
state. Keep distinct conversation/request identities when a user reports an error
and another test passed; inspect saved evidence before retrying paid research.

A chat client may concatenate AIMessage content. Do not expose transport envelopes,
heartbeats, revision IDs or editable draft packets as the final chat report. Verify
a readable presentation separately from the structured API protocol, preserve final
references/limits/material artifacts, and test long waits and connection closure.
Use an explicit, documented format contract; do not guess Agent Hub from subject,
thread, trace or streaming flags. Retain the machine protocol for clients that
request it and verify a real client conversation after redeploy/readiness.

## Diagnose a public card when Registry inspection fails

`registry inspect-card` performs one signed GET of the selected publication's
canonical A2A card, with redirects disabled, bounded bytes and deadline, exact
agent URL validation and publication readback. It saves a separate public-card
artifact. It never creates `inspection.json`, changes a registration or grants
readiness. The raw gateway card may differ from the Registry service's normalized
card (including an internal URL and optional authentication extension). Do not
remove those differences or import the raw artifact as a normalized inspection.
A failed `inspect-a2a` is an inspection-service failure, not proof that Hub cannot
invoke an existing ACTIVE registration; verify the requested conversation separately.
Re-adoption remains pending until a current normalized inspection can be verified.
Source: [Oracle published agent cards](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-flow-deployment.html).
