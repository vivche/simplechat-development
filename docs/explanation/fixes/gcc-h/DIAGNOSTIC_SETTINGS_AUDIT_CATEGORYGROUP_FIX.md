# Fix: Diagnostic Settings — 'Audit' CategoryGroup Not Supported in GCC-H

## Issue Description

Running `azd up` against an Azure Government (GCC-H) subscription failed during the Key Vault deployment step with:

```json
{
  "code": "BadRequest",
  "message": "CategoryGroup: 'Audit' is not supported, supported ones are: 'allLogs'"
}
```

Full failing resource:
```
Microsoft.KeyVault/vaults/<name>/providers/Microsoft.Insights/diagnosticSettings/<name>-diagnostics
```

## Root Cause

The `standardLogCategories` variable in [deployers/bicep/modules/diagnosticSettings.bicep](../../../../../deployers/bicep/modules/diagnosticSettings.bicep) defined two category group entries:

```bicep
var standardLogCategories = [
  {
    categoryGroup: 'Audit'   // ❌ Not supported in Azure Government
    enabled: true
    ...
  }
  {
    categoryGroup: 'allLogs' // ✅ Supported everywhere
    enabled: true
    ...
  }
]
```

The `Audit` categoryGroup is not available in Azure Government — only `allLogs` is supported. Additionally, having both entries in Azure Commercial caused audit events to be **double-logged**, increasing Log Analytics ingestion costs unnecessarily.

## Fix Applied

Removed the redundant `Audit` entry. `allLogs` is a superset of `Audit` and works in all environments.

**File:** `deployers/bicep/modules/diagnosticSettings.bicep`

```bicep
// Before
var standardLogCategories = [
  { categoryGroup: 'Audit',   enabled: true, retentionPolicy: standardRetentionPolicy }
  { categoryGroup: 'allLogs', enabled: true, retentionPolicy: standardRetentionPolicy }
]

// After
var standardLogCategories = [
  { categoryGroup: 'allLogs', enabled: true, retentionPolicy: standardRetentionPolicy }
]
```

## Impact by Environment

| Environment | Before | After |
|---|---|---|
| Azure Commercial | Worked but double-logged audit events | Works, single log stream, lower cost |
| GCC-H | ❌ Deployment failed with BadRequest | ✅ Deploys successfully |

## Resources Affected

This `diagnosticSettings.bicep` module is shared by all resources that use `standardLogCategories`, including:

- Key Vault
- Cosmos DB
- Azure AI Search
- Cognitive Services (OpenAI, Document Intelligence, Content Safety)
- App Service
- Storage Account
- Redis Cache

## Version

Implemented in: **v0.238.024**

## Resolution Steps

After this fix, re-run `azd up` from the `deployers/` directory. AZD will resume from the failed step — already-deployed resources are skipped.

```powershell
cd C:\Source\DIA\simplechat-development\deployers
azd up
```

## Related Fixes

- [INITIALIZE_ENTRA_LOGOUT_URL_FIX.md](./INITIALIZE_ENTRA_LOGOUT_URL_FIX.md) — Entra app registration logout URL Bad Request on GCC-H
