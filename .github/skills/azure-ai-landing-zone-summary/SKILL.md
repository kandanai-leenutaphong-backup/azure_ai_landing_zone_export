---
name: azure-ai-landing-zone-summary
description: Summarize or refresh this repository's deployed Azure AI landing zone across the connectivity hub, SEA workload spoke, regional agent spoke, and AI Gateway subscriptions, including subscription IDs, resource groups, VNets, peerings, subnets, and key resources. Use for environment orientation, deployment planning, troubleshooting, handoffs, and reuse of the current Azure topology.
---

# Azure AI Landing Zone Summary

Use this skill to answer questions about the current four-subscription Azure
environment represented by this repository.

## Workflow

1. Read `references/current-environment.md` first for the known baseline.
2. Treat the reference as a dated snapshot, not an assurance of current Azure
   state.
3. If the user asks for the current, live, latest, refreshed, or verified
   environment, run:

   ```bash
   bash .github/skills/azure-ai-landing-zone-summary/scripts/summarize.sh
   ```

4. Reconcile live output with:
   - `bicep/main.bicep` for deployment intent and defaults.
   - `bicep/agent-spoke.bicep` for the minimal regional agent spoke.
   - `bicep/parameters/main.json` for checked-in hub and spoke values.
   - `ARCHITECTURE.md` and `docs/ai-gateway-landing-zone.md` for design context.
   - `deploy/README.md` and `deploy/env/sea.env` for the independently released
     `customer-service-multi-agent` app, public DNS, TLS and hub WAF route.
5. Clearly label facts as either live Azure state, checked-in configuration, or
   documented intent when they differ.

## Response requirements

- Lead with a compact table containing role, subscription name, subscription
  ID, resource group, region, VNet, and address space.
- Then summarize connected peerings, subnet purposes, and key resource roles.
- Include exact resource names when they are relevant to a command, deployment,
  incident, or handoff.
- Prefer operationally useful detail over an exhaustive list of generated
  objects such as NICs, disks, private endpoint NICs, DNS VNet links, and Event
  Grid system topics.
- Call out drift, failed provisioning states, disconnected peerings, missing
  resource groups, and inaccessible subscriptions.
- Never print access keys, connection strings, tokens, SSH key material, APIM
  subscription keys, or secret values.
- Do not modify Azure resources unless the user separately asks for a change.

## Stable role mapping

- Connectivity hub: centralized VPN, DNS resolver, and private DNS.
- Workload spoke: private application compute, SEA Foundry accounts, data
  services and private endpoints. The public Application Gateway WAF is in the
  connectivity hub, not this spoke.
- Regional agent spoke: private Foundry standard agents with customer-owned
  Blob Storage, AI Search, and Cosmos DB; global peerings to the hub and SEA spoke.
- AI Gateway hub: APIM, shared Foundry quota, semantic cache, API inventory,
  and usage/chargeback services.

## Customer service project

`applications/customer-service-multi-agent` composes its workflow in SEA and
invokes native prompt agents in the existing private West US 3 project. Reuse
the four-subscription topology; do not interpret this app as another landing
zone or move Foundry into SEA. Its target hostname is
`customer-service-multi-agent.azuremew-domain.org`, backed by the existing
hub WAF and delegated public DNS zone. A dated app `verify` receipt, not this
skill, establishes whether the hostname is serving.

Report system, journey-type and per-agent telemetry separately. Specialized
judge scores are estimates; missing human calibration and real business-impact
data remain explicit gaps. Imported harness guidance is project-adapted under
`.github/instructions/customer-service-multi-agent.instructions.md`.
