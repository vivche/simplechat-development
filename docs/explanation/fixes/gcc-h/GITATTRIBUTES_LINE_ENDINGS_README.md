# .gitattributes Line Endings README (GCC-H)

**Version:** 0.238.024  
**Fixed/Documented in version:** **0.238.024**

## Overview

This document explains why `.gitattributes` is important for cross-platform deployment work in this repository, especially for `azd` hooks that run on both Windows and Linux.

## Problem

When contributors work on Windows, Git can convert shell scripts from `LF` to `CRLF` during checkout/commit depending on local Git settings.

For hook scripts (for example `*.sh`), `CRLF` can break execution on Linux/bash with errors like:

- `$'\r': command not found`
- `unbound variable`
- unexpected script parse failures

## Root Cause

Without repository-level line-ending rules, behavior depends on each developer machine (`core.autocrlf`, editor defaults, etc.).

That creates inconsistent script behavior across:

- Windows local development
- Linux CI/CD runners
- Azure deployment hook execution paths

## Solution

Add and commit a repository `.gitattributes` file so line endings are enforced consistently for everyone.

Current rules used:

- `*.sh text eol=lf`
- `*.yaml text eol=lf`
- `*.yml text eol=lf`
- `*.py text eol=lf`
- `*.bicep text eol=lf`
- `*.md text`
- binary assets marked `binary`

## Why This Matters for GCC-H Deployment Work

Recent GCC-H deployment fixes involve both:

- Linux shell scripts (`deployers/bicep/*.sh`)
- Windows PowerShell scripts (`deployers/bicep/*.ps1`)

Keeping `.sh` files on `LF` prevents Windows-introduced line-ending regressions when testing/rolling out deployment fixes across environments.

## Validation Guidance

After adding `.gitattributes`:

1. Re-check script files for normalized endings (`LF` for `.sh`)
2. Re-run target deployment commands (`azd provision` / `azd up`) in the intended environment
3. Confirm hook scripts execute without line-ending related parsing errors

## Related Files

- `.gitattributes`
- `deployers/azure.yaml`
- `deployers/bicep/cosmosDb-postDeployPerms.sh`
- `deployers/bicep/cosmosDb-postDeployPerms.ps1`
- `docs/explanation/fixes/gcc-h/AZURE_YAML_WINDOWS_HOOK_FIX.md`
