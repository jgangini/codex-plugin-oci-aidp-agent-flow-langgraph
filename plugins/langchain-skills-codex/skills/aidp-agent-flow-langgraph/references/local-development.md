# Local-first development contract

This original adapter follows current primary documentation and generalized
integration requirements. Examples contain no project-specific business logic,
private configuration, customer data or live acceptance status.

## Command setup and scope

The package includes a Python CLI. During active campaigns install it side by side:

```text
uv venv <versioned-engine-directory>
uv pip install --python <versioned-engine-python> <absolute-reviewed-wheel-or-plugin-directory>
<versioned-engine-executable> --version
```

Record that absolute executable and engine hash in the project's existing runbook;
keep using it for the selected campaign until explicit adoption. Do not overwrite a
shared `uv tool` installation or its active environment during another campaign.
The installed 0.4.8 package does not switch existing project executors automatically.
Check `<versioned-engine-executable> --help` from the selected repository. Installation does not prepare another repository,
create credentials or invoke a model. `capabilities` reports what is implemented
and what remains a contract gap; these are separate from live acceptance.

Use the same portable graph and prompts locally and natively. Inject the model,
tools/repositories and checkpointer through an explicit factory. The CLI expects
`factory(runtime) -> compiled_graph`, configured in `aidp-agent.toml`; it does not
rewrite an existing agent's constructor. `runtime` supplies `model`, `services`,
`checkpointer` and an `external_effects_allowed` flag set false. A project factory
must honor this boundary; the worker is not a sandbox for arbitrary project code.

## Prepare once

```text
aidp-agent-flow --json project init --path <new-directory> --name "Sales agent"
aidp-agent-flow --project <project> --json doctor
```

Initialization creates a minimal modular starter and prepares its uv environment.
CLI initialization also activates a bounded fixture-only campaign policy; read
[campaigns](campaigns.md) before enabling paid experiments or adopting an existing
project. Existing projects install a reviewed policy with `campaign init` once.
`--no-sync` creates files without dependency downloads. `--langgraph-version`
selects an exact target-compatible version; the default 1.0.1 follows current
Oracle documentation, not a statement about every existing compute. Initial
sync resolves a lockfile; later sync uses it in locked mode. It changes no native
packages. The starter is not a completed sales/research agent.
Use [runtime compatibility](runtime-compatibility.md) for the executable profile
gate and candidate-bound native observations; support is not Oracle certification.

For an existing single-file or modular agent:

```text
aidp-agent-flow --project <project> --json project adopt --factory package.graph:build_graph --entry agent/agent.py --dependencies agent/requirements.txt --python-path agent
aidp-agent-flow --project <project> --json project sync
```

Adoption writes a new `aidp-agent.toml`, refusing overwrite, and appends missing
local artifact/auth/environment ignore rules without replacing existing rules. It does not add
an adapter function, change project code or prepare dependencies automatically.
Reuse the owning project's setup when it already has a supported environment.
Only use `project sync` for a uv project. References to protected `.oci` paths
and a selected profile stay local; no private key is copied into the agent.

## Select a useful experiment

```text
aidp-agent-flow --project <project> --json test --cases tests/cases.json --case graph-fixture --hypothesis "Verify the fixture response"
aidp-agent-flow --project <project> --json test --cases tests/reviewed-real-cases.json --case relevant-local-source --real --hypothesis "Assess the frozen source evidence"
aidp-agent-flow --project <project> --json package check
```

The test command starts a fresh worker using the project's interpreter and
records package/input hashes, mode, visited nodes, assertions, model calls and
known/unknown cost. `--real` invokes the configured OCI model and requires explicit
case selection. `model_calls` counts attempted adapter calls;
`completed_model_responses` counts responses successfully returned by that adapter.
The mode distinguishes recorded fixture responses from live OCI responses.
The built-in adapter supports the generic chat family; it is
not a substitute for every model family, GuardedChatOCIGenAI, CustomRemoteSigner
or existing guardrail configuration. Verify adapter parity before comparing.

Case JSON is a reviewed list, with unique IDs, an `input` object, assertions and
optionally `expected_nodes`, `model_responses`, `service_records`, `node`,
`start_after`, `stop_before`, `require_model_call`, `trace_boundaries` and `clock_at`. Reference assertions are
not passed to the graph/model. Examples are in the generated starter. Supported
assertions are exact `equals`, `contains` and `not_empty` for dotted object paths;
these establish only their specified property, not semantic quality generally.
Semantic cases still need a defined rubric and reviewed evidence.
Real-model responses require a supported complete final response; truncation,
filtering, tool calls or malformed text cannot gain a final-answer verdict even
if the graph catches the adapter exception. Safe completion metadata is retained.

For example, given an existing factory whose `retrieve` node precedes `assess`
and `deliver`, a reviewed partial case can have this shape. Replace node names,
state and expected values with the actual project contract; the runner does not
create this topology or the evidence for you:

```json
[
  {
    "id": "assess-conflicting-records",
    "input": {"evidence": [{"id": "doc-1", "value": 10}, {"id": "doc-2", "value": 12}]},
    "start_after": "retrieve",
    "stop_before": "deliver",
    "expected_nodes": ["assess"],
    "require_model_call": true,
    "assertions": [{"path": "assessment.status", "equals": "conflicting"}]
  }
]
```

The state contains observations, not the reference verdict. A fixture model
can check wiring; `--real` plus a reviewed semantic outcome checks the model.
Verify that the factory actually uses the injected model and test checkpointer.
Do not replace an existing project signer/guardrail adapter merely to adopt this
runner. A direct-node call bypasses persistence; the partial case seeds only a
fresh local checkpoint and must show the intended path.

Selected cases are validated before any worker starts. Assertions require an
existing path and exactly one operator; `equals` preserves JSON types (`true`
does not equal `1`, and missing is not `null`). Errors explicitly recorded as tool
outcomes can be expected; an unrecorded extra/mismatched call fails even if the
agent catches it and returns plausible prose. Exhausting `model_responses`
likewise fails the model contract even if a fallback hides the exception.
`require_model_call` requires at least one successfully completed model response;
an attempted call followed by a caught provider failure does not satisfy it.
A reviewed recovery case without that requirement may accept a valid fallback.
This is not an exact-call budget assertion. Unused model responses are not required to be consumed.

An individual-node test bypasses checkpoints. A partial run uses only a fresh
local checkpointer and, with `start_after`, seeds it after the declared node.
Both partial selectors require the supplied checkpointer. The worker inspects
the checkpoint frontier after execution: `stop_reason` distinguishes the requested
`stop_before`, an earlier terminal path, another pending frontier, a dynamic
interrupt, normal completion and execution error. `frontier.expected` and
`frontier.observed` retain node names, with `null` observed when inspection was
unavailable. A requested stop passes only when the requested node is pending,
has not completed, and no dynamic interrupt occurred. A preloaded answer cannot
make an unreached stop pass. Dynamic interrupts also fail ordinary completion.
Use `expected_nodes` to assert the actually completed path. In-memory tests do not certify native
persistence or user isolation. The worker rejects a shared/managed checkpointer.
Selected frozen MCP/RAG/table results can be replayed using `runtime['services']`;
read [tools and data](tools-and-data.md) before wiring actual connectors.

`trace_boundaries: true` adds optional value-free boundary metadata: top-level
input fields, each completed node's update fields, and final observed output
fields carry SHA-256 hashes and canonical JSON byte sizes. Matching field hashes
help locate where evidence changed or disappeared; node updates are not complete
post-reducer state snapshots. No state values, prompts, interrupt payloads or
exception bodies are added to this trace. Field names and graph node names remain
metadata and should not contain secrets. SHA-256 is not anonymization: keep these
artifacts private, especially for low-entropy values. Existing reviewed case
snapshots and successful final output remain part of private run receipts;
failed output is omitted.

The trace caps completed-node records at 64, fields per observation at 32, each
serialization at 64 KiB, total serialized bytes at 256 KiB, nesting at 16 and
items per serialization at 1,024. Conservative size checks may omit a field
before its actual encoded size reaches the cap. Unsupported objects and oversized
fields receive an omission status; arbitrary object serializers are never called.
Truncation is explicit. Durations are monotonic wall time between completed-node
events, including intervening graph work, not model latency or isolated node time.

An optional timezone-aware ISO `clock_at` injects a fixed callable
`runtime['clock']` for project factories that use it. Without it the callable
returns current UTC time. This does not freeze campaign budgets, authentication,
provider clocks, receipt timestamps or elapsed-time measurement.

Results are private JSON artifacts under ignored `.aidp-local`, with summaries
on stdout and stable JSON errors. The harness disables standard LangSmith tracing
environment flags in its worker; it does not install or configure an external
tracing destination. Project code may still have other explicit exporters.
The CLI does not retry a failed or timed-out experiment. If a trusted project
factory performed a real external operation despite the local contract, reconcile
that operation before another start.

## Native boundary and remaining operations

Each private run artifact preserves a redacted case snapshot and hashes of the
complete case, project configuration, package and experiment (mode, limits and
runner version). Changing assertions, fixtures or selectors changes the experiment
identity even if the user input stays identical. Configuration contents and keys
are not stored; a hash alone does not prove which model the factory actually used.
Pin runtime dependencies as well. Snapshots remain private business data; redaction
is not a complete secret scan.

Completed error envelopes retain stage, selection, completed nodes and model/tool
counters. `last_completed_node` is not the failed node. A killed/timed-out worker
may supply no progress: reconcile project effects before retry. Known key markers
are redacted and arbitrary provider exception bodies omitted. Local assertion
PASS always retains `native_test_accepted: false`.

Keep tests, local auth and dependencies outside the packaged entry folder. AIDP
accepts modules in that folder/subfolders; no flattening is required by AIDP.
Respect a project's existing readable assembly contract rather than replacing it
as part of routine prompt work. `package check` hashes the selected package and
rejects apparent secret files/material, path escapes and symlinks. It is not a
complete secret scanner, import verifier, upload command or runtime acceptance.

The CLI implements documented 20260430 reads: `native agents`,
`native deployments`, and `native session --session <key> [--trace <key>]`.
Session/trace details go to a protected local artifact, not general stdout.
These reads do not certify the served source revision or TEST quality.

The package now provides scoped native lifecycle, invocation and Registry helpers.
Read [native CLI acceptance](native-cli.md) for exact commands, mixed GA/legacy
contracts, explicit apply, durable operation receipts and served-revision gates.
Read [Registry](registry.md) for inspection, registration and existing-record
adoption. A target must support those contracts; these helpers do not infer a
TEST selector from a production response enum.

Native integration acceptance is still necessary for managed memory, credential
bindings, packaging, deployed output protocol and identity. Use small native
checks when changing those boundaries, and close the agreed final matrix before
authorized publication and Agent Hub acceptance. Do not redeploy for every
prompt experiment or reopen unrelated accepted cases.

## Sources

- [Oracle Agent Creation / Testing](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html): entry class, folders and packaged execution.
- [Oracle Agent REST operations](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/api-agent.html): current data-plane operations.
- [Oracle redeploy request](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aiwap/op-aidataplatforms-aidataplatformid-workspaces-workspacekey-agents-agentkey-deployments-actions-redeploy-post.html): do not infer a TEST request selector from response enums.
- [OCI inference client](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/client/oci.generative_ai_inference.GenerativeAiInferenceClient.html): signed model calls from a selected config.
- [LangGraph tests](https://docs.langchain.com/oss/python/langgraph/test): nodes and partial execution with checkpoint distinctions.
- [LangGraph application structure](https://docs.langchain.com/oss/python/langgraph/application-structure): modular organization; LangSmith deployment configuration is not an AIDP requirement.
