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
