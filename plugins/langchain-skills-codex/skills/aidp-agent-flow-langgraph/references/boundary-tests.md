# Tests across runtime and effect boundaries

Use this reference when a focused node passes but its integrated path fails, or
when changing authorization, recovery, adapters or phase contracts. Add only the
affected criteria to the existing checklist and node-progress map. The cases below
are test designs for project-owned boundaries, not checks automatically performed
by loading a skill or proof that the CLI protects code which bypasses its adapters.

## Separate clocks and effect ownership

Name the policy and clock that governs each decision. A source observation,
measured quality, user grant, client deadline and remote operation can expire or
finish independently. Advance one clock at a time, then the combinations which
matter to the route; do not use wall-clock sleeps for deterministic expiry tests.

| Boundary | Injection and control | Required observation |
| --- | --- | --- |
| First effect after I/O | Keep authority valid in the positive case; expire or revoke it during the last prerequisite read in the counterexample. | If policy requires authority at effect start, no writer/start is entered after expiry. Admission-time policy must be explicit rather than inferred. |
| Evidence used after a delay | Expire the source observation while keeping authority and quality measurement unchanged. | Reobserve or report the limitation under policy; a new read does not renew consent or a quality measurement. |
| Effect already started | Lose the client response, then pass the authority deadline before reconciliation. | Read the same intent/receipt and establish outcome; do not start the action again or erase uncertainty merely because the grant expired. |
| Refreshed evidence | Replace an observation with a genuinely new proof/version. | Recompute dependent assessment/draft as needed, preserve the old observation and keep unrelated clocks unchanged. |

Instrument entry to the real effect adapter and its durable receipt. A mock method
call, a nonempty write and a committed mutation are different observations. The
test must assert the one required by the contract. A checkpoint rollback does not
undo an external write. Reuse the project's ownership/idempotency mechanism; a new
generic job framework is not a prerequisite.

## Campaign renewal versus action consent

When operational renewal or its caller changes, use a controlled clock and the
actual authority/effect adapter. Keep these cases in the existing acceptance map:

| Case | Required observation |
| --- | --- |
| Operational declaration expires; an active same-scope grant authorizes renewal | Renew once through the verified contract, retain old/new receipts, verify the new scope, then continue the pending test without another permission question or duplicate effect. |
| Renewal reply is lost or its outcome is unknown | Reconcile the same renewal identity before any retry; no second renewal or dependent effect while unverified. |
| Campaign is explicitly expired, revoked or paused, or actor/target/scope changes | No automatic renewal or dependent effect under the old grant; permitted read-only diagnosis remains possible. |
| Campaign declaration renews, but action consent expires during I/O | The action still fails its effect-time check; renewal does not repair, extend or recreate that consent. Include a positive with its own valid consent. |
| Paid quota is exhausted or previous usage is unknown after renewal | Existing paid/publication gates and all reservations remain unchanged; renewal does not admit a blocked call. |

These cases specify behavior to verify in a project; reading the skill does not
execute them or establish native acceptance. A static documentation review can
check this decision table but cannot prove a hosted authority adapter follows it.

## Cancel the operation, not only its await

Use a controllable worker/barrier for blocking I/O. Start one read, cancel the
invocation while that read is blocked, and issue a second cancellation during
cleanup. Verify the owner signals cancellation, starts no subsequent business
work, accounts for the in-flight worker, and closes owned clients only when they
are no longer in use. Release and join test workers in `finally` even on assertion
failure. Test normal completion and exceptions as controls.

Cancelling a coroutine awaiting thread work does not establish that the thread
or remote request stopped. A bounded shutdown may instead leave an operation
explicitly unresolved for reconciliation. Record that limitation; do not claim a
drained worker or release reservations without evidence. Cancellation must still
permit the narrowly defined durable outcome/recovery record, without re-enabling
new model calls, business writes or unrestricted cleanup mutations. Assert the
final outcome or exact recovery identity, not just `CancelledError`.

## Exercise every adapter that can admit a model result

Feed equivalent provider messages through the local model adapter, the native
callback and the packaged entry path. Include a valid terminal response as the
control, truncation, filtered/refused output, absent terminal metadata and an
unexpected tool call for a text/JSON-only phase. Validate the complete message
before extracting `content`; valid JSON is not proof of completed generation.

Use the installed SDK's actual metadata and allowed termination contract rather
than imposing universal field names across providers. Tool-using phases may
legitimately produce tool calls; test their allowed transition and validated
arguments instead of rejecting all calls. The CLI's own completion tests cover
its adapter; they do not establish parity for a project callback or prove that a
hosted SDK exposes the same metadata. Keep unobserved native paths unverified.

## Keep alternate inputs behind the same required gates

Inventory accepted identifiers, aliases and compatibility routes for the affected
operation. For equivalent resource/revision inputs, compare resolved identity,
ownership, code/config revision and permitted effects before the first claim,
model call or writer. Test current, incompatible and missing revision, plus an
identifier belonging to a different run or scope. Assert that an alternate syntax
does not bypass a required gate; retain legitimate older formats when their
explicit compatibility policy permits them. Reject oversized/untrusted input at
the documented ingress boundary before activity/checkpoint persistence, while
retaining downstream validation. Do not export a project's size limit globally.

## Preserve decisions and material limits between phases

Define which routing decisions are binding and which are advisory. Test the
assessment and response together using the same admitted evidence and revision.

| Assessment contract | Permitted continuation | Response invariant |
| --- | --- | --- |
| Sufficient support | Answer the bounded question. | Claims remain supported; IDs and citations resolve to admitted content. |
| Useful partial support | Answer the supported part when policy allows. | Carry the material omissions and scope into the delivered answer. |
| Conflicting evidence | Explain the conflict, compare or clarify as the contract permits. | Do not silently replace contradiction with a resolved conclusion. |
| Binding clarification required | Ask the missing question and preserve the brief. | Do not label the unresolved substantive answer complete or begin forbidden effects. |
| Insufficient/not evaluable | Explain the concrete limitation and next useful step. | Do not manufacture a supported factual answer or imply a check was executed. |

These are example policies to adapt, not a universal enum or a ban on useful
partial answers. Check material limitations across state, schema and final text;
a list field alone cannot prove the response communicates them. Keep mechanical
invariants and reviewed semantic examples separate.

## Runtime and evidence scope

Compare the actual local interpreter/dependencies with the documented Oracle
profile and the versions observed on the candidate's native TEST/production
runtime. Missing native observations remain unknown. Passing on a newer local
version does not prove an API exists in the managed runtime. Do not upgrade hosted
LangGraph, LangChain or aidputils to make an example run.

Oracle currently documents LangGraph **1.0.1** support; current upstream
`timeout=` and node-level `error_handler=` require **1.2 or newer**. Check the
selected profile before adopting them; use existing compatible recovery mechanisms
unless the actual target and supported capability have been verified. Documented
support is not Oracle certification of the plugin, dependencies or agent behavior.

Record each criterion's revision, precondition, injection, positive control,
observed adapter/effects and evidence in the existing validation workflow. Close
the focused reproduction first, then affected integration/native cases. Neither
these examples nor a compatibility match provide exhaustive semantic coverage.

## Official sources

Verified on 2026-11-02:

- [Oracle agent creation](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html): supported LangGraph version and native lifecycle.
- [LangGraph testing](https://docs.langchain.com/oss/python/langgraph/test): isolated nodes, fresh test checkpoints and partial paths; direct node calls bypass checkpointers.
- [LangGraph fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance): version requirements and distinction between retries, timeouts and recovery.
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts): resume/replay and side-effect boundaries.
- [Python asyncio tasks](https://docs.python.org/3/library/asyncio-task.html): cancellation, shielding, timeouts and thread execution; use the matching interpreter's documentation when choosing APIs.
