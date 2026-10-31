# Agentcraft Framework

One public composition and discovery surface over canonical capabilities. The framework
does not contain another data client, model loop, authorization system or lifecycle engine.
`appcompose` validates the dependency graph and owns startup/shutdown.

## Offline Workflow

Run [the installed example](src/agentcraft/examples.py): native async `azdata` queries ->
`situation_detector` observations -> one native `llm_interface` structured response ->
`workrecovery` preservation, uncertain-save read-back and verified recovery. Every result
feeds the next operation. No custom model loop, copied capability implementation or
source-path injection is used.

**SYNTHETIC ONLY:** HTTP responses, credential tokens and readings are fixtures. Real
public operations and SDK parsing run; no network, model service, cloud or user data is
accessed. Temporary filesystem writes are real. This is not live provider acceptance.

### Install And Run

Requires Python 3.12+ and `agentcraft[data,models,recovery,optimization]==0.1.0`.
`optimization` explicitly includes `situation-detector`; no
optimization run is performed. `models` supplies the native OpenAI provider. Installing
extras grants neither data access nor inference. Identity/inventory profiles are not
needed for this task.

Outside the checkout, use a reviewed, complete local wheelhouse. Set `CONSUMER_ENV` to
an absolute fresh environment path and `WHEELHOUSE` to the absolute directory containing
the final framework, member and dependency wheels. No registry fallback:

```bash
uv venv --offline --python 3.12 "$CONSUMER_ENV"
uv pip install --python "$CONSUMER_ENV/bin/python" --offline --no-index \
    --find-links "$WHEELHOUSE" 'agentcraft[data,models,recovery,optimization]==0.1.0'
cd /tmp
"$CONSUMER_ENV/bin/python" -I -B -m agentcraft.examples
```

For source development, complete [workspace installation](../../../../libraries/README.md#installation)
with `data`, `models`, `recovery` and `optimization`, then use that explicit environment:

```bash
"$UV_PROJECT_ENVIRONMENT/bin/python" -B -m agentcraft.examples
```

Callable from an existing async application, with the same extras installed:

```python
from agentcraft.examples import offline_workflow

result = await offline_workflow()
assert result["recovery"]["verified"]
```

The callable accepts no target, credential, path or user payload. It returns an inspectable
dictionary; the module command prints that dictionary as JSON.

### Inspect Results

| Report field | Expected observation |
| --- | --- |
| `requests` | `data: 2`, `model: 1`; negative probes add no HTTP requests |
| `rules` | Declaration order `all_readings`, `high_readings`; ordered native rows `(1, 2)`, `(2, 7)`; matches `[1, 2]`, `[2]` |
| `configuration_digest` | Digest produced by the real rule battery |
| `model` | Structured counts `[2, 1]`, terminal `completed`, shared run ID |
| `budget.reserved` | `data_calls: 2`, `model_calls: 1`, `store_calls: 5` in one `ExecutionContext` |
| `budget.unknown` | Two timed-out store attempts remain unknown; successful read-back does not refund them |
| `recovery` | `unknown` -> `saved` -> repeated `saved`; one destination write, verified bytes, zero pending artifacts |
| `closed` | Framework/data/model closed; each separately owned synthetic identity/HTTP resource closed once |
| `temporary_files_removed` | `true`; only this invocation's synthetic temporary directory was removed |

Rule callbacks reject partial/failed queries before processing. The model receives actual
observations, not a parallel canned prompt; native structured output and terminal completion
are inspected before saving. The host's store callbacks reserve before every save/read-back
and check the same deadline. Native data/model calls reserve at their existing owners.
This is process-local attempt accounting, not a wall-clock filesystem interrupt, a bound
on pure rule processing, or a billing quota.

### Refusal And Recovery

- Data without a query grant returns `denied` / `operation_not_granted`; model inference
    without its grant raises `LlmError` with `model_calls_denied`. Neither acquires a token.
- Exhausting the shared budget yields data `denied` / `budget_exhausted` and model
    `LlmError` with `budget_exhausted`, category `denied`, field `model_calls`. No extra
    request is sent; data refusal item effects remain `none`.
- Partial native data becomes `RuleExecutionError`, stage `execute`, code `callback_failed`,
    never an empty successful rule. Incomplete model output raises `LlmError` with
    `summary_not_completed` before recovery staging.
- The host's tiny synthetic destination adapter uses actual `ArtifactStore` atomic
    no-clobber writes and digest-verified reads in a second temporary directory. Its first
    save lands then raises `StoreTimeout`; the unreadable read-back leaves state `unknown`
    and preserves the completed payload in the separate recovery root.
- A fresh `RecoverableJobs` instance reads that preserved payload. An overwrite attempt
    raises `ArtifactExists` without changing it. Restoring only the synthetic read-back
    allows `recommit` to verify the already-stored bytes. Repeating `commit` with identical
    output performs no second destination write or computation. Pending artifacts disappear
    only after verified read-back. This is instance reopening, not a process-restart test.

The example owns all fixture paths. `Framework` owns the connectors/model plus their
separately bound synthetic credential and borrowed transports. Recovery handles perform
short filesystem operations and require no close hook. Socket connect/connect_ex and DNS
are blocked with scoped standard-library mocks, restored on exit. Those mocks are
process-global: run this demonstration alone, never concurrently with live application
work. Synthetic temporary fixtures are cleaned even when the demonstration fails; never
apply that cleanup rule to a production recovery root or pending user output.

### Verification

```bash
"$UV_PROJECT_ENVIRONMENT/bin/python" -B -m unittest discover \
    -s .github/skills/harness-guide/framework/tests -p test_example.py -v
```

Five focused tests cover changed native rows propagating through every handoff, grant and
budget refusals, partial-query failure, incomplete-model refusal without saved artifacts,
repeatability, owned cleanup, and module execution outside the checkout. The
[release-candidate receipt](distribution/release-candidate.json) records current artifact
hashes, non-editable installation and remaining gates; a source test alone is not an
artifact pass. Publication and live authorization are separate.

**HISTORY, recorded artifact:** Linux/Python 3.12.3 with uv 0.9.30; all 16 Python
wheel/sdist pairs rebuild equivalently; base and combined profiles install from the
complete offline wheelhouse; 49 framework plus 2 core installed tests pass, including
the workflow and real SDK MCP checks. The actual `agentcraft mcp --offline` command
also passes SDK success/refusal and process cleanup. Exact final identities and paths
belong to the receipt. Later source, documentation and generated-guidance changes are
not certified by those hashes. The [independent reader](distribution/independent-reader.json)
passed three offline tasks; the client example below resolves its recorded gap.
[Native client closeout](distribution/native-client-closeout.json) and
[external-export acceptance](distribution/guidance-dedup.json) subsequently passed the
actual CLI installation/discovery/disable/cleanup gate. CLI 1.0.83 accepted malformed
root manifests in earlier probes; strict first-party `--check` and hash validation remain
mandatory. Those failures are preserved, not relabeled as native validation passes.

[Conformance](CONFORMANCE.md#remaining-gates) owns remaining artifact, platform and live
requirements. Ontology and Investigation evidence belongs to the
[application migration record](../../../../template_apps/investigation_app/docs/LIBRARY_MIGRATION.md).
No setup, full suite, build or live command was rerun for this documentation revision;
the listed source example and prior artifact/reader results are reused within their scope.
The public example matched the tested installed bytes, SHA-256
`d5696584d0735451b19127519f7afb058e2d1d81e8719a05ed2a5fbe715782d7`.
That checked environment has `agentcraft`/`agentcraft-core` 0.1.0, `azdata` 4.0.0a4,
`llm-interface`/`situation-detector` 0.1.0a1, `recoverable-jobs` 1.0.0, OpenAI 3.13.0,
Agent Framework Core 1.18.0 and MCP 1.30.0. Matching example bytes is reuse evidence,
not a rerun against every later dependency or source change.

Navigation: [knowledge task](../../../../docs/README.md#offline-data-rules-and-recovery) -> this
page -> [callable module](src/agentcraft/examples.py).

## Composition Contract

Bind real `azdata.connect(...)` and `llm_interface.connect(...)` values explicitly; their
configuration, credentials, grants and specialized requests remain typed. `app.data(name)`
and `app.model(name)` validate the bound type. Plain construction and `describe()` perform
no service call, credential acquisition, thread startup or state write.

Bindings are borrowed unless `owned=True`. Owned repeated handles close once, dependents
close before dependencies, and appcompose retains unsafe shutdown state. New access after
close refuses. Creating a run context never grants access; native capability policies are
still required. Use `ExecutionContext` for shared bounded calls, without automatic retries.

The optional MCP host loads only operator-configured bindings and installed public APIs.
Pure Python use, frontend source rendering and rule execution need no MCP or hosted service.

## Offline MCP Client

Use the same Python environment with `agentcraft[mcp]` installed. This complete native
SDK example launches only the composition fixture, validates a document, inspects a
refusal, and recovers with the valid version. It does not activate editor configuration
or bind data, models or recovery storage. Async context exit closes the child process.

```python
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agentcraft.cli", "mcp", "--offline"],
    )
    document = {"schemaVersion": 1, "kind": "portable.app-composition",
                "name": "Offline example", "members": []}
    async with asyncio.timeout(30):
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = await session.list_tools()
                refused = await session.call_tool("composition_validate", {
                    "binding": "composition",
                    "document": json.dumps({**document, "schemaVersion": 2}),
                })
                valid = await session.call_tool("composition_validate", {
                    "binding": "composition", "document": json.dumps(document),
                })
                if not refused.isError or valid.isError:
                    raise RuntimeError("Unexpected validation result")
                print(json.dumps({"tools": sorted(tool.name for tool in tools.tools),
                                  "refusal": refused.structuredContent["error"]["code"],
                                  "valid": valid.structuredContent["valid"]}))


asyncio.run(main())
```

Expected: three `composition_*` tools, refusal `unsupported_version`, and `valid: true`.
The timeout bounds this client session, not a remote-job cancellation or billing guarantee.
For configured hosts, use `agentcraft.mcp.create_server` with explicitly supplied
bindings, grants, principal and execution context; tool input cannot choose credentials
or targets. No actual plugin-client installation is claimed by this SDK example.

Missing `mcp` import: install the explicit extra into the selected owned environment;
do not activate editor registrations as a dependency fix. A refused schema is corrected
and validated again before any composition. Async context exit closes the child; retain
failed diagnostics without prompts, credentials or provider response bodies.