---
name: deploy-container-apps
description: "Use when deploying a web application to Azure Container Apps: managed-identity ACR pulls, server-side image builds, protected rollout sequencing, verification, teardown."
---

# Deploy a web app to Azure Container Apps

## Project integration

Read [customer-service context](../../instructions/customer-service-multi-agent.instructions.md).
Reuse the **internal, VNet-integrated** `capps-env-sea` with the existing hub WAF route.
Parent owns `deploy/deploy.sh`, TLS and gateway activation. The intended public URL does not
authorize a public Container Apps environment or public Foundry endpoint. Preserve other
apps and existing identity; no RBAC grants, secret retrieval or new registrations.
Examples below are portable, unexecuted patterns, not approved values or local receipts.

Deployment guidance, not an automatic installer. Use the target project's `deploy/deploy.sh`
and documented environment configuration as the single operator entry point. Require explicit
authorization for provisioning, rollout and teardown; installing this skill grants none.
No local Docker is required. Timings below are historical observations, not current guarantees.

## Resources

| Resource | Why | Note |
| --- | --- | --- |
| Log Analytics | environment logs | skip if reusing an environment |
| Container Apps environment | runtime host | reuse the approved existing environment, including private/VNet topology |
| Container Registry (Basic) | image | `adminUserEnabled: false` |
| User-assigned identity | pull + data access | AcrPull on the registry |
| Container App | the app | ingress and scale from the owning app configuration, not defaults here |

Reuse beats provisioning; no timing saving is measured in this checkout. Inspect first with
`az containerapp env list -g $RG --query "[].{n:name,vnet:properties.vnetConfiguration}"`. A
VNet-integrated environment needs its approved routing. An internal environment may use app
`external: true` for callers outside the app but inside its reachable network; that does not
make the environment public. Preserve the existing WAF-to-internal-backend pattern.

## Bicep essentials

Illustrative only. The role-assignment resource below requires separate authority and is
**not authorized for this project**. Reuse effective existing pull identity; report missing access.
Do not deploy a quickstart placeholder or copy scale/ingress values without the owning contract.

```bicep
param existingEnvironmentName string = ''          // '' creates one
var environmentId = empty(existingEnvironmentName)
  ? environment.id
  : resourceId('Microsoft.App/managedEnvironments', existingEnvironmentName)

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)   // 7f951dda-4ed3-4680-a7ca-43fe172d538d
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'                    // omit → transient failures
  }
}

configuration: {
  ingress: { external: true, targetPort: 8080, allowInsecure: false }
  registries: [ { server: registryServer, identity: identity.id } ]   // identity pull, no creds
}
scale: { minReplicas: 0, maxReplicas: 2 }
dependsOn: [ acrPull ]        // pull fails if the role lands after the app
```

`.id` on a conditional resource is safe (compiles to `resourceId()`); `.properties` is not — guard
with `!` or a condition. First deploy has no image: default `containerImage` to
`mcr.microsoft.com/k8se/quickstart:latest`, leave `registryServer` empty.

Needs resource-creation permission and permission to assign the required role at its target scope.
If either is absent, stop for the operator to resolve it. Do not replace managed-identity pulls
with registry credentials to work around missing authority.

## Image: split base and content

```dockerfile
# Dockerfile.base — rebuild only when dependencies change
ARG APPROVED_BASE
FROM ${APPROVED_BASE}
RUN useradd --create-home --uid 10001 app
COPY requirements.txt /app/requirements.txt
RUN uv pip install --python /usr/local/bin/python --no-cache -r /app/requirements.txt
```

```dockerfile
# Dockerfile — one thin layer per publish
ARG BASE
FROM ${BASE}
COPY server.py /app/server.py
COPY site/ /app/site/
EXPOSE 8080
USER app
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8080","--no-server-header"]
```

The approved base must already contain `uv` and the named interpreter; this example does not
install tooling or create an environment. Match actual app manifests instead of assuming Python.
Imported historical timing: naive 93s versus split 46–60s (28s build, 18s rollout).
Original receipts are unavailable here; no current speedup is established.

## Build and roll out

```bash
az acr build -r $ACR -t writeup-base:1 -f deploy/Dockerfile.base .      # once
az acr build -r $ACR -t app:$TAG -f deploy/Dockerfile \
  --build-arg BASE=$REGISTRY/writeup-base:1 .                          # per publish
az containerapp update -g $RG -n $APP --image $REGISTRY/app:$TAG
```

`az acr build` runs server-side — **no local Docker daemon**. Unique tag per publish; reusing a tag
makes rollout a no-op.

Non-root images: `nginxinc/nginx-unprivileged` (listens 8080), not stock `nginx`, whose entrypoint
needs root for pid/cache.

## Verify

```bash
az containerapp revision list -g $RG -n $APP \
  --query "[].{n:name,active:properties.active,health:properties.healthState,r:properties.replicas}" -o table
curl -so/dev/null -w'%{http_code}\n' https://$FQDN/healthz
```

Use the owning app's approved probe/auth contract. Do not add a public authentication
exemption merely for this example. Ingress `targetPort` must match the listen port.

## Gotchas

| Symptom | Cause / fix |
| --- | --- |
| `COPY failed: file not found` | `.dockerignore` excludes what the Dockerfile copies. Use `deploy/*` + `!deploy/app`. |
| 504 immediately after rollout | Revision handover. Old revision still takes traffic for seconds. Re-probe. |
| Two revisions active | Normal briefly in Single mode; latest takes 100% once healthy. |
| `RoleAssignmentUpdateNotPermitted` | No User Access Administrator on the scope. |
| Image pull fails | Role assignment raced the app. `dependsOn` the assignment. |
| Config change appears not to apply | Sidecar/config picked up at replica start. `az containerapp revision restart`. |
| ARM 200 but the setting reverts | Possible Azure Policy `Modify`; inspect Activity Log and read back fields. Policy exemptions are outside this project's grant; report a blocker. |

## Teardown

Not authorized by the current app request. Never delete the shared landing-zone resource group,
environment, registry, identity, gateway or DNS zone using this portable example.

```bash
az group delete -n $RG --yes --no-wait          # dedicated group only
```

In a **shared** group delete resources individually — registry, identity, app — or you take out
someone else's work.

## Sequencing, and the exposure window

```
infra → base image → content image → auth → verify
```

Between first rollout and auth configuration the app **serves publicly**. For non-public content,
`az containerapp ingress disable` before the first rollout; re-enable only once refusal is proven.
Do not race it.

Optional companion skills: `azure-access-management` for native-first sign-in and identity integration and
`content-from-a-store` for independent content publication. Request them through the client when
available; this skill does not load sibling files. The application must still fail closed before
ingress is enabled, whether those companions are installed or not.
