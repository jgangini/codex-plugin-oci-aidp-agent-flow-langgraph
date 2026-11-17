# Choose an OCI model from evidence

There is no universal best model. Grok, a newer release or the model already in
the project is not automatically the right choice for another agent or node.
Preserve an existing model until a reviewed comparison supports changing it.

## Inventory the selected region

Configure the intended nonsecret `[model].region` and `compartment_id` in
`aidp-agent.toml`, keeping the existing protected `[oci].config_file` and profile.
Then run this read-only operation when authenticated discovery is authorized:

```powershell
aidp-agent-flow --project <project> models list --limit 100
```

`--limit` sets the page size, not the total. The helper uses OCI SDK
`GenerativeAiClient.list_models` with retries disabled. It reads at most twenty
pages and 2,000 models, failing on incomplete or invalid pagination. It returns
allowlisted model identity, name, vendor, version, lifecycle and capabilities,
plus retirement/deprecation metadata when supplied. It does not invoke models,
print credentials, choose a model or modify project configuration.

This is a regional, permission-scoped inventory of pretrained and custom model
metadata. A listed or ACTIVE model does not prove the intended principal can
invoke it using the desired on-demand/dedicated serving mode. This command does
not inspect dedicated endpoints or establish AIDP runtime compatibility. Keep
unknown information explicit; do not infer missing capabilities from a name.

## Shortlist before paid comparisons

Write down the node's actual requirements: text/image/audio modalities, language,
tool calling, structured output/schema fidelity, context and output limits,
guardrails, latency needs and the project's provider/model-family adapter.
Check these against current Oracle model documentation and the target runtime.
The inventory's broad `capabilities` field alone does not establish tool calling,
context limits or JSON-schema support. A generic OCI chat adapter is not proof
of compatibility with every listed family. Account for retirement dates and
serving-mode availability before shortlisting a small number of candidates.

Freeze representative cases before comparing: identical questions, retrieved
evidence/tool results, system instructions, expected structured outcomes and
scoring criteria. Use separate reviewed cases for real-model runs, never the
fixture's exact recorded response as a quality expectation. Set explicit model
call/token limits and a total comparison/spending budget. Use the user's existing
authorization for the shortlist and paid scope; resolve material missing scope
before comparison. Do not launch a broad benchmark or repeat uncertain paid
calls automatically.

Evaluate task quality first: correct resolution, retrieval use, evidence grounding,
unsupported claims, escalation/refusal and schema/tool behavior. Then compare
latency, token usage and current costs on the same cases and serving mode. Missing
usage or price data stays unknown; faster prose is not evidence of better task
performance. Different nodes may justify different models when the measured
benefit outweighs extra operational complexity. Record the selected model/version,
region, adapter, cases, limits, results and tradeoffs, then make any configuration
change explicitly. Close affected native TEST checks before publication.

## Reasoning effort in the local generic adapter

When the user selects an effort level, an existing `[model]` section can include:

```toml
reasoning_effort = "HIGH"
```

It is optional: omission leaves provider defaults unchanged, not an assumed LOW.
The local adapter validates the value with the installed OCI SDK before credentials
or calls and passes it to the request. SDK2.189.0 accepts HIGH but rejects XHIGH;
model documentation advertising XHIGH does not prove that this client supports it.
Use the exact supported value; do not disable validation, silently downgrade, or
upgrade managed native libraries to force it. An accepted SDK field still needs
model/provider compatibility and affected native acceptance. Project-owned adapters
must establish their own parity; this setting does not rewrite native configuration.

Compare effort with fixed evidence and an explicit call budget, independently of
prompt/provider changes. Inspect finish reason, usable output and token limits;
more reasoning may increase duration and interact with evidence/consent expiry.
Do not increase those limits automatically or claim that it repairs empty retrieval.

## Primary references

- [OCI Python SDK: GenerativeAiClient.list_models](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai/client/oci.generative_ai.GenerativeAiClient.html#oci.generative_ai.GenerativeAiClient.list_models)
  defines compartment-scoped pretrained/custom inventory, pagination and retries.
- [OCI Python SDK: ModelSummary](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai/models/oci.generative_ai.models.ModelSummary.html)
  defines returned capabilities and lifecycle/retirement metadata.
- [OCI Generative AI model retirement and serving modes](https://docs.oracle.com/en-us/iaas/Content/generative-ai/deprecating.htm)
  distinguishes on-demand and dedicated retirement schedules.
- [OCI Generative AI pretrained models](https://docs.oracle.com/en-us/iaas/Content/generative-ai/pretrained-models.htm)
  links model-specific features and availability; verify current regional and
  serving-mode details for each shortlisted model.
- [Generative AI models by region](https://docs.oracle.com/en-us/iaas/Content/generative-ai/model-endpoint-regions.htm)
  distinguishes on-demand, dedicated and interconnect availability by region.
