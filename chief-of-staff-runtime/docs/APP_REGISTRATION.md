# App Registration — cos-runtime-api

> Identity record for the Chief of Staff Runtime's Entra app registration. **No secrets are stored in
> this file.** The client secret lives only in Key Vault.

## Identifiers

| Field | Value |
|-------|-------|
| Display name | `cos-runtime-api` |
| Cloud | Azure US Government (GCC High) |
| Tenant ID | `03f141f3-496d-4319-bbea-a3e9286cab10` (FedAIRS) |
| Application (client) ID | `bed646c0-7953-4871-8b74-456a5883c283` |
| Application object ID | `846202a8-d38d-4a7c-ab44-4e1982b5eca6` |
| Service principal object ID | `898b2d54-c102-4188-a86d-c0ec3f770a1b` |
| Application ID URI | `api://bed646c0-7953-4871-8b74-456a5883c283` |
| Exposed scope | `access_as_user` (id `7404b803-276b-45b0-a246-3eda2bca731d`) |
| Sign-in audience | `AzureADMyOrg` (single tenant) |

## Delegated Microsoft Graph permissions (read-only POC set)

Consent to these = the finite capability-catalog superset for the POC. Every agent uses a **subset**.

| Scope | GUID | Purpose |
|-------|------|---------|
| `openid` | `37f7f235-527c-4136-accd-4a02d197296e` | Sign-in |
| `profile` | `14dad69e-099b-42c9-810b-d002981feec1` | Sign-in |
| `offline_access` | `7427e0e9-2fba-42fe-b0c0-848c9e6a8182` | Refresh tokens |
| `User.Read` | `e1fe6dd8-ba31-4d61-89e7-88639da4683d` | Baseline profile |
| `Mail.Read` | `570282fd-fa5c-430d-a7fd-fc8dc98a9dca` | Email — Read / Triage capability |
| `Calendars.Read` | `465a38f9-076d-4033-b4d0-fea877edaa4a` | Calendar — Read / Prep capability |
| `Chat.Read` | `f501c180-9344-439a-bca0-6cbf209fd270` | Teams — Chat Read capability |

Deferred (NOT yet requested — add via a one-time re-consent when write capabilities are enabled):
`Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`.

## Client secret

- A client secret named `cos-runtime-poc` (1-year expiry) was created for the OBO confidential-client call.
- **The secret value is stored only in Key Vault** — never in this repo.
- Key Vault secret reference: _TODO — record `<vault-name>/<secret-name>` once stored._
- Hardening path: replace the secret with a **federated identity credential** (Function managed
  identity → this app registration) so no secret is stored. See [`AUTH_FLOW.md`](AUTH_FLOW.md).

## Admin consent

Requires a Privileged Role / Global Admin in the GCC High tenant.

- Portal: Entra admin center → App registrations → `cos-runtime-api` → API permissions →
  **Grant admin consent for FedAIRS Azure Gov - GCCHigh**.
- Or admin-consent URL (sovereign authority):
  ```
  https://login.microsoftonline.us/03f141f3-496d-4319-bbea-a3e9286cab10/adminconsent?client_id=bed646c0-7953-4871-8b74-456a5883c283
  ```

> Note: `az ad app permission admin-consent` is **not supported on sovereign clouds** — use the portal
> or the URL above.

## Consent status

- [ ] Admin consent granted (date / by whom): _pending_
