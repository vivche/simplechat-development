# Auth Flow (Discussion Draft)

> The hardest and most important part of the governance story in GCC High. This captures the options,
> the recommended flow, and the open choices for the POC. Update as we converge.

## Goal

When a user asks their agent to "summarize my inbox," the runtime must call Microsoft Graph **as that
user** (delegated), touch **only that user's data** (`self-only`), and use **only the scopes the
agent's selected capabilities require** — nothing more — with everything auditable.

## Constraints (GCC High)

- Sovereign endpoints: `login.microsoftonline.us` (authority) and `graph.microsoft.us` (Graph).
- Admin consent must be granted via the **portal** (Azure CLI admin-consent is not supported on
  sovereign clouds).
- The runtime is a **separate service** (Azure Function) from the SimpleChat UI, so it cannot rely on
  SimpleChat's in-process MSAL session cache.

## The three candidate patterns

### Option A — Delegated On-Behalf-Of (OBO), runtime as its own confidential client ✅ recommended

- The **runtime** has its **own app registration** (`cos-runtime-api`) that:
  - exposes an API scope (e.g. `api://cos-runtime/access_as_user`), and
  - holds the **delegated Graph scopes = the capability-catalog superset** (Mail.Read,
    Calendars.Read, Chat.Read, …), admin-consented **once**.
- SimpleChat sends the runtime a token whose **audience is the runtime API**.
- The runtime validates it, then performs an **OBO exchange** to get a Graph token **for the user**,
  requesting **only the subset of scopes** the invoked agent needs.
- **Why this wins:** the runtime owns its own permissions (portable, decoupled), acts as the user
  (self-only by construction), and the OBO call is the exact place to enforce **least privilege per
  invocation**. The consented superset stays finite and auditable.

### Option B — App-only via managed identity ❌ rejected for POC

- Runtime uses **application** Graph permissions (e.g. `Mail.Read` as app) via its managed identity.
- **Rejected:** application permissions are tenant-wide — they break the `self-only` guarantee and the
  least-privilege governance story. Wrong tool for a "chief of staff acting for me" product.

### Option C — SimpleChat forwards a raw Graph token ❌ rejected

- SimpleChat already mints a delegated Graph token today; it could just forward it.
- **Rejected:** forwarding a token whose audience is Graph is poor hygiene, gives the runtime no way
  to re-scope per invocation, and tightly couples the two services. Defeats the decoupling goal.

## Recommended flow (Option A)

### Token hops

There are two ways to get a runtime-audience token to the runtime. Pick one for the POC:

**A1 — Single OBO (simplest, recommended for POC):**
SimpleChat requests the **runtime API scope at user login**, so the access token it already holds has
`aud = cos-runtime-api`. It forwards that token. The runtime does **one** OBO hop to Graph.

```
User ──OIDC sign-in (aud=cos-runtime-api)──► SimpleChat
SimpleChat ──Bearer token (aud=cos-runtime-api)──► Runtime /v1/agents/{id}/invoke
Runtime ──OBO(user token → Graph, scopes=subset)──► graph.microsoft.us
Graph ──self-only user data──► Runtime ──result──► SimpleChat ──► User
```

**A2 — Double OBO (cleaner separation, more moving parts):**
SimpleChat's session token has `aud = SimpleChat`. Before calling the runtime, SimpleChat does OBO to
mint a token with `aud = cos-runtime-api`, forwards it; the runtime then does a **second** OBO to
Graph. More correct in theory, but two OBO hops = more config/consent. Defer unless needed.

### Per-invocation least privilege

In the OBO call the runtime passes `scopes=[…]` = **only** the scopes mapped to the agent's selected
capabilities (from the Tool Registry). Even though the app registration is consented for the whole
superset, the **issued Graph token is scoped to just what was requested**. This is the enforcement
point named in `ARCHITECTURE.md` §3.

### Identity is derived, never trusted from the client

The runtime derives the user identity from the **validated token claims** (`oid` / `upn`), never from
a client-supplied user id. Combined with the OBO user token, this makes `self-only` structural: the
runtime can only ever reach the calling user's data.

## Runtime credential (for the OBO confidential-client call)

The OBO exchange requires the runtime to authenticate as a confidential client. Options, best-first:

1. **Federated Identity Credential (workload identity)** — the Function's **managed identity**
   federates to the `cos-runtime-api` app registration; **no secret stored**. Best for GCC High
   hardening. Slightly more setup.
2. **Certificate in Key Vault** — solid, rotation-friendly.
3. **Client secret in Key Vault / app settings** — simplest; acceptable for the POC, flag for
   replacement before production.

## Consent model recap

- Admin-consents the **finite superset** of catalog delegated scopes on `cos-runtime-api` **once**
  (via the GCC High portal).
- Every agent uses a **subset** → **no per-agent consent** ever needed.
- Adding a new catalog capability (Tier 1, platform owner) may expand the superset and require a
  one-time re-consent.

## Open choices for the POC (need your call)

1. **A1 (single OBO) vs A2 (double OBO)?** — recommend **A1** for the POC.
2. **Runtime credential:** federated identity (secretless) vs certificate vs client secret? —
   recommend **client secret in Key Vault** for the POC, FIC as the hardening path.
3. **New `cos-runtime-api` app registration** (clean/portable) vs temporarily reusing the existing
   Flask app registration? — recommend a **new registration** so the runtime owns its permissions and
   stays extractable; the trade-off is one more portal consent step.

## Implications for existing SimpleChat auth

- Today `get_valid_access_token_for_plugins()` mints the delegated Graph token inside SimpleChat.
- Under Option A, that Graph-calling responsibility **moves to the runtime**. SimpleChat's job shrinks
  to: sign the user in and obtain a **runtime-audience** token to forward. The Graph scopes currently
  on the Flask app registration would migrate to `cos-runtime-api` (or be duplicated during
  transition).
