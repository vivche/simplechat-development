# FETCH MODELS MANAGED IDENTITY SUBSCRIPTION NOT FOUND FIX

## Overview
This document describes the fix for Azure OpenAI model discovery failures when using Managed Identity authentication.

Related issue: **#763**

Fixed in version: **0.238.025**
Related config version: `application/single_app/config.py` (`VERSION = "0.238.025"`)

## Issue Statement
In GCC-H deployments, the Admin action to fetch Azure OpenAI deployments (GPT, Embedding, and Image models) could fail with `SubscriptionNotFound`, even when the subscription and resource group values were correct.

## Root Cause Analysis
The backend model-fetch endpoints were always constructing the Azure management client with `ClientSecretCredential`, regardless of the selected authentication mode in settings.

As a result:
- Environments configured for Managed Identity still attempted service principal secret authentication.
- The credential context could target an unintended tenant/subscription path for management-plane calls.
- Model listing calls returned authorization/subscription resolution errors.

## Technical Changes
### Files Modified
- `application/single_app/route_backend_models.py`

### Code Changes Summary
1. Added `_create_management_client(subscription_id, auth_type)` to centralize management client creation.
2. Added auth-mode branching:
   - `managed_identity` -> `DefaultAzureCredential()`
   - other modes -> `ClientSecretCredential(...)`
3. Preserved sovereign/custom cloud handling:
   - Uses `base_url=resource_manager` and `credential_scopes=credential_scopes` for `usgovernment` and `custom`.
4. Updated all model routes to pass per-endpoint auth type from settings:
   - `/api/models/gpt` uses `azure_openai_gpt_authentication_type`
   - `/api/models/embedding` uses `azure_openai_embedding_authentication_type`
   - `/api/models/image` uses `azure_openai_image_gen_authentication_type`

## Impact Analysis
### Before
- Managed Identity configuration was ignored for model-fetch management calls.
- Admin model-fetch requests could fail with `SubscriptionNotFound` or related auth errors.

### After
- Model-fetch calls honor each endpoint’s configured authentication type.
- Managed Identity environments use `DefaultAzureCredential` as expected.
- Model discovery behavior is consistent with Admin authentication settings.

## Validation
### Testing Approach
- Static verification of route logic in `route_backend_models.py`.
- Confirmed all three model endpoints now read and use their own `*_authentication_type` settings.
- Confirmed sovereign cloud branch remains intact for GCC-H.

### Expected Runtime Validation
1. In Admin settings, set model auth type to Managed Identity.
2. Use "Fetch GPT Models", "Fetch Embedding Models", and "Fetch Image Models".
3. Verify deployments are returned without `SubscriptionNotFound`.

## Notes
If fetch still fails after this fix, verify role assignments for the active principal (Managed Identity or Service Principal) at the Azure OpenAI account scope and confirm tenant/subscription alignment in settings.