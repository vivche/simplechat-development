# Issue: Missing `AZURE_ENVIRONMENT` app setting causes `SubscriptionNotFound` in US Gov deployments

## Summary
Discovered in US Gov during Admin model discovery operations. App Service was missing `AZURE_ENVIRONMENT`, so runtime config defaulted to `public` and used public cloud management endpoints. This caused `SubscriptionNotFound` for a valid US Gov subscription.

Manual addition of `AZURE_ENVIRONMENT=usgovernment` in App Service immediately resolved the issue.

## Environment
- Cloud: Azure Government (`AZURE_ENVIRONMENT=usgovernment`)
- Area: Admin configuration → model discovery
- Endpoints:
  - `/api/models/gpt`
  - `/api/models/embedding`
  - `/api/models/image`

## Problem Statement
Admin “Fetch GPT/Embedding/Image Models” can fail with `SubscriptionNotFound` in US Gov because the deployed app may run with public-cloud endpoint configuration when `AZURE_ENVIRONMENT` is absent.

## Observed Behavior
- Fetch actions return an error from Azure management-plane deployment listing.
- Common error: `SubscriptionNotFound`.

## Expected Behavior
- If auth type is `managed_identity`, model fetch should use Managed Identity credentials and return deployments successfully.
- If auth type is `key` (or not configured), existing key/client-secret path should continue to work.

## Root Cause
Infrastructure configuration set `AZURE_ENDPOINT` instead of `AZURE_ENVIRONMENT` in App Service app settings.

Runtime code expects:
- `AZURE_ENVIRONMENT = os.getenv("AZURE_ENVIRONMENT", "public")`

When missing, the app falls back to `public`, which is incorrect for US Gov and leads to subscription lookup failures.

## Reproduction Steps
1. Deploy app to US Gov without `AZURE_ENVIRONMENT` in App Service settings.
2. Configure valid Azure OpenAI model settings (subscription ID, resource group, endpoint).
3. Click:
   - Fetch GPT Models
   - Fetch Embedding Models
   - Fetch Image Models
4. Observe failure (`SubscriptionNotFound`).

## Proposed Fix
- Update Bicep app settings to publish the expected key:
  - `AZURE_ENVIRONMENT` (not `AZURE_ENDPOINT`)
- Set value to lowercase `usgovernment` when deploying to AzureUSGovernment.
- Keep generated ARM (`main.json`) in sync with the same key.

## Acceptance Criteria
- [ ] App Service contains `AZURE_ENVIRONMENT` after deployment.
- [ ] In GCC-H, value is `usgovernment` (lowercase).
- [ ] Admin model fetch endpoints return deployments without `SubscriptionNotFound`.
- [ ] Public cloud deployments continue to set `AZURE_ENVIRONMENT=public`.

## Impact
- Scope is deployment configuration (App Service app settings) and not limited to one backend route.
- Prevents cloud-environment mismatch across services that depend on `AZURE_ENVIRONMENT`.
