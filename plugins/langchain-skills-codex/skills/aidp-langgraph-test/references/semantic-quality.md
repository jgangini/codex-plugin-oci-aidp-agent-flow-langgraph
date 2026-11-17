# Evidence-bound semantic quality (0.4.23 / engine 0.4.15)

Use `quality calibrate` before `quality assess`. This is post-hoc evaluation of
frozen answers, never another agent/retrieval run. It reuses the current project's
OCI model, campaign admission, one-call ceiling, subprocess timeout and accounting.
No new model/provider, tracing, dependency framework or live source capture is added.

## Method and boundaries

- [FActScore](https://arxiv.org/abs/2305.14251) decomposes factual text into atomic
  claims and measures source support. This plugin adapts that idea to supplied
  market evidence; it does not reproduce the biography benchmark or its accuracy.
- [Anthropic agent evaluations](https://www.anthropic.com/research/demystifying-evals-for-ai-agents)
  motivates multiple trials, graders and calibration. Model judgments remain
  fallible; review disagreements and curate labels independently of judge output.
- [LangChain complex-agent evaluation](https://docs.langchain.com/langsmith/evaluate-complex-agent)
  separates response, trajectory and decision. Supply only the observed context
  needed for each criterion. Missing context yields unknown, not invented success.

No 70/80-percent or other universal numeric acceptance threshold is supplied.
Supported-claim fraction and reference-fact coverage are descriptive. Zero factual
claims yields precision null, not 100 percent. Operational agent complete/partial
is separate from semantic acceptance. The executable project gate requires all
reviewed criteria to pass, no unsupported/unknown material claims and coverage of
explicitly required reference facts. These are declared product conditions, not a
research-certified universal definition of a total answer. Optional facts remain
coverage observations; do not hardcode domain entities or require every business
category for every open question.

## Reviewed case format

Reuse ordinary case JSON. Input contains only packet and source. Expected
calibration labels stay in assertions outside packet, never in model input.
Packet requires question, answer, evidence, criteria and reference_facts;
optional context holds observed briefs/trajectory/references. Every field has a
source binding: file (relative project path), sha256 and path (JSON key/index list).
A composite context binding may use parts mapping names to bounded bindings.
Source kind is curated for reviewed controls or agent_receipt for original runs.
Assessment answer must come from output of a closed identified original agent run;
question comes from that experiment's original input. Quality receipts cannot be
presented as original agents. Bytes parsed and hashed are from the same bounded read.

Evidence rows have id/text and optional url/source/published_at/observed_at,
author_name/author_url/source_title/source_description/content_basis. Preserve
observed values and record IDs; omit absent metadata rather than reconstruct it.
Do not drop author metadata when evaluating attribution, or infer official
identity, affiliation or watched-video content from a channel name. Each
support excerpt must still match its exact record and field. Description
metadata accepts up to 12,000 characters; the total packet remains bounded.
Version incomplete evidence projections and recalibrate; earlier results stay
unchanged. Include observed-author positives and wrong-author negatives.
Criteria have id/instruction. Reference facts have id/text/evidence_ids/required.
Use only essential project-reviewed facts as required; preserve a distinction
between an attributed social statement and independently corroborated truth.
Literal support excerpts authenticate text, not entailment or completeness.
The model can omit claims or misjudge support; source review remains necessary.

Calibration cases assert assessment.semantic_pass equals a reviewed boolean and
assessment.criteria.<id> equals pass/fail/unknown for every criterion. At least a
positive and negative example and all matching labels are needed for finite-set
readiness. This is an engineering check of those controls, not population accuracy.
Label curation by Codex must be declared; it is not independent human calibration.
Use a held-out reviewed set and inspect disagreements before broad conclusions.

## CLI

```
aidp-agent-flow --project <project> --json quality calibrate --cases <controls.json> --case <positive> --case <negative> --real --hypothesis "Check source-bound discrimination"
aidp-agent-flow --project <project> --json quality assess --cases <saved-answer-packets.json> --case <trial> --calibration <quality-calibration-report.json> --real --hypothesis "Audit the frozen candidate"
```

Both support --plan, --timeout, --evidence and --repeat-reason. A plan validates
preparation and forecasts capacity without reservation or model access; it is not
a judge/provider smoke test. Actual real calls need explicit case selection and
the existing campaign authority. Do not reset history or hide unknown usage.
Calibration is bound to rubric/model/configuration/engine/environment and completed
campaign receipts; stale or uncertain calibration cannot authorize assessment.
Changed selected cases are rejected before admission. A failed final campaign
write stays visible and blocks readiness even if every worker result was saved.

Quality worker receipts live in .aidp-local/quality-runs, reports in
.aidp-local/quality. Original generation receipts remain unchanged. Semantic
rejection preserves a bounded assessment while ordinary failed business output
remains private. These runs grant neither application progress nor native TEST/
production credit; do not map injected negative calibration cases as agent passes.

For repeated trials report seconds and generation/judge calls separately, all
failures and missing cases, supported claims, required/optional coverage and raw
false-accept/false-reject calibration counts. Compare equivalent facts, not word
identity. Five trials of one capture are not five independent questions.

## Correct the demonstrated boundary

Start with the failed criterion and inspect the actual brief/query, collection,
analysis, draft, repair and final synthesis in order. Record the first demonstrated
loss or attribution change; a final failure alone does not identify its cause.
Keep supported independent findings when repairing another claim, check source
qualifiers per assertion and reassess final synthesis. Do not remove source access
or force a status merely to obtain a pass. Apply one supported correction, retain
the baseline, validate discriminating controls and freeze the next measurement.
The plugin supplies evaluation and guidance, not autonomous production publication
or a guarantee that prompt edits alone ensure coherent answers.

## Diagnosing evaluator failures (0.4.24 / engine 0.4.16)

A provider failure, invalid judge response and semantic rejection are separate
outcomes. Quality-contract failures emit a bounded validation code and, when
private storage succeeds, a path/hash to .aidp-local/quality-debug containing only
the judge's final output, packet hash and validation code. Do not expose that raw
output as a public agent response. Use it to repair the demonstrated contract;
do not relax support checks or retry until a pass appears. Debug-storage failure
does not replace the original validation reason. No reasoning-channel data is read.

Known wrapped network exception types produce safe causes without copying SDK
messages. Unclassified causes stay unverified; do not invent a timeout diagnosis.
No retry or timeout change is added. Machine --json output uses ASCII escaping so
Unicode survives Windows redirected-console encodings. The independent UTF-8
private receipts remain authoritative if a console transcript is unreadable.

Before repeating calibration, distinguish a bad label or incomplete control from
a real judge disagreement. Preserve the old set, rationale and every consumed
call; version corrected controls and revalidate. A finite successful control set
does not certify human agreement, population accuracy or production readiness.

## Descriptive stability of repeated answers

Assessment reports compare covered reference-fact sets only within groups having
the same question, evidence, reference facts and observed generation identity.
Bind context.generation_identity to original receipt fields: config_sha256,
package_sha256, engine_sha256, environment_sha256, mode and model_settings (the
experiment's requested_model_settings object). Missing identity is reported as
unavailable, not comparable. Failed judges stay excluded and counted explicitly.

For nonempty unions, Jaccard similarity is intersection/union of covered fact IDs.
This is the set coefficient described in the [SciPy primary documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jaccard.html),
computed with Python sets and no SciPy dependency. This report deliberately uses
null for two empty fact sets: it does not award perfect factual stability to empty
answers. Facts must already have been reviewed and graded; this is not lexical
similarity or a detector of unsupported claims. There is no pass threshold or
automatic total label. Keep per-answer semantic gates and calibration separate.

## Structured judge output (0.4.25 / engine 0.4.17)

The built-in quality judge requests a strict JSON schema through the installed
OCI SDK, using [JsonSchemaResponseFormat](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/models/oci.generative_ai_inference.models.JsonSchemaResponseFormat.html)
and [ResponseJsonSchema](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/models/oci.generative_ai_inference.models.ResponseJsonSchema.html).
Oracle exposes this format and a strict flag; this is not proof that every model
or region accepts it. Verify the configured endpoint with a focused positive and
known negative control before the complete calibration. Unsupported requests fail
visibly: no automatic retry, model change or unstructured fallback is attempted.

The request constrains only the response structure. Exact IDs, literal evidence,
material support and coverage still pass the existing independent validator;
schema conformance does not prove factual correctness or calibration agreement.
Ordinary agent calls retain their prior format, settings and accounting. Quality
still uses one call and the same selected model, token ceiling and reasoning
effort. Preserve previous malformed responses, labels and consumption; do not
repair two JSON objects into a valid verdict or relabel a case to force agreement.

Coordinated deployment closure remains separate: pending/running operations are
not completed publications. An exhausted bounded wait must preserve its operation
and expose a non-success outcome to automation; read back the served revision and
test transport before declaring the operational TEST path closed. A synthetic
transport fixture is not business-research or production acceptance.


## Empirical claims and limits of inference (0.4.36 / engine 0.4.26)

The judge must distinguish an explicit decision not to extrapolate the answer
from an empirical negative about a population. The former belongs to scope
evaluation; the latter still needs evidence. This clarifies the atomic-claim
selection boundary without changing the validator, schema, material-error gate,
required-fact coverage or provider settings. No code filters out rejected claims.

Calibrate that distinction with positive paraphrases and contrastive negatives
for false attribution and population generalization. Preserve prior disagreements.
A categorical claim of nonrepresentativeness can be ambiguous; do not relabel it
or import a representative flag from another run to obtain approval. Operational
metadata states the observed acquisition contract, not statistical proof.
Prompt changes require real calibration; offline tests cannot certify the judge.
Follow campaign upgrade/adoption after all active attempts close, keeping prior
receipts and generation identity. A new evaluator does not rerun the agent.

## Required themes and optional detail (0.4.37)

Before calibrating coverage, separate the fact or theme needed to answer the
user's question from accessory mechanisms, examples and source names. Do not
present an inferred product requirement as an explicit user request. A required reference
that combines several independently checkable details can reject a useful answer
without identifying what was actually omitted. Keep reference text factual and
mark optional detail explicitly; document the product rationale outside the fact.
[FActScore](https://arxiv.org/abs/2305.14251) supports decomposing factual claims;
it does not define which themes an open question must cover. Essential/optional
coverage is a justified product criterion, calibrated on finite examples, not a
universal research threshold.

Freeze reviewed labels before judging. Include a positive paraphrase that retains
the theme without copying its technical label, a negative that omits the whole
theme, and a negative that invents a mechanism. Check the omission's actual
`missing_required_facts`, not just its overall rejection. Preserve grounding and
attribution checks: accepting thematic coverage must not accept invented details.
If a reference is corrected after an assessment, version and recalibrate it;
preserve the original result and do not transfer approval retroactively.

For grouped attribution, distinguish a shared predicate from thematic aggregation.
Several documents may contribute different themes without each supporting every
detail. Contrast a faithful aggregation with an explicit false attribution to all
documents, including groups identified by dates or titles. Isolate the changed
claim in positive controls so an unrelated defect cannot explain their rejection.
Exercise the application's actual citation/excerpt validator, not only the model's
boolean verdict. Keep failed provider calls separate from semantic disagreement.

## Diagnose overlapping criteria before changing labels (0.4.38)

A control that changes one phrase can legitimately fail several criteria. For
example, replacing an essential sourced finding with an invention may harm both
grounding and a utility criterion that explicitly requires supported findings.
An earlier judge pass is not proof of the expected label. Preserve the failed
calibration and audit each definition; do not relabel it to match the latest vote.

When diagnostic precision warrants separate editorial and factual dimensions,
name and version that change explicitly. Editorial relevance/proportion can judge
topical selection, organization, repetition and detail; grounding judges material
support and attribution. Essential thematic components are distinct from individual
source facts, whose coverage remains separately required. An organized false answer
must still fail grounding and overall acceptance. A faithful repetitive answer
must fail proportion. Calibrate both counterexamples before using the new rubric.
Do not force reference-fact coverage to agree with the editorial verdict, and do
not transfer prior calibration or acceptance across the changed definitions.

This is a product rubric design choice, not a research-certified threshold.
Keep the method grounded in the documented response/trajectory/step distinctions
and atomic factual support above; report finite control agreement and technical
judge failures separately. Missing metadata, malformed quotes and factual defects
are different failure boundaries and require different corrections.

## Adjudicate observed disagreement and preserve the judge profile (0.4.39)

Finite calibration readiness permits a measured evaluation; it does not override
a confirmed error found in an original answer. Preserve both the judge verdict
and the independent finding. A named collective attribution requires support
from each named member. A non-enumerated subset such as "several posts" needs
an adequate supporting subset; selecting one unrelated record does not refute
it when other admitted records support the claim. Preserve qualifiers and do
not use this distinction to excuse a false named attribution.

Separate an invalid literal excerpt from a semantic rejection. Do not silently
normalize a paraphrased quote, relabel the result or count a technical failure
as an answer-quality decision. Reconcile the attempt before a justified focused
repeat and report both attempts. Report disagreement in materiality as well;
do not turn every opportunity for shorter prose into a failed criterion when
neither the question nor the reviewed rubric imposes that requirement.

The current CLI validates the complete saved evaluator configuration and its
environment, including dependency declarations. Do not remove those guards to
reuse calibration after changing an agent candidate. A fixed, exact evaluator
profile may assess original receipts from another candidate: the quality worker
does not invoke that agent factory. Preserve the new answer's original generation
identity in its evidence binding, and distinguish it from the judge identity.
Switch a project profile only at a reconciled boundary with one owner, retain
both profiles, run quality --plan, and restore it only after the evaluation is
closed. Changing the rubric, model, OCI selectors, executor or judge environment
still requires the existing readiness checks and calibration; an old profile
must never be presented as the new agent's deployment or native acceptance.



## Bounded omissions and prospective currency contrasts (0.4.42 / engine 0.4.28)

A complete supplied text can support a statement that it does not specify an attribute, without explicitly stating that omission. Inspect the whole text and observed metadata for a counterexample. Do not infer a denomination from geography or treat a currency symbol as an explicit currency name. Preserve literal excerpt validation. A snippet supports only claims about that snippet, not omission from an unseen complete document.

Use prospective contrastive controls: justified bounded omission, invented value, unsupported global absence, and an explicitly present attribute. Keep a common supported context before varying the tested proposition; a dangling reference can create a separate editorial failure. Freeze labels before observing the judge and preserve failed calibration runs. A focused corrected pair does not retroactively approve a broader failed set or demonstrate population accuracy. Reassess the original saved answer separately from curated controls.

When assessing an original agent receipt, a supplied `context.generation_identity`
must match that receipt's package, config, engine, environment and mode, plus the
original experiment's requested model settings. Hashing an independently reviewed
context file alone does not establish that provenance. Omit unavailable generation
identity rather than copying it from another run; such cases cannot establish
frozen-generation stability.
