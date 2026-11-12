# AIDP Agent Flow LangGraph

Codex plugin **0.4.46**, with CLI/evaluator **0.4.31**, for developing Oracle AIDP
LangGraph agents through local implementation, native TEST, authorized
publication and Agent Hub acceptance. The technical identity remains
`langchain-skills-codex`. This is an independent integration.

## Develop an agent through natural language

Describe the business question, allowed sources, expected result and constraints.
Ask Codex to use this plugin to prepare the environment, implement a working
agent, test its behavior and diagnose failures. The user supplies business
choices, protected access and authorization for external effects.

## Skills and prerequisites

This package supplies four AIDP skills:

| Need | Entry point |
| --- | --- |
| Prepare environment and check framework skills | [Bootstrap](skills/aidp-agent-bootstrap/SKILL.md) |
| Implement and improve the agent | [Agent Flow LangGraph](skills/aidp-agent-flow-langgraph/SKILL.md) |
| Evaluate nodes, paths and behavior | [Agent Flow Test](skills/aidp-langgraph-test/SKILL.md) |
| Inspect and prepare runtime credential bindings | [Credential Store](skills/aidp-runtime-credentials/SKILL.md) |

Install framework skills separately from the
[official LangChain repository](https://github.com/langchain-ai/langchain-skills).
Bootstrap follows the [framework skills prerequisite](skills/aidp-agent-bootstrap/references/framework-skills.md)
to check the active Codex session and load the relevant instructions. Reuse an
existing verified installation; do not duplicate skills. Installing this plugin
does not automatically install other skills, Python libraries or cloud resources.

## Executable and workflow

Install the CLI in an explicitly versioned environment using
[command setup](skills/aidp-agent-flow-langgraph/references/local-development.md#command-setup-and-scope).
Check the selected absolute executable with `--version` and `--help`. Keep the
agent's local environment separate from the CLI and AIDP-managed libraries.

1. Define business cases and acceptance criteria.
2. Prepare the environment and verify local/native compatibility.
3. Implement the portable graph and test the smallest affected node or path.
4. Review answers, decisions, sources and errors; calibrate a judge if used.
5. Verify the same package and required integrations in native TEST.
6. Publish within the established authorization, verify Registry identity and
   test a real conversation in Agent Hub when that is the requested destination.

| Contract | Guide |
| --- | --- |
| Candidate and requirement evidence | [Node progress](skills/aidp-agent-flow-langgraph/references/node-progress.md) |
| Attempts, usage limits and uncertain effects | [Campaigns](skills/aidp-agent-flow-langgraph/references/campaigns.md) |
| Runtime profiles and managed dependency boundaries | [Compatibility](skills/aidp-agent-flow-langgraph/references/runtime-compatibility.md) |
| Claims, coverage and evaluator calibration | [Semantic quality](skills/aidp-langgraph-test/references/semantic-quality.md) |
| Files, TEST, sessions and publication | [Native CLI](skills/aidp-agent-flow-langgraph/references/native-cli.md) |
| Registration and client availability | [Registry and Agent Hub](skills/aidp-agent-flow-langgraph/references/registry.md) |

A local fixture pass does not certify a live model or native integration. TEST,
publication, registration and useful client responses have separate evidence.
An uncertain operation must be reconciled before retrying its external effects.
No universal similarity percentage grants quality acceptance.

## Updates and licensing

Keep a campaign's executable stable while measuring it. Adopt a changed engine
through its documented campaign inspection route. Updated skills may require a
fresh Codex session; they do not upgrade managed AIDP libraries.

[MIT](LICENSE). Existing copyright notices are retained. See
[third-party notices](THIRD_PARTY_NOTICES.md) for origin and trademark information.
No credentials, private corpus or customer deployment records belong in this package.
