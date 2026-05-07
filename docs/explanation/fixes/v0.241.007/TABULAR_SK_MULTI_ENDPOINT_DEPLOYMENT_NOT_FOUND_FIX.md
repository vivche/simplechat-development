# Tabular SK Analysis — Multi-Endpoint DeploymentNotFound Fix

Fixed/Implemented in version: **0.241.007**

## Issue Description

When a user uploaded a tabular file (CSV or XLSX) and asked a question about its contents, the AI returned only 3–5 preview rows instead of performing a full analysis. The response looked like:

> "I cannot access the full list of controls from the catalog based on the limited schema preview available..."

## Root Cause Analysis

The SK (Semantic Kernel) tabular mini-agent crashed with a `404 DeploymentNotFound` error **before calling any tools**:

```
[Tabular SK Analysis] Attempt 1 synthesis failed:
  NotFoundError: Error code: 404 - {'error': {'code': 'DeploymentNotFound', ...}}
  successful_tool_count: 0, failed_tool_count: 0
```

**Why it happened:**  
`run_tabular_sk_analysis` always created its `AzureChatCompletion` service using `settings.get('azure_openai_gpt_endpoint')` — the base configuration endpoint. However, when a user selects a model registered in the **multi-endpoint model system** (e.g., `gpt-5.1` on a different Azure OpenAI resource), that model's deployment does not exist at the base endpoint. The main chat handler correctly resolves the endpoint via multi-endpoint selection; the tabular SK mini-agent did not receive this resolved endpoint.

**Failure chain:**
1. User selects a multi-endpoint model (e.g. `gpt-5.1`)
2. Main chat resolves: `gpt_client, gpt_model, gpt_provider, gpt_endpoint, gpt_auth, gpt_api_version = multi_endpoint_config`
3. Tabular SK mini-agent is invoked with `gpt_model` but **not** `gpt_endpoint`
4. Mini-agent tries to call `gpt_model` on `settings['azure_openai_gpt_endpoint']` → 404
5. Zero tools execute → falls back to schema-only mode (3–5 preview rows)
6. Fallback system message explicitly tells the outer GPT: *"only use the schema summary, do not invent numeric totals"*
7. AI honestly reports it can only see the preview rows

## Files Modified

| File | Change |
|------|--------|
| `application/single_app/route_backend_chats.py` | Added `gpt_endpoint`, `gpt_api_version`, `gpt_auth`, `gpt_provider` params to `run_tabular_sk_analysis` and `run_tabular_analysis_with_multi_file_support`; updated service creation logic; updated all 4 call sites |

## Code Changes Summary

### 1. `run_tabular_sk_analysis` — new parameters

```python
async def run_tabular_sk_analysis(...,
    gpt_endpoint=None,
    gpt_api_version=None,
    gpt_auth=None,
    gpt_provider=None):
```

### 2. `run_tabular_sk_analysis` — service creation priority

When `gpt_endpoint` is provided (multi-endpoint model), the function now creates the SK `AzureChatCompletion` service using the **resolved endpoint and auth** from the caller. Supports all three auth types: API key, managed identity, and service principal. Falls back to the original APIM/base-settings path when no resolved endpoint is given.

```python
if gpt_endpoint:
    # Use the caller-resolved multi-endpoint config
    ...
elif enable_gpt_apim:
    # APIM path (unchanged)
    ...
else:
    # Base settings path (unchanged)
    ...
```

### 3. `run_tabular_analysis_with_multi_file_support` — new parameters

Same 4 parameters added and threaded through to `run_tabular_sk_analysis`.

### 4. Call sites updated (4 locations)

All calls to `run_tabular_analysis_with_multi_file_support` now pass:
```python
gpt_endpoint=gpt_endpoint,
gpt_api_version=gpt_api_version,
gpt_auth=gpt_auth,
gpt_provider=gpt_provider,
```

Affected call sites:
- Non-streaming workspace tabular analysis (~line 7685)
- Non-streaming chat-uploaded tabular analysis (~line 7872)
- Streaming workspace tabular analysis (~line 10149)
- Streaming chat-uploaded tabular analysis (~line 10312)

## Impact Analysis

- **Before fix:** Any user on a multi-endpoint model gets schema-only (3–5 rows) for all tabular queries
- **After fix:** The SK mini-agent connects to the correct endpoint and executes analysis functions (`filter_rows`, `query_tabular_data`, `search_rows`, etc.) against the full dataset
- **No regression risk:** Single-endpoint (APIM / base settings) deployments are unaffected — the new `gpt_endpoint` param defaults to `None` and the existing code paths are preserved

## Version Implemented

Fixed in: **v0.241.007**

## Related

- Fallback system message: `build_tabular_fallback_system_message()` in `route_backend_chats.py`
- Multi-endpoint resolution: `get_streaming_model_endpoint_candidates()` / `build_streaming_multi_endpoint_client()` in `route_backend_chats.py`
- SK mini-agent entry point: `run_tabular_sk_analysis()` in `route_backend_chats.py`
