# Agent structure and maintainable prompts

Read before diagnosing agent layout, introducing a packaging transformation, or
reorganizing code/prompts. Apply this to the project's actual runtime and accepted
requirements; it is design guidance, not a new scaffold, certification or release gate.

## Establish what actually runs

Trace the authoring source, local factory, native entry/dependency files, build
transformations, uploaded files and served candidate. Identify which files an edit
changes at runtime. Distinguish a generated export from maintained source. Publishing
both a self-contained generated entry and apparently editable modules can mislead
operators when only the generated entry executes; report that concrete divergence.

Read current consumers before moving paths: native descriptors, resource loading,
package inventories, hashes, hooks, update journals and rollback. Repeated directory
names can represent different boundaries; they are not a correctness defect by
themselves. Simplify redundant levels when they do not serve an actual deployment or
Python-package boundary. Preserve meaningful separation for multiple agents.

The included starter already uses a small entry plus ordinary Python modules in
`core/`; it does not require an AST flattener or a prompt JSON catalog. Do not attribute
an existing application's packaging decisions to the starter without tracing them.

## Choose the smallest executable layout

For a single agent, prefer a thin platform entry and one importable application
package below the entry folder. An illustrative deployment is:

```text
<product>/
  <private-control>/             # outside the packaged agent subtree
  agents/                       # entry folder for this single agent
    agent.py                    # platform setup/invoke adapter
    requirements.txt
    core/
      __init__.py
      native.py
      graph.py
      state.py
      services.py
      memory.py
      decisions/                # introduce only for cohesive responsibilities
        understand.py
        report.py
      runtime.json              # nonsecret per-candidate configuration, if used
```

Use `core/` as this plugin's default Python package convention, aligned with its
starter. This is not a directory name required by Oracle or LangGraph. Keep one
agent folder boundary: for a single agent already under a product root, prefer
`agents/agent.py` and `agents/core/` rather than repeating the product name.
Do not install a generic `core` package globally or reuse another agent's cached
`core` imports; verify module origins inside the candidate in a clean process.
Existing useful names and grouping remain project decisions. Reuse suitable current modules; do not
create a repository/service/controller layer, one class per node, or a folder per
prompt merely to match the example. Keep graph construction and routing visible;
isolate model/tool/persistence adapters sufficiently to inject them in focused tests.
Do not add a web server, LangSmith deployment or `langgraph.json` to an AIDP-only project.

Oracle documents that Playground and deployed agents package the entry file's
folder and subfolders, excluding parent/sibling workspace folders. Keep executable
modules and required resources inside that boundary. Use ordinary imports and
package-relative resources, not hard-coded workspace paths. Test imports in a clean
process outside the checkout so an authoring copy cannot mask an incomplete package.
Moving the entry directory upward can accidentally include private control files;
inspect the exact package inventory before upload.

Prefer executing the same modular sources locally and natively. A single-file export
is an optional compatibility artifact when a verified target needs it. Keep it clearly
generated, reproducible and separate from ordinary editing; test the exported path
as well. Do not flatten modules by default or equate fewer files with simpler code.

## Keep instructions readable beside their consumer

Choose a prompt representation for the people who edit it:

- For code-owned decision instructions, prefer named multiline Python constants
  beside the decision function and its schema/normalization imports. Keep stable
  decision IDs for telemetry, evaluation and effect ledgers. The shared model adapter
  should own provider invocation and structured-output handling, not business policy.
- A small `prompts.py` is suitable for shared text or an intermediate extraction;
  avoid replacing one large catalog with an equally opaque string registry. Extract
  cohesive decisions when that removes repeated navigation between prompt and code.
- Markdown/text resources suit long editorial content or non-code authors. Package
  them explicitly, use fixed trusted resource names and load at initialization or a
  bounded cache boundary. Preserve injected prompt overrides where the project uses them.
- JSON remains appropriate for structured configuration or externally managed prompt
  catalogs. Do not declare it universally wrong. Check the actual load path before
  alleging per-call parsing; editorial difficulty and runtime overhead are different facts.

Preserve prompt content exactly during a structural migration. Compare the effective
strings, decision IDs and schemas before changing reasoning behavior. Keep runtime
state as raw task/evidence data; format model inputs at the node boundary. Missing
instructions/resources should fail readiness rather than silently become empty text.
Retain authentication, bounded input handling and evidence-as-untrusted-data controls.

Follow the project's formatter and Python conventions: normal spacing, readable
multiline expressions, short helpers with concrete responsibilities and useful types
at boundaries. Do not compress statements onto lines or impose an arbitrary file-size
threshold. Adding formatting tools or dependencies requires a separate justified change.

## Migrate identity and recovery together

A modular candidate's identity must cover every executed module and required prompt,
configuration and dependency resource, not just its thin entry. Define a deterministic
relative-path/hash inventory; avoid self-referential manifest hashes. Exclude secrets,
private control receipts, caches and unrelated files. Verify import origins/readback
and bind native evidence to the actual served candidate. A package manifest or a
metadata version response alone does not establish which code executed.

Version layout changes when existing installations depend on old paths. Preserve
their inventory, resource identities and pending-operation bindings for Resume and
rollback. Review both the old and new descriptor/entry/dependency paths, backups,
runtime configuration and publication boundary. Do not rebuild an empty receipt or
adopt foreign files to get past an old-layout guard. Keep active campaigns on their
pinned executor; changing these guides does not reset evidence, spend or recovery state.

Use the existing validation workflow: clean-package import, resource presence, prompt
equivalence, a deliberate module/prompt mutation rejected by the fingerprint, graph
and checkpoint/stream regressions, and interrupted update/rollback between layouts.
Then perform affected native TEST on the served revision. A structural refactor pass
does not prove a useful research answer; assess that separately against the real case.

## Sources and limits

Verified 2026-11-07. These sources support the boundaries and patterns; they do not
mandate these exact folder names or certify a particular agent:

- [Oracle Agent Creation](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-creation.html):
  setup/invoke entry, dependencies, entry-folder packaging and relative resources;
  currently documents LangGraph 1.0.1. Verify used APIs against that project version.
- [LangGraph application structure](https://docs.langchain.com/oss/python/langgraph/application-structure):
  ordinary package/graph/state/tool separation. Its deployment configuration examples
  target LangSmith; do not transplant that platform into AIDP.
- [Thinking in the Graph API](https://docs.langchain.com/oss/python/langgraph/thinking-in-graph-api):
  explicit nodes/transitions, raw state and prompt formatting at consumption.
- [Python 3.11 modules](https://docs.python.org/3.11/tutorial/modules.html),
  [package resources](https://docs.python.org/3.11/library/importlib.resources.html),
  and [PEP 8](https://peps.python.org/pep-0008/): modular imports/resources and readable style.
- [LangGraph testing](https://docs.langchain.com/oss/python/langgraph/test): isolated
  graph/checkpoint tests and partial execution; local tests do not certify Oracle memory.

The layout, prompt-colocation preference and migration checklist above are adaptation
guidance based on those boundaries. They are not an executable architecture scanner
or a new upstream/Oracle requirement.

## Diagnostic acceptance for this convention

- Identify the actual entry, package root and imported module origins.
- Confirm every editable module and resource reaches the served candidate.
- Bind acceptance to all executable bytes, configuration and dependencies;
  exclude the inventory manifest from its own hash and version the identity.
- Prove a changed module or prompt invalidates acceptance, even if the entry
  is unchanged. Preserve effective prompt text during structural migration.
- Verify native path-rebinding and file-removal contracts before automating
  an existing installation migration. Do not infer those operations from
  create/sync support or overwrite old receipts with a new layout. Preserve
  complete backups and use the recorded layout for recovery.
