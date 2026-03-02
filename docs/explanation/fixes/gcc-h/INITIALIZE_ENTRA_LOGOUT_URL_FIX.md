# Fix: Initialize-EntraApplication.ps1 — Logout URL Bad Request (GCC-H)

## Issue Description

When running `Initialize-EntraApplication.ps1` against an Azure Government (GCC-H) tenant, the script emitted the following error before printing a misleading success message:

```
ERROR: Bad Request({"error":{"code":"BadRequest","message":"Unable to read JSON request payload.
Please ensure Content-Type header is set and payload is of valid JSON format.",...}})
SUCCESS: Logout URL configured
```

The logout URL was **not** actually configured despite the success message. The `try/catch` block swallowed the error and executed the success message unconditionally.

## Root Cause

On Windows PowerShell, passing a JSON string with curly braces directly to `az rest --body` causes the shell to mangle the argument before it reaches the Azure CLI. The PATCH body arrived at the Graph API endpoint malformed, resulting in a `BadRequest` response.

**Before (broken):**
```powershell
$body = @{ web = @{ logoutUrl = $logoutUrl } } | ConvertTo-Json -Compress

az rest --method PATCH `
    --uri "$graphUrl/v1.0/applications/$($appRegistration.id)" `
    --headers "Content-Type=application/json" `
    --body $body | Out-Null
```

## Fix Applied

Write the JSON to a temp file and use `az rest`'s native `@filepath` syntax, which bypasses PowerShell argument quoting entirely.

**After (fixed):**
```powershell
$body = @{ web = @{ logoutUrl = $logoutUrl } } | ConvertTo-Json -Compress
$tempBodyFile = [System.IO.Path]::GetTempFileName()
$body | Out-File -FilePath $tempBodyFile -Encoding utf8 -NoNewline

az rest --method PATCH `
    --uri "$graphUrl/v1.0/applications/$($appRegistration.id)" `
    --headers "Content-Type=application/json" `
    --body "@$tempBodyFile" | Out-Null

Remove-Item $tempBodyFile -ErrorAction SilentlyContinue
```

Temp file cleanup is also performed in the `catch` block so no orphaned temp files are left on failure.

## File Modified

- `deployers/Initialize-EntraApplication.ps1` — lines ~286–299 (Configure Web Settings region)

## Version

Implemented in: **v0.238.024**

## Re-run Instructions

If you encountered this error on a previous run, the script handles re-runs gracefully — it detects the existing app registration by display name and reuses it. Simply re-run with the same parameters:

```powershell
cd ./deployers
.\Initialize-EntraApplication.ps1 -AppName "<appName>" -Environment "<environment>" -AppRolesJsonPath "./azurecli/appRegistrationRoles.json"
```

## Related Issues

- See [INITIALIZE_ENTRA_PERMISSIONS_FIX.md](./INITIALIZE_ENTRA_PERMISSIONS_FIX.md) for the Graph API permissions failure on GCC-H (all 8 delegated scopes failing to add).
