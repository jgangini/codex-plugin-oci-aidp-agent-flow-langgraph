# Bounded experiment campaigns

The campaign ledger admits and records experiments; it does not generate code,
decide the next correction, grant spending permission or retry external effects.
Use it with the existing acceptance checklist and node map. Every CLI `test` and
applied `native invoke` requires a policy and a nonsecret hypothesis. Read-only
reports, fixture preparation and lifecycle plan operations make no inference calls.

## Prepare once

New CLI projects activate a fixture-only policy: at most 20 attempts, one identical
trial, zero paid model calls and zero budget. These starter limits are not an
acceptance target. Existing projects prepare a project-relative JSON definition
and run:

```text
aidp-agent-flow --project <project> campaign init --definition tests/campaign-policy.json
aidp-agent-flow --project <project> campaign status
```

`campaign init` preserves any existing `test-campaign.json`. The policy contains
exactly these fields; choose limits according to the authorized project scope:

```json
{
  "version": 1,
  "max_attempts": 12,
  "max_model_calls": 24,
  "max_identical_trials": 1,
  "native_call_ceiling": 4,
  "budget_usd": "5.00",
  "real_cost_ceiling_usd": "0.50",
  "native_cost_ceiling_usd": "1.00"
}
```

Numbers are illustrative policy values, not prices or approval to spend. Real
attempts reserve the configured model's maximum calls. Native invocations reserve
`native_call_ceiling`; the agent must separately enforce its internal model/tool
limits. Fixture adapter calls do not consume the paid-model quota.

For a finite dollar budget, each paid attempt needs a declared conservative cost
ceiling. Unknown actual charges keep that reservation instead of becoming zero.
These amounts must be grounded in the target/provider limits; the plugin does not
verify pricing or enforce a remote provider's billing cap. Compute, storage and
external tools remain governed by their actual project-side controls.

`budget_usd: null` explicitly disables the monetary gate, while attempt and call
limits remain. Cost ceilings may then be null; unknown consumption is exposed and
`billing_verified` remains false. An authorized unlimited monetary scope must not
be represented as known zero cost. When later setting a finite budget, unpriced
historical attempts must first be reconciled.

## Campaign authority and renewal

At campaign preparation or resumption, inspect the existing user authorization
and the project's actual authority checks. Record their source, actor, TEST target,
case/resource scope, permitted effects, validity, renewal conditions and stopping
conditions in the existing campaign/checklist record. Keep secret values out.
The CLI policy schema above does not gain fields for this record. Do not invent
a two-hour expiry or require a new approval solely because this guide is loaded.

Distinguish operational campaign authority from action-specific consent, evidence
freshness, credentials and spending limits. An internal short-lived declaration
may be renewed under a still-valid campaign grant when that grant covers renewal
and the project supports it. An explicit user deadline or revocation remains a
boundary; a broader development task alone does not override it. An instruction
authorizing routine same-scope TEST renewals covers subsequent renewals within
that campaign, so do not ask for the same approval each time its declaration expires.

When renewal is covered, Codex must manage it as part of the authorized test loop:

1. Verify that the campaign remains active, the grant is valid and not revoked,
   and actor, target, cases/resources, operations and limits are unchanged.
2. Use the project's verified CLI/API renewal contract at a safe boundary before
   the next dependent effect. Preserve authority versions and receipts. Reconcile
   a possibly submitted renewal before retrying; do not overwrite an old grant,
   fabricate a receipt or modify a row merely to bypass its expiry check.
3. Verify the new declaration's identity, scope and deadline against the grant.
   Continue the pending test without restarting the campaign or replaying a
   completed effect. If renewal cannot be verified, block that dependent effect
   and continue informative work that remains permitted.

Ask only for a genuinely missing authorization or necessary decision: renewal
not covered, explicit campaign expiry/revocation, changed actor/scope/operations,
or a budget, permission or publication change requiring authorization. Diagnose
technical renewal failures from their receipts; do not present a permission
question as their repair. Avoid introducing short renewal windows that repeatedly
interrupt a longer authorized campaign. Do not ask again when the relevant user
instruction already resolves the same authorization.

Never renew the consent being tested to turn an expired-consent negative into a
positive. For a positive action, obtain its own valid consent through the actual
flow. Preserve effect-time validation and isolation. Renewal does not refresh
evidence, release unknown consumption, raise quotas, alter IAM/Credential Store,
or authorize production. A credential/session refresh follows its own verified
contract and authorization, not the campaign renewal rule.

This is guidance for the Codex agent, not a CLI renewal daemon. Do not invent a
`campaign renew` command or claim every project implements a renewal API. Record
the exact unavailable contract when it blocks continuation. When the authority
adapter changes, use the focused cases in [boundary tests](boundary-tests.md#campaign-renewal-versus-action-consent).

## One hypothesis, an informative case, then a decision

```text
aidp-agent-flow --project <project> --json test --cases tests/cases.json --case selected-case --hypothesis "Check the changed routing rule" --evidence docs/observed-failure.json
```

Evidence flags are optional project-relative files; their hashes, not contents,
are retained. The attempt records its case/experiment identity, mapped criteria,
hypothesis, evidence references, reservation, outcome and next decision. Model
expectations still stay outside application input. Preserve the failed case when
adding a positive or nearby control.

Paid admission refuses exhausted call/cost reservations and unresolved attempts.
A `SUBMITTED` owner blocks all new attempts. After an attempt has reached
`UNCERTAIN` or `TERMINAL_USAGE_UNKNOWN`, a fixture-only experiment with zero paid-call reservation may continue
offline despite that uncertainty, unpriced history or exhausted call/cost quota.
It preserves every historical receipt and reservation; it neither reconciles usage
nor unlocks real-model/native work or publication. Fixture factories must honor
the injected recorded-model/services boundary; this is not an OS/network sandbox.

All experiments retain the global attempt limit. An identical experiment requires
`--repeat-reason` and remains bounded
by `max_identical_trials`; rephrasing a hypothesis does not change its identity.
Use repeated trials deliberately for stochastic behavior, not as an unrecorded
loop until an answer happens to pass. Different inputs or a revised candidate
need a new hypothesis but still consume the campaign's accumulated limits.

Results are saved after each case. If the next case cannot be admitted, the CLI
returns the completed evidence and lists cases not run. If ledger completion or
the derived table fails, the execution receipt remains available. Fix/reconcile
the control record instead of repeating a completed paid call.

## Uncertainty and reconciliation

The durable intent is created before execution. A timeout, incompatible worker
protocol, process death or native uncertainty leaves its reservation unresolved
and blocks the next paid attempt. A still-`SUBMITTED` record also blocks fixtures
until its owner/outcome is established. A failure after reservation but before native POST
can also need reconciliation; there is no safe automatic assumption of no charge.

After inspecting the project's service/runtime evidence, record an explicit
operator decision:

```text
aidp-agent-flow --project <project> campaign reconcile --attempt <id> --model-calls 1 --cost-usd 0.15 --evidence evidence/provider-run.json --note "Verified the completed run and actual usage."
```

Omit `--cost-usd` when the charge is still unknown: the cost reservation remains.
Reconciliation preserves prior states and evidence hashes; it is not independent
verification of provider billing. Actual consumption above a reservation is
recorded truthfully and blocks further admission if it exceeds the policy.
Unknown-cost native work continues to consume its declared model-call reservation
until actual counts are reconciled.

One exclusive lock protects reservations and updates. If a process dies holding
it, verify that no owner remains before manually recovering that lock. No TTL or
automatic lock deletion permits a competing attempt. Do not erase attempt history
to restart limits. A configured unresolved or over-budget campaign also blocks
publication, even when functional criteria are accepted.

Ledger files remain under ignored `.aidp-local/campaign`. The maintained policy
stays at the project root. Direct Python fixture-only harnesses may omit a policy
for compatibility; they must not be described as campaign-controlled. Real-model
`run_cases` always requires a policy. Arbitrary project code can bypass injected
adapters; this ledger is not a sandbox or an independent spending authority.

## Keep the executor stable during an experiment

Record the plugin guide version separately from the executable evaluator version.
A guide-only release with byte-identical evaluator code needs no engine adoption
or receipt rewrite. A changed engine or project supplement needs the upgrade
verification below, not a campaign reset.

Prefer an existing project-pinned environment/launcher with a verified evaluator
version and dependency lock. Verify which executable and package it resolves;
a version string alone does not prove identical code. If only a global tool is
available, record its path/version and package fingerprint, and verify them at
the safe boundary before the next experiment. Do not replace it under a running
worker. Use existing uv/project conventions for deliberate pinning; this plugin
does not automatically create a pin or install a second engine per test.

Before a batch, inspect remaining calls/attempts and per-case reservations. Report
whether the planned batch fits, rather than discovering the same capacity issue
after each case. An unlimited cloud monetary budget is not automatically an
unlimited configured call quota. Do not invent a small quota as a new user limit;
use the established authorization when setting or updating the policy. If a real
limit is exceeded, reuse an already authorized extension where applicable or ask
one concrete scope/budget question. Do not treat a technical quota change as a
new grant for credentials, business effects or production.

When paused, stop new admissions, let submitted work reach a known outcome or
record its unresolved identity, and preserve receipts/reservations. Save the
current candidate, capability, blockers and next command in the existing record.
Do not kill uncertain writes, automatically resume after a plugin installation,
or widen quota while honoring a user's pause. Zero-call offline work remains
subject to the scope of that pause; it is not permission to ignore a stop request.

## Adopt an updated plugin during a campaign

An engine upgrade is not a new campaign. Reach a safe boundary with no submitted
worker, preserve the existing policy, supplements and all receipts, then inspect:

```text
aidp-agent-flow --project <project> --json campaign upgrade
aidp-agent-flow --project <project> --json campaign upgrade --apply --expected-snapshot <adoption_sha256>
```

The second command appends a local adoption record only when its engine and
policy/ledger snapshot still match. It does not rewrite attempts, release reserved
calls/cost, increase limits, grant permissions, import an old pass as current,
install dependencies or run an agent. It inventories local runs, native invocation
receipts and TEST reviews separately. Unknown states or malformed accounting fail
closed; the recognized terminal-usage-unknown state remains unresolved for paid
work and publication, even if a partial call count is present.

Inspect project-specific launchers/supplements and test their invariants offline
before use: these are not discovered or certified by the adoption receipt. Run the
failure reproduction and a positive control with recorded outputs, then the
affected real-model and integration cases when admission permits. Existing user
authorization to adopt the plugin covers this local inspection and recording;
do not ask for the same authorization repeatedly. New spending, scope or destructive
operations still follow the project's actual authorization.

The progress report shows historical successes and why current evidence is stale.
It conservatively fingerprints the whole candidate, config, plan and evaluator;
it does not prove unrelated code is unaffected or automatically carry acceptance
across versions. Re-run the smallest affected checks first and required candidate
acceptance at integration closure. Preserve historical receipts instead of resetting
the ledger or relabeling their evaluator. Do not replace the executable while a
worker is running; a deliberate upgrade between attempts is supported by this route.
