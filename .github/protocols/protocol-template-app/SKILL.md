---
name: protocol-template-app
description: "Migrate a customer-specific application into a reusable accelerator, preserving approved public data and workflows while excluding private data, historical state and deployment identity."
metadata:
  protocol: protocol-template-app
---

# Template An Application

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
No app export or migration is authorized by this documentation adaptation. In a separately
approved template, keep synthetic issue provenance and portable four-judge rubric contracts;
exclude project identity, private endpoints, allowlist membership and private human labels.
Never replace real human calibration labels with generated fixtures or transfer a calibrated
status without its applicable evidence. Match existing Python package policy: `uv` against
an existing interpreter, no environment creation/activation or implicit setup.

Migrate a customer-specific application into a reusable accelerator without carrying the
customer's data, operational history or deployment identity with it. Preserve working capabilities,
approved public datasets and extension points. A renamed directory is not a generalized application.

This composes [restructure](../protocol-restructure/SKILL.md),
[capability-first modularization](../protocol-capability-modularization/SKILL.md) and the
[architecture principles](../../instructions/architecture-principles.instructions.md).
It adds data provenance, destination-only sanitization and clean-room acceptance, not authority
to publish data, mutate a source repository, weaken authentication or deploy cloud resources.

## Inputs And Scope

Record the source and destination roots, source revision and uncommitted changes, intended audience,
workflows to preserve, approved public data, excluded customer identity/data and permitted local
checks. The source remains read-only unless separately authorized. Never move, delete, reset,
stage, commit or clean it as a side effect of making the destination tidy.

Resolve roots and symlinks first. Refuse overlapping source/destination roots or a destination
containing unowned work that would be overwritten. Copy from an explicit inventory, not an entire
checkout followed by hopeful deletion. Exclusions apply to the destination, including nested copies.
Do not use hard links or symlinks that let a destination edit mutate or depend on the original.

## 1. Anchor One Working Capability

Read the actual composition root and its data/configuration selector. Name one falsifiable hypothesis
about how the application can run with approved inputs, plus the cheapest existing check that could
disprove it. Run that check before making a broad migration. If a source environment is unavailable,
record the limitation and validate an isolated copy without claiming an unobserved source baseline.

Keep a short acceptance table: workflow, callable API or service, data/provider requirement,
authorization, persisted output and executable check. Include the real UI journey when there is one.
Preserve source behavior unless the requested generalization explicitly changes it.

## 2. Classify Inputs Before Copying

Use one migration inventory with path, category, provenance/license, destination, disposition and
verification. Inspect names, manifests and owning code before reading sensitive payloads.

| Category | Default Disposition |
| --- | --- |
| Application source, contracts and relevant tests | Retain; adapt customer assumptions at their owners |
| Public datasets and source assets | Retain with source URL, version/hash, license/notice and acquisition command |
| Large reproducible public downloads | Keep outside Git in destination-owned storage; preserve manifest and checksums |
| Data with uncertain provenance or redistribution rights | Label unresolved; do not describe as open-licensed or publish automatically |
| Customer raw data and all derived forms | Exclude: exports, normalized tables, graphs, indexes, screenshots, fixtures and embedded prompt examples |
| Notebooks, transcripts, experiment runs and investigation artifacts | Exclude historical state; retain only deliberately extracted, sanitized reusable knowledge |
| Secrets, credentials, tenant/resource coordinates and deployment receipts | Exclude values; retain configuration schema and fail-closed templates |
| Dependency installs, build products, caches and source Git history | Exclude; regenerate from declared dependencies and commands |
| Duplicate shared implementations or installed harness copies | Reuse the destination's canonical packages through public APIs |

Publicly downloadable does not mean freely redistributable. Keep attribution and original notices;
do not invent a license. A download recipe is not the same as retaining dataset bytes: state which
was delivered. Measure storage first. If the authorized data cannot fit or rights remain unresolved,
report the exact limitation rather than silently substituting synthetic data or omitting the corpus.

## 3. Separate Product Behavior From Customer Configuration

Catalogue useful capabilities and choose reuse, extend or keep separate for existing destination
packages. Preserve one implementation per shared rule. Keep the application composition root,
domain-specific investigation logic and data adapters in the demo; import foundations explicitly.

Trace customer coupling beyond visible branding: default source IDs, timestamps, queries, graph
vocabulary, agent prompts, rules, fixture payloads, paths, environment files, deployment names,
test expectations and documentation. Remove customer-only pipelines and dead callers together.
Replace organization-specific choices with typed configuration at the edge, not global string
replacement or placeholder values scattered through the implementation.

Provide one useful default profile backed by retained public or clearly labelled synthetic data.
Missing optional providers must report unavailable before any network call, never silently use the
source customer's endpoints. Preserve an explicitly authenticated production path. An isolated
loopback demo identity is a separate bounded adapter, not an authentication-disable switch or proof
of deployed security. Read-only tools remain read-only; model, ingestion and deployment operations
need explicit configuration and authorization.

## 4. Migrate In Runnable Batches

1. Establish the destination skeleton, input inventory and one documented entry point.
2. Copy the smallest complete workflow with its contracts, tests, assets and dependency declarations.
3. Adapt its configuration/data owner, then immediately run the focused acceptance check.
4. Reuse canonical foundations and update their real callers; remove temporary duplicate copies.
5. Add remaining workflows and approved public inputs in similarly verified batches.
6. Regenerate outputs into a destination-owned ignored runtime directory, never the source tree.

Track excluded paths and their reason instead of carrying a historical notebook or artifact archive
into the template. Keep a compact capability/extension map and migration receipt; do not add a second
project-state registry. Never replace real workflows with static screenshots or mock outcomes without
explicitly naming that changed scope.

## 5. Prove The Template

- Run setup and startup from the documented destination, then from a clean copy without source paths.
- Prove the default requires no customer's credentials, resources, data or original checkout.
- Verify retained public-data hashes, provenance and notices; distinguish local holdings from Git contents.
- Scan filenames, text and structured data stores for prohibited customer remnants. A clean text grep
  alone does not prove binary/database sanitization; build those only from approved inputs and record it.
- Run the preserved workflow tests, the real browser controls and result read-back. Include matching
  negative cases for authorization, ownership, input bounds and unavailable services.
- Exercise one real extension point with an alternate fixture/configuration, without editing core rules.
- Check source files remain unchanged and no generated/runtime output became distributable input.

Do not provision or contact original cloud resources to prove portability. Report live integrations
that remain unverified, large datasets not copied and provider/license prerequisites explicitly.

## Deliverables And Stop Condition

Deliver the runnable destination, retained-data manifest, excluded-path disposition, capability and
extension map, generic configuration/deployment templates, one-command local setup and exact observed
acceptance. The destination README states what works and what remains, not the source's historical
deployment claims. Update the parent repository's catalogue/README when adding a discoverable demo.

Stop when the preserved workflows run against approved inputs, the source is untouched, prohibited
customer/state material is absent, shared ownership is clear, and the next operator can run and
extend the accelerator from its own documentation. Generalization is measured by that result, not
file-count reduction or replacing a customer's name in a heading.

## Scope And Permissions

This document is the single procedural authority. Load only the guidance needed for the task.

Preserve the user's scope and this agent's existing permissions. Discovery does not grant
deletion, cloud mutation, credentials, commits or authority over another writer's work.
