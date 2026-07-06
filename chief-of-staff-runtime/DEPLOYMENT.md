# Deploying the Chief of Staff Runtime (Phase 0)

> **Cloud:** Azure GCC High (`AzureUSGovernment`), region `usgovvirginia`.
> **Pattern:** reused from `vivche/security-plugin` — subscription-scope Bicep + container on
> Azure Functions (Elastic Premium), deployed via GitHub Actions.

Phase 0 is a **governance proof**: read-only, in-memory stores (`COS_USE_IN_MEMORY_STORES=true`),
no Cosmos DB. Live Microsoft Graph calls stay blocked until **admin consent** is granted for
`cos-runtime-api` (see [`docs/APP_REGISTRATION.md`](docs/APP_REGISTRATION.md)).

## What gets created

Subscription-scope [`infra/main.bicep`](infra/main.bicep) creates the resource group
`cos-runtime-dev-rg`, then [`infra/modules/resources.bicep`](infra/modules/resources.bicep) deploys:

| Resource | Notes |
|----------|-------|
| User-assigned managed identity | Shared by the Function App |
| Log Analytics + Application Insights | Workspace-based telemetry |
| Storage account | `allowSharedKeyAccess: false` — managed-identity access only |
| **Dedicated COS Key Vault** (`kv-cos-runtime-*`) | RBAC-authorised; holds the client secret |
| Azure Container Registry (Basic) | Holds the runtime image |
| App Service plan + Function App | Container: `DOCKER|<acr>/cos-runtime:latest`. Plan SKU defaults to **B1** (Basic dedicated, ~$13/mo, `alwaysOn`); set `planSku='EP1'` for Elastic Premium scale-out. |

Role assignments on the managed identity: `AcrPull`, `Key Vault Secrets User`,
`Storage Blob Data Owner`, `Storage Queue Data Contributor`, `Storage Table Data Contributor`.

The runtime's `COS_CLIENT_SECRET` app setting is a **Key Vault reference**
(`@Microsoft.KeyVault(SecretUri=...)`) into the dedicated COS vault — no secret value is stored in
Bicep or in app settings.

## GitHub Actions (three workflows, repo root)

The deploy pipeline reuses the proven `security-plugin` three-workflow chain (all under the repo-root
`.github/workflows/`), scoped to `chief-of-staff-runtime/**` and using `COS_`-prefixed
secrets/variables so nothing collides with SimpleChat's own CI:

| Workflow | File | Trigger |
|----------|------|---------|
| COS Deploy Infrastructure | `cos-infra-deploy.yml` | push to `chief-of-staff-runtime/infra/**` or manual |
| COS Build and Push Docker Image | `cos-docker-build.yml` | push to `chief-of-staff-runtime/src/**` or manual |
| COS Deploy Function App | `cos-function-deploy.yml` | after the build workflow succeeds, or manual |

## Prerequisites (one-time)

1. **Service principal (SP JSON).** In GCC High, create an SP and grant it at **subscription** scope
   `Contributor` **and** `User Access Administrator` (the template creates RBAC role assignments):
   ```powershell
   az cloud set --name AzureUSGovernment
   az ad sp create-for-rbac --name "gh-cos-runtime-deploy" `
     --role Contributor --scopes /subscriptions/<sub-id> --sdk-auth
   az role assignment create --assignee <appId> `
     --role "User Access Administrator" --scope /subscriptions/<sub-id>
   ```
2. **Repo secret** `COS_AZURE_CREDENTIALS` = the `--sdk-auth` JSON from step 1.

## Deploy

### 1. Provision infrastructure

Run **COS Deploy Infrastructure** (`cos-infra-deploy.yml`). It validates then deploys
[`infra/main.bicep`](infra/main.bicep) with [`infra/main.bicepparam`](infra/main.bicepparam) via
`azure/arm-deploy@v2` (subscription scope), and writes repo **variables** for the next workflows:
`COS_ACR_NAME`, `COS_ACR_LOGIN_SERVER`, `COS_FUNCTION_APP_NAME`, `COS_RESOURCE_GROUP`.

### 2. Set the ACR + Key Vault secrets (one-time, after first infra deploy)

Because ACR/KV names carry a random suffix, capture them once from the infra outputs (or
`COS_*` repo variables) and set:

- **Repo secrets** for the build/deploy workflows:
  - `COS_ACR_LOGIN_SERVER` (e.g. `acrcosruntimexxxxxx.azurecr.us`)
  - `COS_ACR_USERNAME` / `COS_ACR_PASSWORD` (`az acr credential show -n <acr>`)
- **Copy the client secret into the dedicated COS Key Vault** (Bicep never stores the value). Run in
  a trusted shell — do **not** print the value into logs or chat:
  ```powershell
  az cloud set --name AzureUSGovernment
  az login
  # Grant yourself Key Vault Secrets Officer on the vault if needed, then:
  az keyvault secret set --vault-name <kv-cos-runtime-xxxxxx> --name cos-runtime-poc --value <SECRET>
  ```
  The `COS_CLIENT_SECRET` reference resolves once the secret exists and the managed identity has
  `Key Vault Secrets User` (assigned by the template).

### 3. Build + deploy the runtime container

Run **COS Build and Push Docker Image** (`cos-docker-build.yml`) — builds
[`src/Dockerfile`](src/Dockerfile) and pushes `:<sha>` + `:latest` to ACR. On success it triggers
**COS Deploy Function App** (`cos-function-deploy.yml`), which points the Function App at the new
image, restarts it, and verifies it is `Running`.

## Verify

- `GET https://func-cos-runtime-dev.azurewebsites.us/api/v1/health` (or the `/v1/*` routes) returns 200.
- App settings show sovereign endpoints (`*.core.usgovcloudapi.net`) and the `COS_CLIENT_SECRET`
  Key Vault reference resolves (green in the portal).

## Not yet wired

- **Admin consent** for `cos-runtime-api` is still pending — live Graph and OBO stay disabled until granted.
- **Cosmos DB** is Phase 1; Phase 0 uses in-memory stores.
- **Hardening:** replace the client secret with a federated identity credential before any non-POC deploy
  (tracked in [`docs/BACKLOG.md`](docs/BACKLOG.md)).
