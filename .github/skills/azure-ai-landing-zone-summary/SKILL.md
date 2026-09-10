---
name: azure-ai-landing-zone-summary
description: Summarize or refresh this repository's deployed Azure AI landing zone across the connectivity hub, workload spoke, and AI Gateway subscriptions, including subscription IDs, resource groups, VNets, peerings, subnets, and key resources. Use for environment orientation, deployment planning, troubleshooting, handoffs, and reuse of the current Azure topology.
---

# Azure AI Landing Zone Summary

Use this skill to answer questions about the current three-subscription Azure
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
   - `bicep/parameters/main.json` for checked-in hub and spoke values.
   - `ARCHITECTURE.md` and `docs/ai-gateway-landing-zone.md` for design context.
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
- Workload spoke: application compute, Foundry accounts, data services, private
  endpoints, and Application Gateway.
- AI Gateway hub: APIM, shared Foundry quota, semantic cache, API inventory,
  and usage/chargeback services.

