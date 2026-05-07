# Tabular Plugin: GPT-5.1 Pandas Fast Path Redesign

**Version implemented:** 0.241.007
**Branch:** `feature/tabular-plugin-gpt51-redesign`
**Related evaluation:** [TABULAR_PLUGIN_GPT41_VS_GPT51_EVALUATION.md](./TABULAR_PLUGIN_GPT41_VS_GPT51_EVALUATION.md)

---

## Overview

The Tabular Plugin previously used a Semantic Kernel (SK) agentic tool-calling loop for all file analysis. This loop lets the model autonomously call `filter_rows`, `count_rows`, `aggregate_column`, and other tools to answer data questions. While flexible, the approach has a hard architectural ceiling: a fixed `maximum_auto_invoke_attempts` cap that is exhausted before large datasets can be fully retrieved (see the evaluation doc for detailed failure mode analysis).

The GPT-5.1 Pandas Fast Path bypasses the SK tool loop entirely for GPT-5.1-family models. Instead of letting the model call tools repeatedly, the new path:

1. Asks GPT-5.1 to generate a single pandas expression that answers the question.
2. Executes that expression directly against the blob-loaded DataFrame.
3. Asks GPT-5.1 to synthesise a natural-language answer from the execution result.

This collapses N sequential tool-calling round-trips (each carrying LLM latency) into **two model calls and one in-process compute step**, while also removing the slot-exhaustion problem for large exports.

---

## Architecture

```
User question
     │
     ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 1 — Code-gen (GPT-5.1, FunctionChoiceBehavior.NoneInvoke)  │
│                                                                   │
│  Input:  FILE SCHEMA + question                                   │
│  Output: single pandas expression (no markdown, no explanation)   │
│                                                                   │
│  Prompt rules:                                                    │
│    - Return ONLY the expression                                   │
│    - No markdown code-block markers                               │
│    - Use df for primary/default sheet                             │
│    - Use sheets['SheetName'] for other sheets                     │
│    - Available names: df, sheets, pd, re                          │
│                                                                   │
│  Example output:                                                  │
│    df[['identifier','name']].to_csv(index=False)                  │
└───────────────────────────────────────────────────────────────────┘
     │
     ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 2 — execute_pandas (in-process, asyncio.to_thread)         │
│                                                                   │
│  - Pattern scan (FORBIDDEN_PATTERNS — see Security section)       │
│  - Load DataFrame from blob storage                               │
│  - eval(code, safe_globals, safe_locals)                          │
│  - Serialise result to JSON                                       │
│  - 15-second timeout via asyncio.wait_for                         │
└───────────────────────────────────────────────────────────────────┘
     │
     ▼
┌───────────────────────────────────────────────────────────────────┐
│  Step 3 — Synthesis (GPT-5.1, FunctionChoiceBehavior.NoneInvoke) │
│                                                                   │
│  Input:  question + expression used + raw JSON result             │
│  Output: natural-language / Markdown answer                       │
│                                                                   │
│  System prompt:                                                   │
│    "You are a data analyst. Answer the user's question using      │
│     only the execution results provided. Format tables as         │
│     Markdown when appropriate. Be concise and factual."           │
└───────────────────────────────────────────────────────────────────┘
```

The fast path is attempted on `attempt_number == 1` only. If it fails (bad expression, execute_pandas error, or empty synthesis), the code falls back to the existing SK agentic loop for subsequent attempts.

---

## Performance Analysis

Timing measured on a real query against the NIST SP 800-53 Rev 5 catalog (1,189 rows, `.xlsx`):

| Step | Component | Duration |
|---|---|---|
| Step 1 | GPT-5.1 code-gen model call | ~26 s |
| Step 2 | `execute_pandas` (eval + blob I/O) | 0.019 s |
| Step 3 | GPT-5.1 synthesis model call | ~27 s |
| **Total** | **Fast path** | **~53 s** |

**Compared to the old SK agentic loop:**

| Approach | Typical range | Notes |
|---|---|---|
| SK agentic loop (GPT-5.1) | 60–85 s | Each slot carries full model round-trip; schema + N pagination calls |
| **Pandas fast path** | **~53 s** | Two model calls, no multi-slot overhead |

The `execute_pandas` step (0.019 s) is negligible. The total latency is the sum of the two LLM calls.

### Why synthesis cannot be removed

An obvious optimisation is to ask code-gen to return both the expression *and* the answer in one call, skipping synthesis. This fails for complex queries. The synthesis step serves distinct purposes:

- **Multi-result narratives** — when the expression produces multiple series or a multi-index DataFrame, the synthesis model decides how to present them coherently.
- **Contextual interpretation** — queries like *"which controls are missing from the High baseline but present in Moderate?"* require the model to reason about the structured result, not just format it.
- **Error recovery framing** — if the expression succeeded but the result is empty or unexpected, synthesis can flag this to the user rather than returning a confusing empty JSON dump.
- **Consistent answer style** — synthesis normalises output across simple scalar answers, Series results, and full DataFrames without the caller needing to know which type was returned.

Merging code-gen and synthesis into one call would require the model to simulate execution mentally, which reasoning models do unreliably and which defeats the purpose of the pandas execution step.

### Why a faster synthesis model was not used

Using `gpt-4o` for synthesis (Step 3) would save approximately 15–20 s. This was evaluated and declined because:

- GPT-5.1 handles complex multi-baseline comparisons and structured reasoning that GPT-4o inconsistently produces.
- The synthesis prompt may receive very large JSON payloads (full 1,189-row export) and reasoning-quality parsing matters for correctness.
- The infrastructure cost of routing Step 3 to a separate deployment adds coupling that is not worth the saving given the overall 53 s total is already an improvement.

---

## Security Design of `execute_pandas`

The `execute_pandas` kernel function runs model-generated code, which makes security the primary engineering concern. The implementation uses a defence-in-depth approach with three independent layers.

### Layer 1 — Pattern scanning (pre-execution)

Before any execution, the expression is scanned for a blocklist of forbidden substrings:

```python
FORBIDDEN_PATTERNS = (
    'import ', '__', 'open(', 'exec(', 'eval(', 'compile(',
    'subprocess', 'os.', 'sys.', 'globals(', 'locals(',
    'getattr(', 'setattr(', 'delattr(', '__import__', 'breakpoint(',
    'input(', 'exit(', 'quit(',
)
```

Any match returns an error immediately without reaching `eval()`. This blocks:

- Module imports (`import os`, `import subprocess`)
- Dunder access (`__class__`, `__globals__`, `__builtins__` override attempts)
- File system access (`open(`)
- Reflection and introspection (`getattr`, `setattr`, `globals()`, `locals()`)
- Interpreter control (`breakpoint()`, `exit()`, `quit()`)
- Nested evaluation (`exec(`, `eval(`, `compile(`)

The `__` pattern (double underscore) is particularly important — it blocks all dunder attribute traversal chains that are commonly used in Python sandbox escapes (e.g. `"".__class__.__mro__[1].__subclasses__()`).

### Layer 2 — Restricted `eval()` sandbox

Even if a string somehow passed the pattern scan, `eval()` is called with a severely restricted global and local namespace:

```python
safe_builtins = {
    'len': len, 'int': int, 'float': float, 'str': str, 'bool': bool,
    'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
    'range': range, 'enumerate': enumerate, 'zip': zip,
    'sorted': sorted, 'reversed': reversed, 'sum': sum,
    'min': min, 'max': max, 'abs': abs, 'round': round,
    'isinstance': isinstance, 'True': True, 'False': False, 'None': None,
}
safe_globals = {'__builtins__': safe_builtins}
safe_locals = {'df': df, 'sheets': sheets, 'pd': pandas, 're': re}
```

The key security properties:

- `__builtins__` is replaced with a hand-curated dict of safe functions — the standard library's `__builtins__` module (which gives access to `open`, `exec`, `__import__`, etc.) is not present.
- The only symbols in scope are `df` (the loaded DataFrame), `sheets` (a dict of sheet DataFrames for workbooks), `pd` (pandas), and `re` (regex). Nothing from `os`, `sys`, `subprocess`, or any other module is reachable.
- There is no way to import modules — `__import__` is absent from `safe_builtins`, and the `import` keyword itself is also blocked at Layer 1.

### Layer 3 — 15-second execution timeout

The `_sync_work` callable runs inside `asyncio.to_thread` and is wrapped in `asyncio.wait_for` with a 15-second timeout:

```python
result_json = await asyncio.wait_for(asyncio.to_thread(_sync_work), timeout=15.0)
```

This prevents:

- **CPU exhaustion** from computationally expensive pandas expressions (e.g. a nested Cartesian join on a large DataFrame).
- **Memory exhaustion** from expressions that generate very wide intermediate results.
- **Blocking the event loop** — the synchronous blob I/O and `eval()` run in a thread pool, not the asyncio loop thread.

On timeout, the function returns a structured JSON error suggesting the user simplify the expression or use sliced access (`df.iloc[start:end]`).

### Threat model summary

| Threat | Mitigated by |
|---|---|
| Arbitrary file system access (`open`, `os.path`) | Layer 1 (pattern scan) + Layer 2 (no `open` in builtins) |
| Module import (`import subprocess`) | Layer 1 (`import ` pattern) + Layer 2 (no `__import__`) |
| Dunder escape chains (`__class__.__mro__`) | Layer 1 (`__` pattern) |
| Reflection attacks (`getattr`, `globals()`) | Layer 1 (explicit patterns) |
| Nested eval/exec | Layer 1 (`exec(`, `eval(` patterns) |
| CPU/memory exhaustion via expensive expression | Layer 3 (15 s timeout) |
| Event loop blocking | Layer 3 (`asyncio.to_thread`) |

---

## Model Detection

The fast path activates only for GPT-5.1-family deployments. The detection is in `route_backend_chats.py`:

```python
def _is_pandas_mode_model(gpt_model: str) -> bool:
    """Return True when the model is gpt-5 family and should use execute_pandas."""
    return 'gpt-5' in (gpt_model or '').lower()
```

The `pandas_mode` flag is set from this function earlier in the analysis routine and passed through to the attempt loop. GPT-4.1 and earlier models continue to use the original SK tool-calling loop.

---

## Fallback Behaviour

If the fast path does not produce a result (bad expression from code-gen, `execute_pandas` error, or empty synthesis output), the code logs a warning and continues to the next loop iteration:

```python
if not _pf_succeeded:
    log_event(
        f"[Tabular SK Analysis] pandas_mode fast code-gen attempt {attempt_number} "
        f"did not produce a result; falling back to SK-based attempts",
        level=logging.WARNING,
    )
continue
```

The SK agentic loop then runs for the remaining `max_attempts - 1` iterations, giving the model a second chance via the standard tool-calling path. `previous_tool_error_messages` is populated from the `execute_pandas` error so that the retry prompt can correct the expression.

---

## Configuration

| Setting | Value | Location |
|---|---|---|
| Model detection | `'gpt-5' in gpt_model.lower()` | `route_backend_chats.py` |
| Service ID | `"tabular-analysis"` | `AzureChatPromptExecutionSettings` |
| execute_pandas timeout | 15 seconds | `asyncio.wait_for(..., timeout=15.0)` |
| Fast path attempts | Attempt 1 only | `if pandas_mode and attempt_number == 1` |
| Available names in sandbox | `df`, `sheets`, `pd`, `re` | `safe_locals` in `execute_pandas` |

---

## Files Modified

| File | Change |
|---|---|
| `application/single_app/route_backend_chats.py` | Pandas fast path block (code-gen → execute_pandas → synthesis); elapsed-time logging |
| `application/single_app/semantic_kernel_plugins/tabular_processing_plugin.py` | `execute_pandas` kernel function; `PANDAS_FUNCTION_NAMES` tuple |
| `application/single_app/config.py` | Version bump to `0.241.007` |
