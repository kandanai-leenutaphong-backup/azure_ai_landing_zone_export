---
name: start-app-gateway
description: 'Start the stopped hub WAF Application Gateway (agw-thai-search-sea in rg-hub-sea) that fronts customer-service-multi-agent.azuremew-domain.org, then verify the app answers from outside. Use when the app URL, browser sign-in, exercise or `deploy.sh replay` times out (httpx ConnectTimeout, curl 000, Errno 60), when `deploy.sh status` shows the gateway as Stopped, or when asked to start, restart or wake the app gateway.'
---

# Start the hub App Gateway

The hub WAF gateway is shared and is stopped by tenant governance automation outside working
hours (observed callers: `MCAPSGovernance-AutomationApp`, principal
`da847d8c-ee71-44de-b462-6775e7d649a7`). A stopped gateway makes every public call to the app
time out; the Container App itself stays healthy.

## Run

From the repository root:

```bash
bash .github/skills/start-app-gateway/scripts/start.sh        # environment defaults to sea
```

The script:

1. Prints the current `operationalState` and, when available, who last stopped the gateway.
2. Calls the owning action `bash deploy/deploy.sh -e sea start-gateway` (preflight, start only
   when `Stopped`, refuse unless it settles `Running`). Starting takes about 5 to 10 minutes;
   use a long wait (600 s).
3. Polls `https://$PUBLIC_HOST/healthz` until 200; exits 1 if the gateway is Running but the app
   is not serving.

Targets come from `deploy/env/<environment>.env` (`HUB_SUBSCRIPTION_ID`, `HUB_RESOURCE_GROUP`,
`GATEWAY`, `PUBLIC_HOST`). No secrets are read.

## Authority and limits

- Starting is a billable mutation of a shared hub resource; the user asking to start the
  gateway (or to make the app reachable) is the authorization. Never stop, delete, resize or
  reconfigure the gateway, WAF policy, listeners or NSG from this skill.
- Do not try to disable or work around the governance automation; it will stop the gateway
  again. Tell the user to rerun this skill when the URL times out.
- After a start, `bash deploy/deploy.sh -e sea verify` gives the full evidence (health 200,
  anonymous/forged 401, WAF probe 403).

## Report

One line: before state, after state, `/healthz` status, and who last stopped it.
