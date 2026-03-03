# Fix: OpenAI Model Deployment — GlobalStandard SKU Not Supported in GCC-H

## Issue Description

Running `azd up` against an Azure Government (GCC-H) subscription failed during the OpenAI model deployment step with:

```json
{
  "status": "Failed",
  "error": {
    "code": "InvalidResourceProperties",
    "message": "The specified SKU 'GlobalStandard' of account deployment is not supported by the model 'gpt-4.1' version: '2025-04-14'."
  }
}
(x) Failed: Azure AI Services Model Deployment: simplechat6-dev-openai/gpt-4.1
```

## Root Cause

The default `gptModels` and `embeddingModels` parameter arrays in [deployers/bicep/main.bicep](../../../../../deployers/bicep/main.bicep) used `GlobalStandard` as the SKU for all model deployments. `GlobalStandard` is not available in Azure Government — only `Standard` is supported.

## Fix Applied

Changed the default `skuName` from `GlobalStandard` to `Standard` in all four model entries in `main.bicep`.

**File:** `deployers/bicep/main.bicep`

```bicep
// Before
{ modelName: 'gpt-4.1',              skuName: 'GlobalStandard', skuCapacity: 150 }
{ modelName: 'gpt-4o',               skuName: 'GlobalStandard', skuCapacity: 100 }
{ modelName: 'text-embedding-3-small', skuName: 'GlobalStandard', skuCapacity: 150 }
{ modelName: 'text-embedding-3-large', skuName: 'GlobalStandard', skuCapacity: 150 }

// After
{ modelName: 'gpt-4.1',              skuName: 'Standard', skuCapacity: 150 }
{ modelName: 'gpt-4o',               skuName: 'Standard', skuCapacity: 100 }
{ modelName: 'text-embedding-3-small', skuName: 'Standard', skuCapacity: 150 }
{ modelName: 'text-embedding-3-large', skuName: 'Standard', skuCapacity: 150 }
```

## Impact by Environment

| Environment | Before | After |
|---|---|---|
| Azure Commercial | Worked with GlobalStandard (higher availability) | Works with Standard. Override to GlobalStandard via parameter if preferred. |
| GCC-H | ❌ Deployment failed | ✅ Deploys successfully |

## SKU Comparison

| SKU | Azure Commercial | GCC-H | Notes |
|---|---|---|---|
| `GlobalStandard` | ✅ Available | ❌ Not available | Routes across global Azure AI infrastructure |
| `Standard` | ✅ Available | ✅ Available | Region-specific; required for all GovCloud deployments |

## Overriding for Azure Commercial (Optional)

If deploying to Azure Commercial and you want `GlobalStandard`, override the `gptModels` and `embeddingModels` parameters at the `azd up` prompt or via a `.bicepparam` file:

```json
{
  "gptModels": [
    { "modelName": "gpt-4.1", "modelVersion": "2025-04-14", "skuName": "GlobalStandard", "skuCapacity": 150 },
    { "modelName": "gpt-4o",  "modelVersion": "2024-11-20", "skuName": "GlobalStandard", "skuCapacity": 100 }
  ],
  "embeddingModels": [
    { "modelName": "text-embedding-3-small", "modelVersion": "1", "skuName": "GlobalStandard", "skuCapacity": 150 },
    { "modelName": "text-embedding-3-large", "modelVersion": "1", "skuName": "GlobalStandard", "skuCapacity": 150 }
  ]
}
```

## Version

Implemented in: **v0.238.024**

## Resolution Steps

After this fix, re-run `azd up`. AZD will skip already-deployed resources and retry only the failed OpenAI model deployments.

```powershell
cd C:\Source\DIA\simplechat-development\deployers
azd up
```

## Related Fixes

- [INITIALIZE_ENTRA_LOGOUT_URL_FIX.md](./INITIALIZE_ENTRA_LOGOUT_URL_FIX.md) — Entra app registration logout URL Bad Request on GCC-H
- [DIAGNOSTIC_SETTINGS_AUDIT_CATEGORYGROUP_FIX.md](./DIAGNOSTIC_SETTINGS_AUDIT_CATEGORYGROUP_FIX.md) — Diagnostic settings Audit categoryGroup not supported in GCC-H
