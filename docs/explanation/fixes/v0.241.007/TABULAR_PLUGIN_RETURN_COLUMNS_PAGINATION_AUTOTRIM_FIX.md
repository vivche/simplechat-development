# Tabular Processing Plugin — Return Columns, Pagination & Auto-Trim Fix

Fixed/Implemented in version: **0.241.007**

**File:** `application/single_app/semantic_kernel_plugins/tabular_processing_plugin.py`

## Issue Description

When analysing large spreadsheets (e.g. NIST SP 800-53 with 1,189 rows), the tabular SK mini-agent produced synthesis failures or returned incomplete results because:

1. Tool result payloads exceeded the model's per-message token budget (200K char threshold was too high)
2. The `return_columns` parameter was silently ignored on cross-sheet code paths — multi-sheet workbook queries always returned all columns regardless of the parameter
3. Row-only truncation (after column drops) was not detected by callers, so the `note` field was never set and the outer model had no indication that rows were cut

## Root Cause Analysis

### Problem 1 — Threshold too high

`_auto_trim_df_for_output` used a 200K char threshold. A 1,189-row × 20-column spreadsheet serialises to ~800K–1M chars raw, so trimming fired late and unreliably. The model received massive payloads that triggered 429 RateLimitError on the synthesis call after tool execution.

### Problem 2 — Cross-sheet `return_columns` not forwarded

```python
# Before — return_columns accepted but silently dropped
def filter_rows(self, ..., return_columns=None):
    return self._filter_rows_across_sheets(filename, ...)  # ← param not passed
```

### Problem 3 — Identity check bug on cross-sheet callers

```python
# Before — only detected column drops, missed row-only truncation
if auto_excluded_columns:
    paginated = trimmed_df   # ← silently wrong when only rows were trimmed
```

## Files Modified

| File | Change |
|------|--------|
| `application/single_app/semantic_kernel_plugins/tabular_processing_plugin.py` | Threshold 200K→50K, Phase 2 row truncation, identity check fix, `return_columns` forwarding, `note` field in 4 result payloads |

## Code Changes Summary

### 1. `_auto_trim_df_for_output` — tighter threshold and Phase 2 row truncation

| Parameter | Before | After |
|-----------|--------|-------|
| `max_chars` default | 200,000 | 50,000 |
| Short-circuit guard | `len(df) <= 50` | `len(df) <= 10` |
| Phase 2 row truncation | Not present | Added |

**Phase 2** runs after column drops. If the serialised output is still over `max_chars`, the function calculates a target row count and truncates:

```python
chars_per_row = total_chars / max(1, len(result_df))
target_rows = max(10, int(max_chars / chars_per_row))
result_df = result_df.head(target_rows)
```

The function returns `(result_df, excluded_columns)`. Callers use an object identity check (`trimmed_df is not temp_df`) to detect any trimming — including row-only truncation where `excluded_columns` would be empty.

### 2. Cross-sheet callers — identity check bug fix

**Before (bug):**
```python
if auto_excluded_columns:
    paginated = trimmed_df   # ← row-only truncation silently missed
```

**After (fix):**
```python
if trimmed_df is not temp_df:
    paginated = trimmed_df   # ← catches both column drops and row truncation
```

Applied to both `_filter_rows_across_sheets` and `_query_tabular_data_across_sheets`.

### 3. `return_columns` forwarding — cross-sheet path

`return_columns` is now threaded through from the public `filter_rows` / `query_tabular_data` functions down to `_filter_rows_across_sheets` and `_query_tabular_data_across_sheets`. Multi-sheet workbook queries now honour the parameter.

### 4. Row-truncation `note` field in all four result payloads

When Phase 2 row truncation fires, all four public result payloads include a `note` field:

```json
{
  "note": "Result trimmed from 1189 to 47 rows to fit context budget. Use start_row/max_rows pagination to retrieve remaining rows.",
  "has_more": true,
  "next_start_row": 47
}
```

Affected functions:
- `filter_rows` (single-sheet)
- `query_tabular_data` (single-sheet)
- `_filter_rows_across_sheets` (cross-sheet)
- `_query_tabular_data_across_sheets` (cross-sheet)

## Impact Analysis

| Scenario | Before | After |
|----------|--------|-------|
| Large single-sheet filter (1,189 rows, all columns) | 800K+ char payload → 429/synthesis failure | ≤50K payload, row-truncation note guides pagination |
| Cross-sheet filter with `return_columns` | All columns returned (parameter ignored) | Only requested columns returned |
| Cross-sheet row-only truncation | `note` not set, outer model unaware of truncation | `note` set, model prompted to paginate |
| Small result sets (≤10 rows) | Could still be trimmed at 50K | Short-circuit guard skips trim entirely |

## Failure Mode Reference

The table below summarises every known failure mode for large-dataset analysis and the fix applied.

| Scenario | Root cause | Fix | Where |
|---|---|---|---|
| Mini-agent hits 429 on a 1,189-row fetch | `total_matches <= 25` guard blocked the large-dataset path; fallback budget was only 5 rows | Removed the `<= 25` constraint; raised `max_handoff_chars` to 200,000; gave the fallback a 200K char budget | `route_backend_chats.py` |
| Fallback showed only 5 sample rows even with a large budget | `compact_tabular_fallback_value` had a hardcoded 400-char string cap regardless of row count | Made the per-value string cap dynamic: `(budget − overhead) / (rows × cols)`, clamped to [20, 400] | `route_backend_chats.py` |
| `filter_rows`/`query_tabular_data` had no `return_columns` support | Parameter existed only on `search_rows` | Added `return_columns` to `filter_rows` and `query_tabular_data` (single-sheet and cross-sheet paths) | `tabular_processing_plugin.py` |
| Even with `return_columns`, the raw SK tool result still overflows synthesis context | Plugin emitted full unfiltered JSON; synthesis model context was exhausted | Added `_auto_trim_df_for_output`: estimates output size; if it would exceed 50K chars, drops the heaviest columns one-by-one; result includes `auto_excluded_columns` and a note so the mini-agent can re-call with explicit `return_columns` + pagination | `tabular_processing_plugin.py` (single-sheet paths) |
| Auto-trim never fired on multi-sheet workbooks | Cross-sheet path had no `return_columns` forwarding and no auto-trim | Added `return_columns` parameter to `_query_tabular_data_across_sheets`; forwarded `parsed_return_columns` from `query_tabular_data` caller; added `_auto_trim_df_for_output` in both cross-sheet helpers | `tabular_processing_plugin.py` (cross-sheet paths) |

### Residual risk and recommended usage

When a user explicitly requests long-text columns (e.g., `discussion`, `control_text`) across **all** rows of a large file:

- `return_columns` bypasses `_auto_trim_df_for_output` (by design — the user made an explicit choice)
- 1,189 rows × `discussion` alone is ~1.8 MB, which can still overflow the synthesis context

The safe pattern is **pagination**: the mini-agent should use `max_rows=50` + `start_row` to retrieve long-text columns in chunks. Prompt instruction #20 in the tabular analysis system message explicitly says this. The `auto_excluded_columns` note in the plugin response also prompts the mini-agent to re-call with `return_columns` and pagination.

```python
# Safe pattern for large long-text column export
filter_rows(..., return_columns='identifier,discussion', max_rows=50, start_row=0)
filter_rows(..., return_columns='identifier,discussion', max_rows=50, start_row=50)
# ... repeat until has_more is false
```

---

## Developer Notes

### What is the "SK inner loop" (informally called the mini-agent)?

When a user asks a question about a tabular file, the outer chat model does **not** call the plugin directly. Instead, `run_tabular_sk_analysis` (in `route_backend_chats.py`) creates a **temporary, isolated Semantic Kernel instance** loaded with only `TabularProcessingPlugin` (and optionally `FactMemoryPlugin`). SK's `FunctionChoiceBehavior` then lets the same GPT deployment autonomously decide which plugin functions to call and in what order, within a single `get_chat_message_contents` call. The synthesised result is returned to `run_tabular_sk_analysis`, which injects it into the outer model's context as a computed-results system message.

```
User message
  → route_backend_chats.py  (outer model / "single app")
      → run_tabular_sk_analysis  (creates temp SK kernel)
          → SK auto-invoke loop  (inner loop / "mini-agent")
              → TabularProcessingPlugin functions (filter_rows, query_tabular_data, …)
          ← returns synthesised text
      ← injects as system message
  ← outer model responds to user
```

This two-layer architecture keeps the tabular tool set completely isolated from the main chat flow and allows the inner loop to make multiple sequential tool calls without polluting the outer conversation history.

### Does the plugin support data chunking / pagination?

**Yes — the plugin exposes pagination, but the inner loop must drive it.**

Every data-returning function (`filter_rows`, `query_tabular_data`, `search_rows`) accepts:

| Parameter | Default | Purpose |
|---|---|---|
| `max_rows` | 100 | Maximum rows to return in one call |
| `start_row` | 0 | Zero-based offset into the full result set |

Every response includes `has_more` (bool) and `next_start_row` (int or `null`), so the inner loop can walk through pages by incrementing `start_row`.

**The practical limit: `maximum_auto_invoke_attempts`**

SK's auto-invoke cap is set to **7–8 calls per analysis pass** (`FunctionChoiceBehavior.Required` uses 8, `FunctionChoiceBehavior.Auto` uses 7). This is the hard ceiling on how many plugin calls can happen in a single user turn.

For a full NIST SP 800-53 export at 50 rows per page:

$$1{,}189 \div 50 = 24 \text{ pages}$$

That requires 24 calls — far beyond the 7–8 cap. The inner loop can page through a handful of chunks, but it **cannot autonomously exhaust a large result set in a single pass**. For bulk exports the user must ask in multiple follow-up messages, or a future enhancement would need to run `run_tabular_sk_analysis` in an outer loop at the orchestration layer.

The `auto_excluded_columns` hint in the plugin response and prompt instruction #20 encourage the inner loop to use pagination proactively when long-text columns are requested, but the call-count ceiling remains the binding constraint for very large datasets.

---

---

## Additional Bug Fix — SK `Optional[str]` Parameter Parsing (v0.241.015)

**Applies to:** All three branches carrying this fix — `fix/tabular-plugin-return-columns-pagination-autotrim`, `fix/tabular-sk-multi-endpoint-deployment-not-found`, `feature/tabular-plugin-gpt51-redesign`

### Issue Description

After deploying on Python 3.13, every `@kernel_function` call involving an optional string parameter (e.g. `sheet_name`, `filter_column`, `query_expression`) raised:

```
FunctionExecutionException: Parameter sheet_name is expected to be parsed to typing.Optional[str] but is not.
```

The analysis, aggregation, and filtering operations all failed silently. The outer model received no data.

### Root Cause

Semantic Kernel's `kernel_function_from_method.py` coerces LLM-supplied parameter values by calling `param_type(value)` at runtime. When the annotation is `Annotated[Optional[str], "..."]`, the resolved `param_type` is `typing.Union[str, None]`. Python's `typing.Union` does not support direct instantiation:

```python
typing.Optional[str]("Sheet1")   # → TypeError: Cannot instantiate typing.Union
```

SK wraps this as a `FunctionExecutionException`, aborting the call before the function body ever runs.

### Full Traceback Path

```
kernel_function.py:invoke
  → kernel_function_from_method.py:_invoke_internal
      → gather_function_parameters
          → _parse_parameter
              → param_type(value)   # param_type = typing.Optional[str]
                  → TypeError: Cannot instantiate typing.Union
```

### Before the Fix

**Before (broken):**
1. LLM calls e.g. `query_tabular_data(sheet_name="Sheet1", ...)`
2. SK tries `Optional[str]("Sheet1")` → crashes: `TypeError: Cannot instantiate typing.Union`
3. Function **never runs** — caller receives `FunctionExecutionException`
4. No data returned; mini-agent synthesis fails

### After the Fix

**After (working):**
1. LLM calls `query_tabular_data(sheet_name="Sheet1", ...)`
2. SK parses `str("Sheet1")` → `"Sheet1"` — succeeds trivially
3. Function runs with the **actual sheet name** passed through
4. Body executes `(sheet_name or '').strip()` → `"Sheet1"` → forwarded to `_resolve_sheet_selection()`
5. Correct sheet is loaded and data is returned

**If the LLM omits an optional parameter** (e.g. single-sheet CSV where no sheet name is needed):
- The `= None` default is used directly — SK never calls `param_type()` on a default
- Body: `(None or '').strip()` → `''` → falls through to auto-select the first sheet

### Fix Applied

Replaced all `Annotated[Optional[str], "..."] = None` with `Annotated[str, "..."] = None` in every `@kernel_function` method signature:

| File | Occurrences changed |
|------|-------------------|
| `tabular_processing_plugin.py` | 90–92 |
| `databricks_table_plugin.py` | 2 |

Function bodies were **not changed** — they already used `(param or '').strip()` / `(param or None)` patterns that handle both `None` and empty string `""` identically.

### Backward Compatibility

- Valid on Python 3.9+ (SK itself requires 3.10+)
- `Optional[str]` is retained for all non-`@kernel_function` internal helper methods (e.g. `_resolve_sheet_selection`, `_match_workbook_sheet_name`) — only the SK-facing public signatures were changed
- `Union.__call__` has never been callable in any Python version, so this bug affected Python 3.10–3.13 equally; the fix is version-neutral

---

## Related

- Multi-endpoint DeploymentNotFound fix: `TABULAR_SK_MULTI_ENDPOINT_DEPLOYMENT_NOT_FOUND_FIX.md`
- Redesign proposal for GPT-5.1+: `docs/explanation/features/TABULAR_PLUGIN_REDESIGN_GPT51.md`
- Plugin source: `application/single_app/semantic_kernel_plugins/tabular_processing_plugin.py`
