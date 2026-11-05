# Oracle-supported profile and observed runtime parity

Oracle's [agent creation documentation](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html)
lists **LangGraph 1.0.1** as supported (reviewed 2026-11-02). The starter pins
that exact version in local and packaged dependency files. This is a documented
support profile, not certification of this plugin or of all transitive packages.
Existing projects and managed compute are not upgraded or downgraded by this check.

## Local check

```text
aidp-agent-flow --project <project> --json doctor
aidp-agent-flow --project <project> --json runtime check --require-profile
```

The selected project's interpreter supplies Python and distribution metadata in
an isolated subprocess, without importing agent code or making network calls.
The profile gate checks installed LangGraph against 1.0.1, not a version declared
but never installed. A missing environment is unknown; a different version is
outside the documented profile, not proof that every API fails. Explicit custom
versions remain available for separately verified targets. The plugin's own
environment is distinct from the agent's environment.

Preserve a reviewed project lockfile. If the environment differs, diagnose the
required APIs and approved target before changing dependencies. Oracle does not
document an entire transitive lock in this profile; do not label arbitrary
LangChain, OCI SDK or Python versions Oracle-certified. Current LangGraph
[`timeout=` and node-level `error_handler=` require >=1.2](https://docs.langchain.com/oss/python/langgraph/fault-tolerance).
Do not copy those examples into the 1.0.1 baseline without a verified compatible
alternative or a separately supported target.

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
`--require-profile` fails unless local LangGraph matches the documented profile.
`--require-parity` additionally requires **both TEST and PROD** to match the
current package, Python major/minor and exact shared distribution versions
(LangGraph, langchain-core, langgraph-checkpoint, OCI SDK). Use that full check
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
