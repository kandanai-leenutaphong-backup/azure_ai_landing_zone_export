# Azure LLM Compatibility Retired

Project context: [customer-service-multi-agent](../../instructions/customer-service-multi-agent.instructions.md).
This is an imported retirement notice, not an installable skill or this app's dependency
decision. The two template hosts, migration record and `libraries/` replacement are absent
here. No local compatibility, provider behavior or test receipt follows from that history.

B03 removes this runtime, package metadata/lock and raw Responses compatibility tests.
The source-workspace template hosts used `libraries/llm-interface/CONTRACT.md` and OpenAI 3.13.x.
There is no compatibility import, provider-ID continuation, raw SDK escape hatch or second
tool loop. Native Agent Framework owns invocation and semantic run events.

Credentials are explicit and borrowed; model calls default denied. Hosts supply exact tool
schemas, authorizers and authenticated session owners. Interrupted sessions do not replay.
Historical campaign records and receipts remain unchanged, not reinterpreted or re-certified.

Imported rationale, unavailable here: `libraries/azure-data-connectors/MIGRATION_B02_B03.md`.
Live inference, provider compatibility and deployed identity remain separately unverified.
