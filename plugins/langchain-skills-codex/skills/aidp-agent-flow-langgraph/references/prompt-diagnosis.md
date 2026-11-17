# Diagnose a prompt against its actual contract

Use this when a model decision or answer fails an existing acceptance criterion.
Keep the case, criterion and receipts in the project's current evaluation records;
this guide adds neither another plan nor a semantic certification service.

## Correct autonomously within the authorized development task

The Codex agent applying this skill owns the correction loop. Do not stop at a
diagnosis, offer a patch without applying it, or request permission for each
reversible edit and test already covered by the user's task. The CLI diagnoses
and compares evidence; it is not a separate background agent that rewrites code.

1. Reproduce the failure at the smallest informative boundary and identify the
   earliest evidenced defect. Inspect the assembled context and consumer before
   deciding whether the prompt, context assembly, routing, tool or adapter needs
   correction. Missing facts cannot be supplied by stronger wording.
2. Apply one coherent correction to the responsible component, including the
   prompt when the evidence supports that diagnosis. Keep the baseline, receipts,
   model and rubric fixed for the comparison; preserve unrelated user changes.
3. Execute the reproduction and a useful positive control, then relevant
   counterexamples and held-out cases. Use the existing authorized real-model
   budget when reasoning quality is the question; fixtures alone cannot close it.
   Review meaning against the source and rubric, not merely schema or transport.
4. If the candidate regresses, preserve its result and discard only its own
   experimental edits when appropriate. Diagnose the remaining defect and try
   the next evidence-backed hypothesis without waiting for another user prompt.
   If the candidate passes, check affected consumers/integration and update only
   the criterion and layer actually demonstrated. Continue to the next pending
   criterion within the active task; publication retains its existing gates.

Stopping a failing candidate or an uninformative experiment does not mean stopping
the development task. When the same failure recurs without new discriminating
evidence, change the diagnostic surface or hypothesis instead of appending another
prompt exception or repeating the same trial. Existing campaign limits still
apply. If paid work is blocked by unresolved consumption, preserve the reservation
and continue useful zero-call diagnosis where allowed. Report an external blocker
when no permitted informative work remains; ask only for genuinely missing scope,
information or authorization. This skill adds no per-iteration approval ceremony.

The required behavior is autonomous diagnosis, correction and verification, not a
guarantee that every candidate will succeed or that passing cases prove universal
correctness. Do not lower the rubric, remove failed cases or weaken controls to
declare success. Applying this skill does not by itself resume a paused project.

## Establish what the model could know and control

Trace one failed case through the actual caller: admitted data -> assembled
messages/tool schemas -> structured result -> validators -> branch/effects ->
delivered result. Inspect the final model input, not only the prompt source file.
Keep private payloads local; record hashes and the minimum excerpts needed for
review. A helper or fixture that skips a stage cannot validate that stage.

For the affected criterion, record these facts beside the existing case:

| Contract | Question to resolve |
| --- | --- |
| Task | What decision or useful answer is this node responsible for, and what is outside its responsibility? |
| Available context | Which facts, source excerpts, dates, scope and prior decisions reach this call? What was omitted, summarized or truncated? |
| Output | Which schema fields carry the answer, uncertainty and proposed next step? Which combinations are valid? |
| Consumer | Which caller validates or consumes each material field? Is a next-step label binding, advisory or unused? |
| Acceptance | Which assertions check mechanics, which reviewed evidence checks meaning, and what remains untested? |

Do not put reference answers, verdict labels or hidden evaluator instructions in
the generation input. Existing `input`, selectors, `expected_nodes`, assertions
and receipt links remain the executable case contract. A rubric is reviewed
criteria; its presence alone does not make the runner grade meaning.

## Choose the first test by the earliest evidenced failure

| Observation | First discriminating test |
| --- | --- |
| Necessary content is absent, stale or truncated before inference | Replay the source envelope through admission/context assembly; assert retained content and explicit limits. Prompt wording cannot supply unread evidence. |
| Correct content reaches the model but the answer changes its meaning | Freeze that input and model profile; compare one prompt change on the reproduction and a positive control. |
| Valid model output reaches the wrong branch or starts an effect | Inject that exact output and a contradictory combination into the partial graph; assert the real consumer, visited nodes and effects. |
| A slow call crosses evidence/authority expiry, or delivery never completes | Use the real adapter with controlled delay/completion fixtures and durable outcomes; follow [boundary tests](boundary-tests.md). |
| Transport/schema/completion fails before a semantic answer exists | Reproduce the adapter envelope or finish status first; do not score the fallback prose as successful model reasoning. |

A model field named `next_action` does not prove the graph follows it. Trace the
predicate before adding stronger instructions. If it is deliberately advisory,
record that contract; making it binding is a product/control change requiring its
own tests. Missing permission, a rejected effect or an unavailable capability
cannot be repaired by prompting the model to claim success.

## Structure a decision contract before adding rules

Organize code-owned instructions around the node's task, admitted context, scope,
decision policy and output contract. State positively what the decision should
produce. Keep the user's requested objective separate from procedural cautions,
source-selection assumptions and validation rules; do not copy system restrictions
into a business objective as though the user requested them. Domain rules belong
with their consumer and apply when relevant, rather than becoming new requirements
for every question. Preserve raw input and assemble only the relevant context at
the node boundary. Audit conflicting rules before appending another exception.

For open conversation research, missing unrequested categories are not automatically
unfulfilled requirements. Identify a concrete requested condition, unresolved entity
or absence of useful evidence before refining. Preserve support and qualifiers for
the claims selected for the answer; this does not require repeating every source's
accessory details. A concise answer still needs material scope and uncertainty.

Define consistency before repeated trials: stable supported core facts, faithful
scope, correct effect decisions and useful presentation. Do not require identical
prose or accept merely nonempty text. Keep reviewed references and verdict labels
outside generation inputs. Calibrate semantic graders on reviewed examples and
inspect disagreements; deterministic guards enforce only their stated conditions.
The plugin supplies guidance and evidence controls, not an autonomous learning
process or a certificate of answer truth. Promote demonstrated recurring lessons
through reviewed, versioned changes and regression checks.

These are adaptations of [Anthropic prompt engineering](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview),
[context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents),
[agent evaluations](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
and [LangGraph state/prompt separation](https://docs.langchain.com/oss/python/langgraph/thinking-in-graph-api).
Claude-specific tuning is not assumed to transfer to another provider; validate
the selected OCI model and the complete answer against the project's sources.

## Make a small prompt experiment

1. Name one hypothesis and an alternative explanation. Fix the model ID, adapter,
   effort/temperature, token limit, schema, evidence and rubric revisions for the
   comparison. Record the actual assembled input's revision/hash. A later model
   comparison is a separate experiment, not evidence for the prompt change.
2. State the node's task, admitted context, output contract and uncertainty behavior
   clearly. Reuse meaningful sections and a few contrasting examples when needed.
   Review conflicting or redundant rules before appending another exception;
   prompt length alone proves neither a defect nor a need to rewrite.
3. Compare the baseline with one coherent change, such as removing an irrelevant
   context section or adding one canonical example. Hold other factors fixed.
   Preserve the original reproduction, a useful positive control and nearby
   counterexamples. Keep some entities/phrasings held out from tuning.
4. Check the whole revised answer, not only the complained-about sentence. A repair
   must preserve supported content and material qualifiers while removing the
   unsupported claim. If repair is the target, verify what the second call receives:
   previous draft where needed, grounded feedback, original task and admitted
   evidence. Do not treat the first draft or the reviewer's explanation as new facts.

Useful contrasts include a lower bound versus an exact quantity; a range versus
a point estimate; missing measurement versus a measured failure; a static reference
versus observed execution; and a bounded sample versus exhaustive coverage. Keep
entity, unit, period, qualifier and attribution together. Omission is acceptable
only when the remaining answer still satisfies the criterion. An all-abstaining
candidate fails a positive case that the available evidence can answer.

Use code for IDs, arithmetic, required qualifiers in structured facts, paths and
effects where the contract permits. Review free-text entailment against source
excerpts with a defined rubric. Calibrate a model judge on reviewed supported and
unsupported examples; inspect disagreements and do not let the generator's own
approval become the sole evidence of correctness.

## Execute and decide when to stop

Reuse the [existing runner](local-development.md#select-a-useful-experiment) or
the owning project's harness. Select the responsible node/partial path in the
existing case file. Fixture execution first checks wiring; `--real` checks the
configured model only within current authorization and campaign limits. For
example, replace these paths and IDs with existing reviewed cases:

```text
aidp-agent-flow --project <project> --json test --cases tests/cases.json --case repair-reproduction --hypothesis "Check the repair consumer with recorded outputs"
aidp-agent-flow --project <project> --json test --cases tests/cases.json --case repair-positive-control --real --hypothesis "Preserve qualified facts with the fixed model and evidence"
```

These are execution commands, not an instruction to start paid calls during
plugin maintenance. Do not initialize another project or reset its campaign.

Inspect existing local receipts before spending another call:

```text
aidp-agent-flow --project <project> --json experiment diagnose --receipt .aidp-local/runs/failed.json --case repair-reproduction
aidp-agent-flow --project <project> --json experiment compare --baseline .aidp-local/runs/baseline.json --candidate .aidp-local/runs/candidate.json
```

Diagnosis shows the recorded failure stage, failed assertions and mapped criteria,
without returning private answer contents. Its first-check suggestion is a
triage aid, not a proven root cause. Comparison retains missing cases and control
regressions. Case/rubric, config, evaluator, mode or execution-control differences
make the pair non-comparable; a changed candidate package is the intended variable.
Missing metadata is unknown. Even comparable assertion gains require semantic
review and held-out evaluation; neither command calls a model or accepts TEST.

Choose repetitions before execution according to variability and consequence;
retain every trial. Stop this experiment if its input contract is wrong, the
candidate fails a critical invariant or positive control, its budget is exhausted,
an operation is unresolved, or another identical trial cannot distinguish the
hypotheses. Then follow the autonomous correction loop above: apply the next
supported correction and run its informative checks within the existing task.
Do not escalate a model, repeat paid effects or change acceptance criteria merely
because the previous candidate failed; those actions require their own evidence
and must remain within the established authorization and campaign limits.

Close only the criterion and layer demonstrated by the receipt plus review.
Record baseline/candidate verdicts, held-out result, actual calls/cost, remaining
uncertainty and the next unmet gate. Then test affected downstream consumers and
required native TEST cases on the served revision. Completed JSON, a local pass,
successful background work and a delivered useful answer are distinct evidence.
Passing this set supports these cases under the recorded conditions, not all
future questions, model versions or source changes.

## Default periods and capture identity

When the same question and clock produce different date boundaries, separate
semantic period selection from arithmetic. A model may classify a requested
period versus a default recent window; calculate the configured default from
the controller's timezone-aware clock. Preserve explicit periods and existing
calendar-date semantics. Validate the decision explicitly rather than guessing
from free-text assumptions; an unknown decision must not silently change scope.
Test non-midnight clocks, equivalent timezone offsets, explicit dates and
missing/invalid decisions. Deterministic arithmetic does not prove that the model
correctly classified what the user requested; evaluate that decision separately.

Diagnose capture replays against each receipt before combining failures. An
equivalent display label for the same organization can need a reviewed exact
alias; a changed date boundary is a scope difference. Use the existing alias
mechanism when supported by evidence, preserve the original capture, and prove
that the underlying evidence and unrelated scope guards stay unchanged. Do not
add fuzzy identity matching, enlarge the captured period, rewrite failed trials
or claim native failure merely to make a replay pass. Freeze the revised
reference before the next comparison set and report the reference change.

## Repair the demonstrated defect without regenerating the report (0.4.39)

If a repair introduces a new attribution or specificity, inspect its exact input
before adding another copy of an existing grounding rule. Unverified analysis
findings can repeat the relation that caused rejection even when the rejected
draft and review already identify it. Where the repair consumer needs only the
rejected prose, objections and source evidence, remove that redundant analysis
from this consumer; preserve the brief, admitted IDs, source scope, facts and
calculations needed to correct it. Do not remove findings from initial drafting
or another consumer that still depends on them. Hash the actual model input and
keep admission/journal fingerprints distinct when they cover a broader context.

Prefer a bounded correction over a fresh report: preserve supported material,
correct the challenged author/value/qualifier or omit an unnecessary detail.
Do not expand a short summary into a list of authors or add unrelated facts from
the evidence. This is not a literal-copy restriction: correcting a false value
may require a supported proposition absent from the rejected text. Keep the
existing repair budget, reference checks and post-repair verification. Reproduce
the original input and test preservation as well as removal before repeating
the complete frozen graph. This is an evidence-driven application pattern, not
a guarantee that a model will obey it or a new LangGraph API requirement.

## Keep repaired units independently publishable (0.4.40)

A claim-level review still removes the whole unit it rejects. If a central fact
shares a unit with an unsupported inference about corroboration or independence,
correctly rejecting that inference can remove the useful fact as well. Keep the
central unit limited to its supported subject, event/object, attribution and
necessary qualifiers. Other units need their own referent so they remain
understandable if the first unit is removed. Test removal of the first unit as
well as removal of an accessory unit, without restoring rejected fragments or
opening another repair cycle. Verify the actual generated units with saved
preconditions; a passing prompt inventory is not evidence of model compliance.

Apply collective-attribution checks to unnamed subsets too: "several versions"
cannot jointly assert location plus cause when one document supplies location
and another supplies cause. Separate their support or omit incidental detail.
This is a correction to attribution, not a ban on combining themes or describing
one event from several sources. Preserve the original failure and use the same
reviewed rubric to measure the corrected candidate.

## Separate throttling from answer quality (0.4.40)

When a frozen trial fails with a confirmed provider HTTP 429, retain that failed
trial and all admitted calls. Do not change the prompt or calibration labels to
make the transport failure disappear. Oracle recommends delayed/backoff requests
for [dynamic throttling](https://docs.oracle.com/en-us/iaas/Content/generative-ai/dynamic-throttling.htm),
but a transparent SDK retry must not collapse multiple HTTP attempts into one
counted observation. Any adopted retry must have bounded attempts, cancelable
waiting, distinct observations and the existing budget admission. An ambiguous
timeout is not a confirmed rejection. Inspect local and native wrappers separately;
a local counted retry does not establish native durable-effect recovery or parity.
Do not add retries during a frozen measurement or rerun until only passes remain.

## Late factual rejection and repair granularity

If a final review rejects previously accepted prose, compare the disputed claim
against the literal evidence: preserve its subject, quantifier, attribution and
qualifier. An earlier model verdict is fallible; neither repeated publication nor
another successful JSON response makes the claim true. Preserve every failed trial
and its latency rather than reporting only delivered answers.

Trace the consumer before changing prompts. A workflow that repairs atomic units
but then retains only their combined paragraph can retract a whole source for one
unsupported detail. Where this failure is observed, retain the admitted units in
internal state, bind them to the exact current block, and review them individually
against current evidence and objections. Keep only newly accepted units and rebuild
references, artifacts and limitations from that subset. Do not silently reuse stale
units, relax support checks, generate unlimited repairs or broaden the question.
Keep internal review state outside the public event/response protocol. If every
unit fails, the empty response must not claim that findings were preserved.

Use discriminating regressions: accept only the useful unit, reject every unit,
and accept every unit. Give units distinct evidence IDs to test removal of the
rejected unit's exclusive references and limits; also verify correction events,
replay and the existing repair budget. Then run real-model controls and the frozen
comparison set. This is project design guidance, not a generic automatic repair
command or a guarantee of semantic correctness. Prompt guidance alone does not
repair a consumer that discards the verification granularity.

This adaptation follows [LangGraph state design](https://docs.langchain.com/oss/python/langgraph/thinking-in-graph-api)
and [Anthropic agent evaluation](https://www.anthropic.com/research/demystifying-evals-for-ai-agents):
retain inspectable state and examine actual transcripts/outcomes across trials.
The selective-retention mechanism is an application design choice supported by
an observed failure, not an API requirement or a new capability of LangGraph 1.2.

## Primary references and adaptation limits

Reviewed 2026-11-02; the workflow above is original adaptation guidance. No upstream
code was copied, executed or installed, and no hosted tracing service is required.

- [Anthropic prompt engineering overview](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview): define success and evaluation before tuning; some failures are outside prompt control. Claude-specific tuning is not an OCI model contract.
- [Anthropic context engineering](https://www.anthropic.com/research/effective-context-engineering-for-ai-agents): inspect the whole context, use clear sections and canonical examples, avoid accumulating a list of special cases.
- [Anthropic agent evaluations](https://www.anthropic.com/research/demystifying-evals-for-ai-agents): separate trials, transcripts and outcomes; combine graders and inspect failures.
- [LangChain evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts): keep references outside application inputs and compare versioned experiments.
- [LangChain complex-agent evaluation](https://docs.langchain.com/langsmith/evaluate-complex-agent): single-step, trajectory and final-response checks answer different questions.
- [LangGraph testing](https://docs.langchain.com/oss/python/langgraph/test): direct-node tests bypass checkpoints; partial paths can use disposable checkpoints. Confirm APIs against the installed runtime.
- [Pinned LangGraph checkpoint regression](https://github.com/langchain-ai/langgraph/blob/eb8ec111b3e9d3108af5d7bdcac51e3e913637a0/libs/langgraph/tests/test_pregel.py#L4432): the upstream test checks the checkpoint and next node at an interrupt. This MIT-licensed reference is evidence for that upstream revision, not proof that a managed runtime supports its newer stream modes.

## Match model schemas to cross-field validation

When the model returns valid JSON but the node rejects it, compare the schema sent
to the provider with normalization and application validators. A validator such as
query-requires-justification is ineffective at generation time if the JSON schema
allows the opposite combination. Do not invent a missing justification or weaken
the validator to make a run pass.

One design is a nullable justification object that owns its optional next action;
normalize that model decision into the existing persisted state. Expose only null
when that action is not admitted. This is an application design pattern, not an
Oracle or LangGraph requirement. Test valid/invalid combinations offline, then
check the exact chosen provider/model with a focused saved-evidence decision.
Provider schema adherence does not establish semantic truth or coverage. See
[LangChain structured output](https://docs.langchain.com/oss/python/langchain/structured-output)
for schema strategies and provider-specific support.

## Verify incremental delivery and the retrieval surface

When the product requires streaming-only delivery, trace the native entry and every
caller: returning an iterator only when a request flag is true leaves an alternate
buffered path. Use the same asynchronous output contract locally and natively;
keep internal structured model decisions separate from user-facing delivery. Test
that an identified progress event reaches a live consumer while a tool is blocked,
and that a verified source capsule arrives before a subsequent source completes.
A saved final transcript or ordered event file alone does not prove live delivery.
Compare first-progress, first-useful-capsule and final-arrival times on the actual
transport, retaining network tags. Never expose hidden reasoning as progress.

If reviewed drafts are shown early, mark them as revisable. Later factual rejection
must publish an explicit correction or withdrawal with the prior block identity;
plain append-only chat cannot erase already delivered text. Multisource summaries
must retain all contributing sources rather than assuming a single source key.
Preserve the existing typed protocol for clients that replace blocks by identity.
See [LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming).

For missing social evidence, inspect the exact actor's input/output and persisted
dataset before tuning prompts or repeating a capture. Instagram popular discovery
is not a time-filtered caption search; selected public profiles/posts can instead
be read with the post reader's `onlyPostsNewerThan` plus client-side date validation.
Do not present discovery snippets as posts, captions as retrieved comments, or old
posts as recent because the collection ran today. An unavailable optional metric
must not silently become zero; an observed sentinel may be normalized to unknown
only under the affected provider/field contract, with regressions that retain text
and still reject malformed values. Retain historical parsers needed for durable
receipts without advertising obsolete retrieval routes to the planner.
See the official inputs for [Instagram discovery](https://apify.com/apify/instagram-search-scraper/input-schema)
and [post reading](https://apify.com/apify/instagram-post-scraper/input-schema).

Open-ended conversation queries may need several relevant enabled sources; honor
explicit source restrictions and require the plan to cover the selected sources.
Do not infer that every enabled connector is required or that a partial response
proves no conversation exists. Before stop-before-collection controls, inspect the
harness binding: a frozen capture scoped to one question must not be reused for
held-out entities. Keep those failure receipts; use the existing no-retrieval
fixture for intake controls and the frozen capture only for its reviewed scope.
These are evidence-backed design checks, not an automatic quality certification.
