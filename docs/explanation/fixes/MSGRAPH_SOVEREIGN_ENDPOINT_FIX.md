# MSGraphPlugin Sovereign Cloud Endpoint Fix

**Fixed in version:** 0.250.021

## Issue Description

`MSGraphPlugin` defaulted its Graph endpoint to the commercial cloud
(`https://graph.microsoft.com`) whenever a manifest did not explicitly provide an `endpoint`.
In sovereign clouds such as **GCC High**, this caused Graph requests to be sent to the wrong
cloud (`graph.microsoft.com` instead of `graph.microsoft.us`), which fails because a GCC-H app
can only reach the sovereign `.us` Graph surface.

This was a **general plugin bug**, not specific to any single feature. Any code path that
instantiates `MSGraphPlugin` without an explicit endpoint (for example, reusing the plugin
directly rather than from a fully configured action manifest) would target the commercial
endpoint in a GCC High deployment.

## Root Cause

`MSGRAPH_DEFAULT_ENDPOINT` in `functions_msgraph_operations.py` is hardcoded to
`https://graph.microsoft.com`, and `MSGraphPlugin.__init__` used it verbatim as the fallback:

```python
self._endpoint = str(self.manifest.get("endpoint") or self.DEFAULT_ENDPOINT).rstrip("/")
```

The deployment already exposes a sovereign-aware helper, `get_graph_base_url()` in
`functions_authentication.py`, which honors `CUSTOM_GRAPH_URL_VALUE` and `AZURE_ENVIRONMENT`,
but the plugin never consulted it.

## Files Modified

- `application/single_app/semantic_kernel_plugins/msgraph_plugin.py`
  - Imported `get_graph_base_url` from `functions_authentication`.
  - Added module-level `_resolve_default_graph_endpoint()` that derives the Graph host root
    from `get_graph_base_url()`. Because the plugin appends `/v1.0/...` paths itself, the
    helper strips a trailing `/v1.0`, leaving the host root (e.g. `https://graph.microsoft.us`).
    Falls back to the commercial default if the base URL cannot be resolved.
  - `MSGraphPlugin.__init__` now uses `_resolve_default_graph_endpoint()` as the fallback
    instead of the hardcoded commercial constant.
- `application/single_app/functions_chief_of_staff.py`
  - Removed the feature-local `_resolve_graph_endpoint()` workaround (now redundant) and
    reverted `load_graph_briefing_data()` to a plain `MSGraphPlugin()` instantiation, which
    now resolves the correct endpoint automatically.
- `application/single_app/config.py` — version bump to `0.250.021`.

## Behavior

- **Commercial cloud:** `get_graph_base_url()` returns `https://graph.microsoft.com/v1.0`, so
  the resolved host root remains `https://graph.microsoft.com` — no change.
- **GCC High (`AZURE_ENVIRONMENT=usgovernment` or `CUSTOM_GRAPH_URL_VALUE` set):** the plugin
  now targets `https://graph.microsoft.us` by default.
- An explicit `endpoint` in a plugin/action manifest still takes precedence, so existing
  configured actions are unaffected.

## Validation

- Chief of Staff functional test suite passes (`functional_tests/test_chief_of_staff_briefing.py`).
- Live Graph calls in a GCC High tenant could not be exercised in this environment; the change
  is verified by inspection and the shared endpoint-resolution logic.
