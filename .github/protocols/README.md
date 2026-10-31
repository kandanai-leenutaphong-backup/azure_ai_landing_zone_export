# Protocols

Each `protocols/<name>/SKILL.md` owns its metadata and complete authored procedure. There are no
generated wrappers or separate top-level procedure files. Edit the owning `SKILL.md` directly.

All nine protocols are listed below and in [catalogue.json](catalogue.json). A protocol is an
execution procedure; domain skills supply reusable implementation or knowledge. The catalogue
returns the complete procedure's path. Automatic client discovery depends on client configuration.

| Protocol | Use When | Outcome |
| --- | --- | --- |
| [Capability-first modularization](protocol-capability-modularization/SKILL.md) | A named area has disordered ownership, duplicated behavior or scattered backend/frontend responsibilities | Functional capability catalogue, shared foundations with real consumers, preserved vertical workflows and measured cleanup |
| [Demonstrate](protocol-demonstrate/SKILL.md) | A requested result must be demonstrated as a real user journey | Requirement-to-observation table and reproducible walkthrough |
| [Document](protocol-document/SKILL.md) | A comprehensive documentation sweep is explicitly requested | Verified coverage inventory and corrected owning documentation |
| [Foundry agent lifecycle](protocol-foundry-agent-lifecycle/SKILL.md) | An agent package must be hosted on Foundry, verified, evaluated, optimized, redeployed and re-verified | Retained receipts per step, selected or baseline version live, baseline kept as restore target |
| [Garbage collect](protocol-garbage-collect/SKILL.md) | Dead code or abandoned files are suspected in one named area | Reachability evidence and one authorized deletion batch |
| [Lean](protocol-lean/SKILL.md) | Weight spans docs, code, dependencies, CI or infrastructure | Cost-ordered verdicts and measured, authorized cleanup |
| [Regression loop](protocol-regression-loop/SKILL.md) | A change needs repeatable acceptance against the actual artifact | Fixed acceptance command and observed pass or named blocker |
| [Restructure](protocol-restructure/SKILL.md) | A working legacy area must change shape to absorb named work | Salvage map, reversible migration and verified replacement |
| [Template an application](protocol-template-app/SKILL.md) | A customer-specific app must become a reusable accelerator | Destination-only sanitized migration, preserved public inputs, explicit extension points and clean-copy acceptance |

The [architecture principles](../instructions/architecture-principles.instructions.md) govern
placement and reuse. A protocol supplies an execution method; it does not expand the user's scope
or grant permission to delete, deploy, alter access, or overwrite another writer's work.

Use the smallest applicable procedure. User scope and the [work contract](../instructions/work-contract.instructions.md)
control authorization and verification. Protocols do not require a particular agent persona,
ticket, notebook, commit, or cloud deployment. References to repository tools apply when those
tools are installed; otherwise use the project's equivalent and state what was not checked.
Preserve reusable findings in an existing record only when rediscovery would cost more.