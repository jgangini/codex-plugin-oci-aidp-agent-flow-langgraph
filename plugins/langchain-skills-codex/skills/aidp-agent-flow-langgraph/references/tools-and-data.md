# MCP, retrieval, tables and graph state

Choose integrations from the agent's actual behavior. A model-only classifier
may need none of MCP, RAG or application tables. A retrieval agent may use a
single existing repository without needing a new database. Keep the owning
project's factory, approved central metadata identity and current credentials
as the integration contract. This plugin supplies recorded-result tests and
guidance; live clients and data access remain project-owned.

## Keep the responsibilities separate

| Concern | Maintained owner and purpose | Test boundary |
|---|---|---|
| Graph state/checkpoints | LangGraph or AIDP runtime; conversation state, routing and resume position | Fresh local checkpointer and thread; native continuity/isolation checked separately |
| Long-term memory | Existing managed memory/store; approved user or cross-session facts | Verify identity scope, retention and retrieval; preserve the configured owner |
| Application tables | Existing catalog/schema/table or operational database; business records and authoritative central metadata | Approved query/repository adapter and least-privileged identity |
| Evidence index/knowledge base | Existing retrieval repository; source documents, chunks, embeddings and freshness | Retrieval contract, source attribution, access filters and empty/stale evidence |
| Operation ledger | Existing idempotency/budget owner; submitted, uncertain and reconciled effects | Resume/retry behavior without duplicate external effects |
| Test records | Reviewed frozen inputs/results; repeatable tool and reasoning checks | Local replay, no service connection and no freshness assertion |

LangGraph checkpointers retain thread-scoped graph state; stores hold
application-defined data across threads. An in-memory checkpointer does not
survive a process restart. These facilities do not decide ownership of a
business table or replace the project's authorization model.
[LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence).

Read [Oracle memory and framework boundaries](oracle-memory-and-frameworks.md)
before changing managed conversation memory. Do not add checkpoint tables,
application tables, a vector index or a second metadata database merely to
enable a local test. Do not use a graph checkpoint as proof that a timed-out
external write or paid operation did not start.

## Recorded services in local cases

The local worker supplies `runtime["services"]` to the project factory. Tool
nodes can close over that dependency and call it asynchronously:

```python
async def retrieve_node(state):
    evidence = await runtime["services"].call(
        "rag", "approved_policy_repository",
        {"query": state["question"], "limit": 3},
    )
    return {"evidence": evidence}
```

The enclosing project factory owns graph construction; the snippet defines a
node inside that factory. A local test case carries `service_records` outside
the graph's `input`, alongside assertions and optional `model_responses`:

```json
{
  "id": "empty-evidence",
  "input": {"question": "What policy supports this request?"},
  "service_records": [
    {
      "kind": "rag",
      "name": "approved_policy_repository",
      "arguments": {"query": "What policy supports this request?", "limit": 3},
      "result": {"chunks": []}
    }
  ],
  "model_responses": ["No supporting evidence was found."],
  "assertions": [
    {"path": "answer", "equals": "No supporting evidence was found."}
  ]
}
```

The factory's graph determines whether this case is applicable. Keep expected
answers and reference labels outside graph/model input. Record only authorized,
reviewed data; fixtures can contain sensitive business content even though the
replay adapter's call metadata omits arguments and results.

The public adapter is `RecordedServices(records)` in
`scripts/aidp_agent_flow/services.py`:

- `await call(kind, name, arguments)` matches one unconsumed record exactly.
  Kinds are `mcp`, `rag` or `table`; names use 1–128 ASCII letters, digits,
  underscores, dots or hyphens; arguments are plain JSON objects.
- JSON object key order is ignored. Types, array order, parameter values,
  service kind and name remain significant. Repeated identical calls require
  repeated records, consumed in fixture order. Concurrent calls on one event
  loop cannot consume the same record. Use a fresh adapter for each graph run;
  sharing one instance between event loops is refused.
- `calls` returns a metadata snapshot containing `kind`, `name`, `status` and
  `record_index`. It does not expose argument/result payloads or raw provider
  errors. `assert_consumed()` fails when expected calls never occurred.
- A record requires exactly one `result` or `error`. `null`, `false`, `0`, `[]`,
  `{}` and an empty string are valid successful results, not unavailable data.
  Errors use `"error": {"code": "nonsecret_identifier"}` with an optional
  message that is never emitted. They are consumed once and raise a sanitized
  `ServiceError`, which is also a `FlowError`. No retry or live fallback occurs.
- Bounds are 1,000 records, 1,000 call-metadata entries, 1 MiB canonical JSON per
  record/call argument, 8 MiB total fixture size, 32 nesting levels and 100,000
  JSON value nodes per payload. Non-JSON objects, cycles, nonfinite numbers and
  malformed records fail before replay.

The adapter returns the supplied JSON result without interpreting arbitrary
business fields. Normalize actual provider errors into the explicit fixture
`error` envelope when capturing a case. For MCP this includes distinguishing
JSON-RPC errors from a tool result with `isError: true`; a raw result containing
that field is otherwise just recorded data. A successful empty response stays
a result. The owning live adapter must validate the actual tool's input/output
schema; replay's generic JSON checks do not provide that validation.
[MCP tools and errors](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

The replay adapter performs no network access, database queries, imports from
fixture strings or arbitrary code execution. It treats a SQL-looking string as
data. Project code can still bypass the supplied adapter, so
`external_effects_allowed: false` is a factory contract, not an OS network
sandbox. Review the factory's dependencies when claiming an offline run.

## Real integration contracts

Keep a small project-owned adapter at the same node boundary. Reuse an existing
client/repository rather than creating a generic MCP transport, SQL execution
layer or retrieval stack in the plugin. Preserve approved service endpoints,
catalog/schema/table names, central metadata keys, credential references and
tenant/user scoping. A logical fixture name is an alias for that existing
mapping, not permission to create a replacement resource.

| Integration | Verify in the owning project before an authorized live check |
|---|---|
| MCP | Approved server and client lifecycle/transport; discovered tool identity and current schemas; credentials and authorization; input/output validation; normalized protocol/tool errors; bounded timeout/output and effect classification |
| RAG | Approved repository or knowledge base; source/index identity and freshness; query/filter contract; tenant/document access filters; top-k/size limits; chunk IDs and source citations; explicit no-match/error distinction |
| AIDP tables | Actual catalog type, schema/table/view and approved central metadata identity; existing validator/query ID/repository; parameter binding; runtime data permissions; row/time limits and authorized side effects |

Oracle's documented SQL tool currently executes predefined parameterized queries
against external catalogs and excludes standard-catalog data. It is not an
NL2SQL interface. Verify the actual catalog and preserve the project's
supported adapter for standard-catalog tables rather than assuming SQLTool
can access them. Oracle also documents `MCPTool` and `RAGTool` integration
through its existing tool configuration.
[Oracle agent tools](https://docs.oracle.com/en/cloud/paas/ai-data-platform/aidug/agent-flow-tools.html).

For model-generated SQL, narrow actual database permissions and retain the
project's catalog/query validator. Parameterized approved queries are preferable
when the use case is fixed. A `startswith("SELECT")` check is not an authorization
boundary. Do not infer read-only safety from a prompt or hide schema discovery,
database writes, compute startup or retry costs inside a test helper.
[LangChain SQL agent guidance](https://docs.langchain.com/oss/python/langchain/sql-agent).

## Isolate the failing behavior

### Compose calls in maintained code; evaluate Code Mode selectively

For a known workflow, keep pagination, filtering, deduplication and bounded
composition in reviewed tool/node code when this avoids sending intermediate
payloads through the model. Preserve source IDs, citations, partial failures and
the operation ledger; do not discard evidence merely to reduce context.

Cloudflare's Code Mode is a different execution pattern: the model generates
code against APIs derived from MCP schemas, then an isolated runtime executes
that code. Consider it for dynamic sequences of many calls only when a measured
test shows value over direct tools or maintained composition. It is not required
by MCP or LangGraph, and fewer model round trips do not by themselves establish
better task success. [Cloudflare Code Mode](https://blog.cloudflare.com/code-mode/).

This plugin does not implement that generated-code runtime. Its local worker
runs trusted project code with the user's interpreter and environment; a
subprocess and `external_effects_allowed: false` do not isolate secrets, files or
network access. Do not execute model output with `exec`/`eval` there. A future
Code Mode integration needs an actual sandbox, narrow authorized tool bridges,
no ambient credentials, and enforced execution/output/call/cost limits. Compare
task success, evidence coverage, calls, tokens, failures and external effects on
the same cases before adopting it. Retain MCP schema validation and permissions
at the tool boundary.

### Test the affected boundary before integration

1. Exercise the affected tool node with recorded success, empty result,
   normalized failure and relevant authorization/filter boundary cases.
   Check routing and state updates without a model call when possible.
2. Freeze relevant MCP/RAG/table results and test the reasoning node with a
   fixture model. For a model behavior question, run only the selected case
   with `--real`; this switches the model adapter while services remain
   recorded. Keep model limits and independent expected assertions. It does
   not establish current retrieval quality or live database permissions.
3. Run the relevant partial/full graph to check orchestration, repeated calls,
   fallback and resume behavior. Supply only records expected for that path;
   unconsumed records and unmatched calls reveal an incorrect test boundary.
   A node-only test bypasses graph/checkpointer semantics.
4. When the actual integration needs verification and authorization covers it,
   use the owning project's approved live adapter and native TEST target.
   Record the served revision, actual service/table/index identity, permissions
   and response contract. Keep uncertain external effects in their operation
   ledger. Local replay, a real-model response, native TEST and production
   publication remain separate outcomes.

Reviewed against the linked primary documentation on 2026-11-02. The implemented
feature here is bounded local replay; no live MCP/RAG/table adapter or hosted
integration acceptance is supplied by this guide.
