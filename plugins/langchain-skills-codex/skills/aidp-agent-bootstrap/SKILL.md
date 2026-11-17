---
name: aidp-agent-bootstrap
description: Prepare or repair an Oracle AIDP agent development environment by checking the existing project toolchain, authentication, verified CLI contracts and native TEST target. Use on first setup or environment/auth failures; not for provisioning a platform, creating tables or publishing an agent.
---

# AIDP agent bootstrap

Apply the bootstrap idea from Migration Workbench: establish a reproducible
project-local environment once, verify it, then hand off to development. This
includes the plugin's executable `aidp-agent-flow` project helpers. Installing
or loading this skill alone executes nothing. Do not bootstrap again for
each node or prompt edit when the relevant environment is already verified.

## Framework skills readiness

Before authoring or changing framework code, follow [official framework skills](references/framework-skills.md). Check the active Codex skill inventory, reuse the separately installed official skills and load those required for this task. Missing skills must be installed through the supported host flow within setup authorization; this plugin does not bundle or automatically install them. Keep this instruction-level check distinct from CLI `doctor` and the native runtime profile.

## Local project entry point

Resolve the project's pinned absolute CLI first and check `--version` and `--help`.
For a new setup, read the engine version from this distribution's `pyproject.toml`
and look under `~/.codex/runtimes/aidp-agent-flow/<engine-version>/`
(`Scripts/aidp-agent-flow.exe` on Windows, `bin/aidp-agent-flow` on Unix);
verify it rather than assuming it exists.
A bare command on PATH may still select an older campaign's engine. Do not replace
it or silently switch an existing campaign; follow the documented adoption check.
If the selected CLI is not installed, use the plugin's
documented explicit versioned environment installation; do not run an upstream installer.
For a new project, `project init --path <new-directory> --name "Agent name"`
creates a modular starter and its uv environment. `--no-sync` prepares only files.
For an existing project, `project adopt` adds configuration without rewriting
the agent; reuse its current bootstrap when available. Run offline `doctor`
before any live check. Read [the executable contract](../aidp-agent-flow-langgraph/references/local-development.md)
for exact flags, factory interface and limits. The helper supports a single-file
or modular existing factory; it does not reconstruct business logic automatically.
Run `runtime check --require-profile` to check the actual local LangGraph against
the selected target profile. New projects use the observed managed 1.2.4 profile;
retain an explicit historical profile when that is the verified target. Before native acceptance, read
[runtime compatibility](../aidp-agent-flow-langgraph/references/runtime-compatibility.md)
to compare candidate-bound TEST/PROD observations. Unknown hosted versions remain
unknown; the plugin does not certify Oracle compatibility or upgrade managed packages.
Read [model selection](../aidp-agent-flow-langgraph/references/model-selection.md)
before choosing a model; inventory the selected region and compare requirements.

## Establish the target

Before choosing a new layout or reorganizing an adopted agent, read
[agent structure and maintainable prompts](../aidp-agent-flow-langgraph/references/agent-structure.md).
The starter is already modular; diagnose the actual authoring/package/entry boundary
before recommending another structure or a self-contained export.

Read the repository's guidance and existing environment scripts before changing
anything. Identify its dependency/lock files, supported interpreter, CLI/helper,
protected auth context, API generation, region, platform/workspace and intended
development agent. Reuse established project values and discover missing
non-secret context from approved local configuration or supported read-only
queries. Ask only for unresolved choices that affect the target or access.

Inspect the separately installed official Oracle Workbench Engineer Agent's
version and compatibility guidance before using its execution skills. Discover
the installed names; do not assume Claude hooks, a plugin-root environment
variable or a globally installed CLI. If the plugin is absent, use a verified
supported project/API route when available; do not silently install a plugin.

## Prepare the local toolchain when needed

Prefer the repository's documented bootstrap and lockfile workflow. For the
Migration Workbench Python 3.11/uv repository, this may be
`scripts/bootstrap-dev.ps1` and `uv run`; use those only when they actually exist
and apply to the target project. Another agent repository may use a different
interpreter, environment and dependency contract. Do not copy `uv sync`,
`codex-oci doctor` or migration manifests into an unrelated project by assumption.
The new CLI is a reusable option when the existing project lacks this setup.

First check installed command help/version and the existing environment. Missing
commands are readiness failures, not reasons to invent wrappers or install
global packages. Prepare or repair the local environment within the requested
setup scope using its maintained scripts. Recreate an environment only when
needed and authorized; preserve existing files and unrelated runtime users.

Keep local authoring dependencies distinct from packages managed by AIDP AI
Compute. Inspect the actual native runtime versions at an authorized test step;
a local import/version check cannot establish hosted compatibility. Never upgrade
LangGraph, LangChain or aidputils on managed compute to match generic examples.
No extra tracing service, persistence database or evaluation framework is needed
to complete this bootstrap.

## Verify access and native TEST readiness

Separate offline readiness from authenticated checks. Use the existing protected
OCI config/profile or session and supported secret references; preserve its
authentication mode. Follow the owning repository's `.oci/` convention where
defined. Do not relocate keys, repair global permissions, print tokens, copy
credentials into command arguments, or commit auth/session artifacts.

When a live read is within scope, use the installed verified CLI/project helper
to inspect the selected workspace and development agent. Verify entry/dependency
paths, compute attachment/state, configured model/tool references and existing
production identity. Reuse compatible resources; this bootstrap does not create
compute, tables, workflows, agents or credential-store entries. A missing target
is an explicit follow-on setup action, not a silent provisioning fallback.

Validate operation contracts separately: file read/write, status, traces,
native TEST refresh/invocation and production deployment can have different
support. Use actual help/API schemas and target response shapes. A wrapper
installation does not mean it implements agent commands. One bounded capability
check is enough to identify a missing automation route; record it and use the
supported UI for that operation, then return to CLI where verified.

Use [Credential Store](../aidp-runtime-credentials/SKILL.md) when setup requires
an approved runtime credential; inspecting a plan is separate from `--apply`.
Preserve a matching shared runtime credential instead of rotating it.

Avoid an agent invocation, paid tool call, SQL scratch notebook or compute start
merely to check authentication. Native invocations belong to the scoped TEST
cycle, with the existing cost limits and uncertain-start reconciliation. If the
auth session has expired, use the established login/refresh flow; do not change
credentials or repeatedly retry forbidden requests.

## Handoff

Record a concise readiness result in the existing project record: source and
environment revision, supported local/native versions, verified CLI operations,
target ownership, offline/live checks actually performed, limitations and next
step. Keep restricted identifiers in the project's protected context. Missing
native access is a blocker for integration acceptance, not for unrelated local
tests. An available TEST target does not mean the candidate passed TEST.

Continue with [AIDP Agent Flow LangGraph](../aidp-agent-flow-langgraph/SKILL.md)
for the edit/test lifecycle and [layered evaluation](../aidp-langgraph-test/SKILL.md)
for a failing behavior or acceptance design. Preserve the project's one checklist.
Required native TEST closure, authorized production publication and Agent Hub
acceptance are separate gates.

For a single-agent layout already scoped by its product root, recommend a thin
`agents/agent.py` entry with `agents/core/` as the importable package. Reuse suitable
existing modules and follow the structure reference for versioned migrations.
