# Oracle memory and external framework guidance

## Responsibility boundaries

AIDP Agent Flow LangGraph defines the development/test/publication standard.
The installed official Oracle Workbench Engineer Agent handles supported live
operations. Separately installed official LangChain/LangGraph skills supply
framework guidance; they are not bundled here or an Oracle integration.

Follow the bootstrap
[framework skills prerequisite](../../aidp-agent-bootstrap/references/framework-skills.md)
to verify the active session and load only the skills needed for this change.
This plugin retains the technical ID `langchain-skills-codex` and supplies four
AIDP skills. It is not an official Codex plugin published by LangChain. Reuse
a verified official installation; do not install a duplicate for this workflow.

Before using upstream guidance, verify installed AIDP distribution versions,
their dependency requirements and the Oracle runtime lifecycle. Oracle's Agent
Creation documentation still lists LangGraph 1.0.1 (rechecked 2026-11-07); that
statement is not proof that every managed target can be downgraded to it. A target
may have newer exact requirements from its managed runtime, utilities, LangChain
or checkpointer. Preserve that set when the proposed pin conflicts; do not
install a starter dependency file or bypass a consistency failure simply to
satisfy the documented-profile gate. Follow the target-conflict procedure in
[runtime compatibility](runtime-compatibility.md) and retain its dated evidence.

Engine 0.4.9 checks the selected runtime profile with `--require-profile`; the
historical documentary comparison remains separate. A target match does not
update Oracle's public support statement. Align the local environment to the verified target contract explicitly,
then validate the candidate and native memory boundary; installed metadata alone
is not functional acceptance. Preserve existing supported graph/agent constructors,
setup/invoke hooks, async/streaming behavior, selected OCI model, guardrails and
secret bindings. Generic MUST/ALWAYS, latest-version, provider, database or tracing
examples are not authority to migrate them.

Do not enable external LangSmith tracing or send conversation/evidence outside
approved destinations by installing a skill. Do not replace Oracle persistence
with an example database. Retry policies, replay and interrupt/resume do not
provide exactly-once external effects: use the existing budget/idempotency
ledger and reconcile uncertain paid starts. Skill invocation authorizes none
of these side effects by itself.

## Oracle-managed memory

According to Oracle, Context configures conversational memory and history
limits by messages/tokens. Multi-agent executors can be stateless, private or
shared, with different visibility. Stored Memory controls long-term extraction,
the extraction model/region, session sharing and retention. Cross-session
sharing applies to sessions initiated by the same user; it is optional.
Automatic summarization reduces older context near the model's context limit,
but is distinct from session retention and may lose exact details.

Before changing memory, establish the intended user/session scope, persistence
owner, history/token limits, extraction model cost, approved retention and test
environment. Inspect actual settings instead of assuming defaults. Do not
enable sharing, delete stored sessions or apply a retention change as a side
effect of improving a prompt. Use supported Oracle operations; never delete
shared provider tables directly.

Keep user preferences, research evidence/cache freshness and workflow
checkpoints distinct. Memory may justify suggesting a recurring query; only
an accepted schedule and an actual scheduler can initiate later runs. Reuse of
stored evidence must expose freshness and preserve source references.

## Focused memory tests

Test continuity within one session, the configured new-session behavior for
the same authenticated user, and isolation from another authenticated user.
Check supervisor/executor visibility when applicable. Exercise context overflow
and summarization without treating a summary as exact evidence. Check the
configured retention policy on disposable authorized data, without shortening
production retention or deleting real history merely for a test. Verify resume
does not duplicate external writes or charges. Report extraction/model/storage
costs separately and leave missing measurements unknown.

## Official sources

- [Oracle Agent Memory](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-memory.html).
- [Oracle agent updates](https://blogs.oracle.com/ai-data-platform/oracle-ai-data-platform-agent-updates).
- [Oracle Agent Creation and supported LangGraph](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html).
- [Oracle tool packages and platform-managed dependencies](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-flow-tools.html).
- [Official LangChain skills repository](https://github.com/langchain-ai/langchain-skills).

Reviewed on 2026-10-30. Documentation and static guidance are not live runtime
certification. AIDP memory was not modified by authoring this reference.
