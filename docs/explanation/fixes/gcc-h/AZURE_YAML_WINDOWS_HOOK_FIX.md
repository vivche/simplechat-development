# azure.yaml Windows Hook Fix

**Version:** 0.238.024

## Issue

Running `azd up` on Windows fails with:

```
ERROR: Your azure.yaml file is invalid.
hook configuration for 'postprovision' is invalid, run is always required
```

And even when that error is bypassed, AZD warns:

```
Suggestion: pwsh (PowerShell 7) was not found and powershell (PowerShell 5) was
automatically used instead.
```

## Root Cause

The original `azure.yaml` only defined `posix:` shell blocks for all three hooks
(`postprovision`, `predeploy`, `postup`). This was written assuming `azd up` would only
be run from a Linux-based CI/CD pipeline (GitHub Actions, Azure DevOps, etc.).

Two problems on Windows:

1. **AZD v1.23.7+ requires a top-level `run:` or an OS-matching block.** Finding only
   `posix:` on Windows, it fails schema validation with the "run is always required" error.

2. **The `posix:` blocks use `sh` shell syntax** (bash conditionals, `export`, `set -e`,
   etc.) which are not compatible with Windows PowerShell.

## Fix

Added `windows:` blocks with PowerShell equivalents alongside each existing `posix:` block
for all three hooks in `deployers/azure.yaml`:

| Hook | What it does |
|---|---|
| `postprovision` | Runs `postconfig.py`, grants CosmosDB permissions, restarts the web app |
| `predeploy` | Builds Docker image, pushes to ACR, restarts the web app |
| `postup` | Disables public network access when private networking is enabled |

Each `windows:` block uses `shell: pwsh` (PowerShell 7) and mirrors the logic of the
corresponding `posix:` block. The `posix:` blocks are untouched, so Linux CI/CD pipelines
continue to work as before.

## Prerequisites — PowerShell 7 Required

AZD uses `pwsh` (PowerShell 7) for `windows:` hook blocks. PowerShell 5 (the built-in
Windows version) is **not sufficient** and may cause compatibility issues.

### Install PowerShell 7

```powershell
winget install --id Microsoft.PowerShell --source winget --accept-package-agreements --accept-source-agreements
```

After installation, **close and reopen your terminal**, then verify:

```powershell
pwsh --version
# Expected: PowerShell 7.5.4 (or later)
```

### Why PowerShell 7?

- `pwsh` is cross-platform and actively maintained
- PowerShell 5 (`powershell.exe`) is Windows-only and lacks some modern cmdlets
- AZD's `windows:` hook block specifically invokes `pwsh` — if not found, it falls back
  to PowerShell 5 with a warning, which may cause script failures

## Files Modified

| File | Change |
|---|---|
| `deployers/azure.yaml` | Added `windows: pwsh` blocks to `postprovision`, `predeploy`, and `postup` hooks |

## Related Fixes

- [LOCAL_ONLY_BICEP_CHANGES.md](./LOCAL_ONLY_BICEP_CHANGES.md)
- [DIAGNOSTIC_SETTINGS_AUDIT_CATEGORYGROUP_FIX.md](./DIAGNOSTIC_SETTINGS_AUDIT_CATEGORYGROUP_FIX.md)
- [OPENAI_GLOBALSTANDARD_SKU_FIX.md](./OPENAI_GLOBALSTANDARD_SKU_FIX.md)
