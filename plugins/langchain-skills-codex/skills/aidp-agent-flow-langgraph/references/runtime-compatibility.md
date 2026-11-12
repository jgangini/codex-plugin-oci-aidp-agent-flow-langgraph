# Selected runtime profiles and observed native parity

Oracle's [agent creation documentation](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html)
still lists LangGraph 1.0.1 (rechecked 2026-11-08). The selected tenant instead
requires LangGraph 1.2.4, checkpoint 4.1.1 and prebuilt 1.1.0, as established by
managed package requirements and a restored native runtime probe. These are
different evidence sources; neither establishes universal Oracle certification.

## Engine 0.4.9 profile selection

New projects default to `aidp-managed-1.2.4`, the observed target profile. Verify
each target before using that default. `oracle-aidp-langgraph-1.0.1` remains an
explicit historical profile; `custom` requires an exact version. Existing projects
with no runtime selection retain their historical interpretation, without rewriting
dependencies, evidence or receipts. Select this project's managed target explicitly:

```toml
[runtime]
profile = "aidp-managed-1.2.4"
langgraph_version = "1.2.4"
```

`project init --runtime-profile <id>` and `runtime check --runtime-profile <id>`
share profile resolution with `doctor`. A contradictory explicit version or unknown
profile fails. `--require-profile` checks the selected profile's installed packages,
not a requirements declaration. The managed profile requires the three versions
above; absent versions are unknown, mismatches fail the required gate.
`local_profile_status` continues to report the historical documentary comparison;
`selected_profile_status` reports the selected target separately. Matching a target
does not change the public documentation or establish native functional acceptance.

Inspect actual dependency requirements and run the environment's consistency check
before native acceptance. Never downgrade platform libraries merely to satisfy a
documentary gate. `doctor` and version comparison inspect metadata; they do not
perform `pip check`. Additional managed distributions are recorded as observations,
not instructions to install the managed AIDP runtime locally. Historical observation
files preserve their shared-package comparison. Selecting the managed profile adds
prebuilt to its required parity set; missing historical data remains unknown.

## Capabilities available in the selected environment

`doctor` reports `runtime_capabilities` by inspecting installed APIs in an isolated
process. API presence has `executed_probe=false`: it is not behavioral or native
acceptance. Unknown environments do not claim support. Before adopting a feature,
exercise its behavior in the project's installed version and on the affected native
integration boundary. Current upstream docs may describe APIs newer than 1.2.4.

The official [fault-tolerance guide](https://docs.langchain.com/oss/python/langgraph/fault-tolerance)
requires LangGraph >=1.2 for node timeouts, typed error handlers, graph defaults
and cooperative draining. Node timeouts require async nodes. Engine regressions
exercise a timed-out async node, discarded attempt output, typed handler delivery
and absence of automatic retries. Historical runtimes skip only unsupported
feature tests; their profile, initialization and fixture regressions still run.

Test transient failure/retry exhaustion, timeout, checkpoint/resume and uncertain
external outcomes separately. A timeout does not prove a remote effect was absent.
Use the project's durable effect records before retrying. Do not enable retries,
global handlers or caching merely because the new API exists. A handler must not
turn an unresolved operation or unverified answer into a successful result.

Evaluate decision, trajectory and final response using the existing TEST guide.
Those evaluation techniques are framework-agnostic, not features introduced in
1.2.4. See [LangChain agent evaluation](https://docs.langchain.com/langsmith/evaluate-complex-agent)
and [LangGraph testing](https://docs.langchain.com/oss/python/langgraph/test).

## Native observations

Inspect the actual candidate's TEST runtime using an existing authorized diagnostic
or metadata output during its normal acceptance run. Record only versions, the
verified served candidate's package hash and a nonsecret evidence reference.
Use `package check` for the local hash; a successful local import cannot prove
which package or runtime the service executed. Do not invent a metadata endpoint,
change managed libraries or invoke another model solely to obtain version strings.

Supply a project-relative JSON document with `schema_version: 1` and optional
`TEST` and `PROD` entries. Each entry has exactly these fields:

```json
{
  "schema_version": 1,
  "TEST": {
    "candidate_sha256": "<64 lowercase hex characters for the observed package>",
    "python": "3.11.11",
    "packages": {
      "langgraph": "1.0.1",
      "langchain-core": null,
      "langgraph-checkpoint": null,
      "oci": null,
      "aidputils": null
    },
    "evidence": ".aidp-local/<existing nonsecret diagnostic receipt>"
  }
}
```

The hash is a placeholder and must be replaced. Null means not observed, not an
accepted match. Add PROD only after observing that surface; never copy TEST
values to make the comparison pass.

```text
aidp-agent-flow --project <project> --json runtime check --observations runtime-observations.json
aidp-agent-flow --project <project> --json runtime check --observations runtime-observations.json --require-profile --require-parity
```

Without required flags this is an informative report, including unknowns.
`--require-profile` requires `selected_profile_status=target_match`; it checks
the managed trio, the historical LangGraph version or the explicit custom version
according to the selected profile. The documentary status remains separate and
can still be `outside_documented_profile` for a passing managed target.
`--require-parity` requires **both TEST and PROD** to match the current candidate,
Python major/minor and exact shared package versions. Managed selection includes
prebuilt; historical selection preserves its previous shared-package set. Use it
after production verification; absence of PROD before publication is expected
and must not be fabricated to satisfy it. Before publication, inspect the TEST
entry and perform its functional acceptance separately.

The comparison distinguishes unknown, stale candidate, mismatch and matched
observation. `aidputils` is reported as native-managed; not installing it locally
does not prove its hosted API compatible. Supplied observations are **not
independently attested**: the tool validates their shape and comparisons, not the
truth of a user's evidence reference. Package/version equality alone never grants
functional acceptance, publication permission or a compatibility guarantee.

## Adapter behavior and existing projects

New starters copy the same final-text/cancellation helper used by the local
adapter. The generated native entry rejects a recovered incomplete completion
within that invocation, with separate records for concurrent invocations.
This contract is for its generic OCI final-text phase, not a ban on valid tool
calls in another model's tool-using phase. SDK calls drain their worker on coroutine
cancellation; a process kill or remote timeout still needs reconciliation.
The local worker closes the SDK client it owns. Native client lifetime remains
owned by the hosted agent lifecycle; it is not closed underneath concurrent calls.

Adoption and a plugin upgrade do not rewrite existing callbacks, prompts,
checkpointers or dependency files. Apply the relevant
[boundary tests](boundary-tests.md) to those adapters and run affected native
cases against the actual candidate. Do not declare old native paths covered
merely because a new template passes offline tests.
