# Evidence-based routing and workflow review

Original AIDP adaptation, reviewed against the official sources below on
2026-11-02. Use when changing branches, clarification or research closure, or
when repeated integrated runs do not close a capability. This is a Codex review
procedure, not an automatic semantic analyzer or a certification of an agent.
For a focused defect, inspect the connected slice; do not redesign every graph.

## Trace before choosing a pattern

Read the actual graph builder, routing predicates, state/output schemas,
callers, effects and recovery tests. Record the source revision and distinguish
registered destinations, reachable branches and paths observed in a trace.
A node is not necessarily an LLM agent. Preserve established business policy,
central or per-user identity, managed memory and the existing ledger.

Reuse the current checklist and node-progress map. For each affected decision,
record: precondition/input; predicate and allowed destinations; state preserved;
permitted model/tool calls and writes; expected outcome; source/test evidence;
observed result or uncertainty. Link a route criterion to the nodes owning it
and a partial integration case. Keep tested nodes/edges distinct from inferred
coverage; a progress percentage must retain its stated denominator and revision.

Identify a demonstrated failure, a contract inconsistency, a deliberate product
limitation, a hypothesis requiring a trace, or optional complexity. Only the
first two justify a correction without a new product decision. Preserve valid
accepted cases; reopen affected criteria when the changed behavior warrants it.

## Choose work by intent and evidence

| Situation | Routing criterion | Smallest discriminating check |
| --- | --- | --- |
| Material ambiguity | Ask if missing entity, market, metric, period or authority would change the answer/tool materially. Honor a request to agree the approach first. | Clarification branch emits the question, preserves original context and starts no external work. |
| Clear bounded request | Use permitted defaults only when product policy allows them; disclose material assumptions. Do not ask for every optional field or tool choice. | Positive case proceeds; a nearby materially ambiguous case asks instead. |
| Explanation or follow-up | Reuse eligible evidence; distinguish interpretation of a saved report from new research. | Same scope and eligible dates; no unrequested capture or action. |
| Retrieval/research | Choose a supported operation for a named information gap. Search metadata, page bodies, video descriptions, comments and numerical APIs have different evidential capabilities. | Selected tool/arguments match the question and result; tool success alone cannot pass the answer. |
| State-changing action | Use the project's explicit authorization, identity, expiry and effect boundary. Recheck short-lived authority where used after slow I/O. | Allowed action works; expired/revoked or mismatched authority starts no effect. |
| Uncertain operation | Read/reconcile the same durable identity; do not reinterpret a timeout as failure-before-start. | No duplicate effect, reservation retained as required, uncertain outcome visible. |

An output that explicitly requests clarification must not also trigger external
work, unless that combination is an intentional documented contract. A free-text
question alone is not a universal routing signal: make the schema/predicate
coherent with its meaning. Test contradictory outputs, rather than relying only
on the prompt to emit the happy path. A model-generated confidence score is not
a substitute for an explicit missing fact or permission.

For open-ended research, create a brief of the aspects needed to answer and the
role of each source type. Use source diversity when it resolves a material gap;
do not require every connector or a fixed source quota for every question.
An official statement supports what the organization says; it does not establish
independent consumer opinion. A small convenience sample does not establish
population-wide sentiment. These are quality criteria to adapt to the task, not
new spending permissions or mandatory database tables.

## Review transitions that can cause unproductive loops

- **Batch to global decision:** batch gaps are provisional. Reconcile them with
  the admitted corpus before another capture; one batch may contain the missing
  support or contradiction from another. Avoid another global model call when
  no partition or provisional gap exists. Test a gap solved across batches and
  a real unresolved gap; do not count duplicated sources as corroboration.
- **Draft to delivery:** schema-valid IDs and URLs prove attribution structure,
  not factual support. Check material claims against actual excerpts, content
  type, dates and units; distinguish observation, opinion, inference and unknown.
  A URL slug is a locator, not read content. Add a bounded factual-review/repair
  boundary where the task needs it, reusing evidence first. This can be part of
  the existing node; it need not be another agent or another call for every reply.
  Keep deterministic identity/numerical checks and reviewed semantic examples;
  an LLM judge cannot guarantee truth or silently redefine acceptance.
- **Failure to retry:** fix the earliest evidenced boundary. Wrong wording or
  citation needs a draft check; missing content may need retrieval. Do not
  restart research to repair formatting, nor suppress a provider/receipt error
  behind a catch-all branch that claims success.
- **Clarification/extension to continuation:** preserve original objective,
  supplied answers, approved scope and unresolved gaps. If closed runs/reports
  are immutable, use an explicitly linked continuation under the project policy;
  do not reopen history or interpret a bare yes as unlimited permission.
- **Saved result to delivered result:** identify the authoritative store and
  projections. Trace writes/readback on the response path and their growth with
  history. Attribute latency only from spans. Optimize affected deltas/receipts
  without weakening consistency; asynchronous projection is a product decision
  with durable recovery, not a default shortcut to success.

Choose the least complex supported pattern: deterministic routing for explicit
rules, a bounded dynamic tool/research loop for open exploration, parallel work
for independent tasks, and evaluator-optimizer only where useful feedback and a
bounded repair path exist. Multiple workers, a supervisor, Code Mode, new tables,
new models or a file split are not automatic fixes. Preserve working code and
confirm compatibility with the installed AIDP/LangGraph versions before adopting
an API shown in current upstream examples.

## Demonstrate the adjustment at the responsible boundary

Use [layered evaluation](../../aidp-langgraph-test/references/evaluation-method.md)
and the existing project harness/CLI. For the affected transition, retain the
reproduction, a valid positive control and a meaningful counterexample; separate
synthetic routing mechanics from real configured-model semantics. Keep expected
labels out of the generation input. Observe visited nodes, state deltas and
external effects, not just the final text. Use fresh disposable checkpoints for
independent cases and preserved test checkpoints for explicit resume cases.

For expiry after I/O, cancellation, model adapters, alternative input formats or
assessment-to-response changes, use [boundary tests](boundary-tests.md). Test the
connected adapters, not only the graph node: the native callback may discard
metadata, a worker may outlive its await, or another identifier format may enter
after a required revision gate. Keep authority, evidence and operation clocks
distinct. Preserve binding decisions and material limits across phase handoffs.

Examples to adapt, not a required universal suite:

- Complete topic + explicit ask decision versus the same topic ready to research.
- Short clarification completing the original request versus replacing it.
- A gap solved by another batch versus a genuine missing document.
- Claim supported by a body excerpt versus appearing only in its URL/title.
- Description metadata versus actual comments/transcript read.
- Authorized metadata lookup versus a distinct authorized write decision.
- Delayed I/O crossing authority expiry versus valid authority at the effect.
- Changed draft with no new tool calls versus explicit approved research extension.
- Growing history with unchanged data versus new data requiring verification.

Close the local reproduction and counterexamples first, then test affected real
integration boundaries and required native TEST cases on the served revision.
Do not publish or refresh production as part of this review. Record criterion,
revision, expected/observed route, result/evidence, limitation and next barrier in
the existing checklist. The plugin's runner executes configured checks; Codex
must ground the chosen criteria and review semantics. Passing reviewed cases
supports those cases, not correctness for all future inputs and source changes.

## Coordinated pause and adoption

Before changing tooling during active work, stop admitting new experiments and
new edits. Preserve uncommitted changes, checkpoints, provider IDs, receipts,
reservations, private fixtures and unknown cost. Reconcile an already submitted
operation by read when possible; do not cancel/delete it or resend it simply to
finish a pause. Save a concise handoff in the current checklist: revision,
current case/hypothesis, running/uncertain operations, last accepted criterion,
next smallest test and valid authority/budget. Do not reset the campaign or
create a new project plan to make the counters appear clear.

Adopt the updated guidance after that handoff. Verify plugin guidance and CLI
runtime versions separately. Inspect project-local patches and pending operations
before any upgrade; a guide update does not grant permission to overwrite a
runtime supplement, relax admission, or mark old evidence as current. Work on
one bounded correction, not a parallel full-agent rewrite.

## Official foundations and limits

- [LangGraph workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents):
  routing, parallelization, orchestrator-worker and evaluator-optimizer patterns;
  no universal optimum or requirement for one agent per node.
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts):
  durable pauses and resumption; use only features supported by the managed runtime.
- [LangGraph test](https://docs.langchain.com/oss/python/langgraph/test): individual
  nodes and checkpoint-based partial execution; direct node calls bypass checkpointers.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence):
  thread checkpoints and cross-thread stores have distinct responsibilities.
- [Anthropic research system](https://www.anthropic.com/research/multi-agent-research-system):
  proportional effort, tool selection, source quality and factual/citation evaluation;
  its internal benchmarks are not measured improvement of another project.

These sources guide design and evaluation. They do not certify the user's
agent, guarantee semantic correctness, authorize effects, or replace the
project's requirements and native acceptance.
