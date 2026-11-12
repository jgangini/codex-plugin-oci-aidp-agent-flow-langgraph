# Official framework skills prerequisite

This plugin supplies four AIDP skills and its CLI. Framework instructions come
from the separately installed [official LangChain skills](https://github.com/langchain-ai/langchain-skills).
Do not copy those skills into this package or a generated agent artifact.

## Check the active Codex session

Before writing framework code, inspect the skills available in the current session
and read the relevant `SKILL.md` at its advertised location. A directory on disk,
a marketplace listing or a successful CLI `doctor` is not evidence that Codex
has loaded a skill. `doctor` checks the project environment, not this inventory.

| Skill name | Required when |
| --- | --- |
| `langgraph-fundamentals` | Creating or changing the LangGraph graph |
| `langchain-dependencies` | Preparing or changing framework dependencies |
| `langchain-fundamentals` | Using LangChain agents, tools or structured output |
| `langgraph-persistence` | Adding or changing checkpoints, threads or persistent memory |
| `langgraph-human-in-the-loop` | Adding or changing interrupts and human review |

Resolve by the installed skill name and location, not a hard-coded user path.
Use one verified installation of each needed skill. Do not overwrite customized
skills or silently remove another plugin. If several copies are exposed, report
the ambiguity and establish which official source is being used.

If a required skill is absent, state its exact name and the official repository.
Install only within the user's existing setup authorization using the host's
supported skill installer. Otherwise request that missing installation; continue
independent work but do not claim framework readiness. Do not invent an automatic
plugin dependency or run an upstream shell installer. After installation, use a
fresh Codex session if necessary and verify discovery again.

The [upstream installation guide](https://github.com/langchain-ai/langchain-skills#installation)
documents Codex's skill installer and `npx skills` with a Codex target. Those are
user-invoked installation routes, not startup hooks of this plugin.

## Keep framework guidance separate from runtime compatibility

Record the selected skill names, source locations and revision when available in
the project's existing readiness record. If a revision is unavailable, say so;
do not assign the removed bundled revision to an independent installation.
Do not update skills or the execution engine in the middle of a frozen campaign.

Skills contain authoring guidance; they do not install Python libraries, grant
provider access, establish cost approval or certify a managed AIDP runtime.
Preserve the selected model, supported constructors, memory owner and project
contracts. Examples using newer APIs require a check against the actual local
and native versions. Follow [runtime compatibility](../../aidp-agent-flow-langgraph/references/runtime-compatibility.md)
before choosing dependency pins; never upgrade managed AIDP libraries to fit a
generic example. These AIDP checks still apply when all official skills are present.
