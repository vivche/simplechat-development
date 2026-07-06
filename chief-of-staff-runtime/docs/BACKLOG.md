# Backlog (parked)

> Items deferred while we build the orchestration framework. Not blocking the build — most are
> external (consent) or hardening tasks.

## Auth / identity (parked)

- [x] **Store the `cos-runtime-poc` client secret in Key Vault.** A **dedicated COS Key Vault**
      (`kv-cos-runtime-*`) is created by [`../infra/modules/resources.bicep`](../infra/modules/resources.bicep);
      the secret value is copied in once, out of band (Bicep never stores it). The Function reads it
      via the `COS_CLIENT_SECRET` Key Vault reference. Record `<vault>/<secret>` in
      [`APP_REGISTRATION.md`](APP_REGISTRATION.md).
- [ ] **Admin consent** for `cos-runtime-api` in the GCC High tenant (portal or admin-consent URL).
- [ ] After consent: flip a test to live Graph and verify OBO returns a `self-only` token.
- [ ] **Hardening:** replace client secret with a **federated identity credential** (Function managed
      identity → app registration) so no secret is stored.
- [ ] **Deferred write scopes** (`Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`) — add to the
      catalog + one-time re-consent when write capabilities are enabled.

## SimpleChat integration (parked)

- [ ] SimpleChat requests the `api://cos-runtime-api/access_as_user` scope at login and forwards the
      runtime-audience token (see [`AUTH_FLOW.md`](AUTH_FLOW.md), option A1).
- [ ] Migrate the Graph-calling responsibility out of `get_valid_access_token_for_plugins()` into the
      runtime (or keep in SimpleChat for the POC and move later — decision pending).
- [ ] Agent Builder UI in SimpleChat (compose agent from catalog subset, POST to `/v1/agents`).

## Infra / deployment

- [x] **Bicep for the Function App + Key Vault + storage + ACR (GCC High).** Subscription-scope
      [`../infra/main.bicep`](../infra/main.bicep) + [`../infra/modules/resources.bicep`](../infra/modules/resources.bicep)
      + [`../infra/main.bicepparam`](../infra/main.bicepparam), reusing the proven `security-plugin`
      pattern (UAMI, secretless storage, RBAC Key Vault, container on a Linux plan — default **B1**
      Basic dedicated for POC cost, `planSku='EP1'` for Elastic Premium). See
      [`../DEPLOYMENT.md`](../DEPLOYMENT.md).
- [x] **CI/CD for the runtime** (own workflows, extraction-ready): the security-plugin three-workflow
      chain at the repo root — `cos-infra-deploy.yml` (arm-deploy), `cos-docker-build.yml` (ACR push),
      `cos-function-deploy.yml` (container set); Azure Government SP-JSON login, `COS_`-prefixed secrets.
- [ ] **Cosmos DB** — deferred to Phase 1 (`COS_USE_IN_MEMORY_STORES=true` for Phase 0).
- [ ] Decide federated identity vs secret before any non-POC deploy.

## Platform roadmap (from canonical scenario — see DESIGN_DISCUSSION §10–§12)

### Phase 1 — dynamic agent creation
- [ ] Agent Builder UI + `POST /v1/agents`: users compose agents from the catalog subset (no admin).

### Phase 2 — agent collaboration + approval gate
- [ ] **Workflow/orchestration plan**: Chief of Staff delegates to sub-agents (Gary/Georgia).
- [ ] **Reviewer sub-agent** pattern (e.g. Gary reviews drafts against a stored conversational-style profile).
- [ ] **Approval gate primitive** (hard, non-promptable): `send` blocked until a recorded human approval
      exists; POC collection mechanism = post a Teams approval message (approver may be the user).
- [ ] **Async / durable monitoring** (e.g. Georgia watching for replies over hours/days).
- [ ] **Conversational-style memory** capture/curation (new memory type Gary reads).

### Phase 3 — templates
- [ ] Ship starter agent packages (Chief of Staff, Meeting Prep, Security Review, …) as configuration.

### New capabilities the scenario needs (catalog + one-time re-consent)
- [ ] `teams.chat.message.read` (ChatMessage.Read) — read Teams chat message bodies.
- [ ] `teams.message.send` (ChatMessage.Send) — post summaries/notifications to Teams.
- [ ] `email.draft` (Mail.ReadWrite), `email.send` (Mail.Send) — already stubbed as disabled.
- [ ] Configurable read window (60 days vs current 48h default).

## Extraction (parked)

- [ ] When POC graduates: `git filter-repo`/`subtree split` `chief-of-staff-runtime/` to its own repo
      (procedure in [`INTEGRATION.md`](INTEGRATION.md)).
