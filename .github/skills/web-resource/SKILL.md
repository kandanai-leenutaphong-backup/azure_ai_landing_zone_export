---
name: web-resource
description: "Use when acquiring public documentation, reference images or screenshots with guarded transport, robots policy, rate limits and verifiable provenance."
---

# Web Resource

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Public documentation acquisition is separate from private Foundry/WAF acceptance. Do not
route the private endpoint through a public-only fetcher or send repository/customer content
to external services. Existing dependencies and acquisition authority must be verified.

For an explicitly selected integration, package `harness-web-resource` provides `webres.fetch`, `Catalogue`, `Provenance`, `validate_url`
and the `web-resource-*` commands. Read the canonical [guide](GUIDE.md)
and [installation and verification](README.md).

Python 3.11+; screenshots additionally require the declared `browser` extra and existing Chromium.
Public-only URLs, DNS/redirect checks, robots.txt, rate limits and provenance remain mandatory.
No login, private-network access, paywall bypass or acquisition permission follows from installation.
Host chooses output/catalogue locations; downloaded material remains untrusted publisher-owned content.
Tests use local fixtures, never public acquisition or collection refresh.