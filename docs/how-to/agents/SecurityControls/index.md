---
layout: showcase-page
title: "NIST SP 800-53 Security Controls Agent"
permalink: /how-to/agents/SecurityControls/
menubar: docs_menu
accent: slate
eyebrow: "How-To Guide"
description: "Connect a SimpleChat agent to an Azure Function that exposes the NIST SP 800-53 Rev 5 security and privacy control catalog. Browse families, search controls, and retrieve full control text and guidance through a conversational interface."
hero_icons: ["bi-shield-lock", "bi-diagram-3", "bi-search"]
hero_pills: ["NIST SP 800-53 Rev 5", "Azure Function integration", "Compliance and control lookup"]
hero_links: [{ label: "Create agents", url: "/how-to/create_agents/", style: "primary" }, { label: "How-to index", url: "/how-to/", style: "secondary" }]
---

This guide walks you through connecting a SimpleChat agent to the Security Controls Azure Function API. Once configured, users can ask natural-language questions about NIST SP 800-53 controls and get authoritative answers backed by live API data.

<section class="latest-release-card-grid">
    <article class="latest-release-card">
        <div class="latest-release-card-icon"><i class="bi bi-filetype-yaml"></i></div>
        <h2>1. Add the OpenAPI action</h2>
        <p>Upload the provided OpenAPI spec to create a SimpleChat action that connects to the Security Controls Azure Function.</p>
        <p><a href="#step-1-create-the-action">Jump to step 1</a></p>
    </article>
    <article class="latest-release-card">
        <div class="latest-release-card-icon"><i class="bi bi-robot"></i></div>
        <h2>2. Create the agent</h2>
        <p>Create a SimpleChat agent and paste the provided instructions so it knows how and when to call each API operation.</p>
        <p><a href="#step-2-create-the-agent">Jump to step 2</a></p>
    </article>
    <article class="latest-release-card">
        <div class="latest-release-card-icon"><i class="bi bi-chat-dots"></i></div>
        <h2>3. Test and use</h2>
        <p>Try example prompts to browse control families, search by keyword, or look up individual controls by identifier.</p>
        <p><a href="#step-3-test-the-agent">Jump to step 3</a></p>
    </article>
</section>

---

## Prerequisites

- A running deployment of the Security Controls Azure Function  
  (base URL: `https://<your-function-app>.azurewebsites.us/api`)
- SimpleChat admin access to create actions and agents
- If function-level authentication is enabled, have the function key (`code` query parameter) ready

---

## Step 1: Create the action

1. In SimpleChat, go to **Admin → Actions → New Action**.
2. Set the action name to **Security Controls** (or similar).
3. Upload or paste the contents of [`open_api_specs/sample_security_controls_openapi.yaml`](open_api_specs/sample_security_controls_openapi.yaml).
4. In the spec, update the `servers.url` value to your deployed function's base URL:
   ```
   https://<your-function-app>.azurewebsites.us/api
   ```
5. **Authentication** — choose the option that matches your function app configuration:
   - **Anonymous** (no key required): remove the `security` block and `securitySchemes` from the spec before uploading.
   - **Function key**: leave the spec as-is. SimpleChat will prompt you for the key value, which is passed as the `code` query parameter.
6. Save the action. You should see four operations: `listControls`, `getSecurityControl`, `listFamilies`, `getControlsByFamily`.

---

## Step 2: Create the agent

1. In SimpleChat, go to **Admin → Agents → New Agent**.
2. Set the agent name, e.g. **NIST 800-53 Controls Assistant**.
3. Assign the **Security Controls** action created in step 1.
4. Paste the contents of [`agent_instructions/security_controls_agent_instructions.txt`](agent_instructions/security_controls_agent_instructions.txt) into the **Instructions** field.
5. Choose an appropriate model (GPT-4o recommended for structured compliance responses).
6. Save the agent.

---

## Step 3: Test the agent

Try the following prompts to verify the integration is working:

| Prompt | Expected behaviour |
|---|---|
| `List all control families` | Calls `listFamilies`, returns a table of all 20 families with prefix and count |
| `Show me all Access Control controls` | Calls `getControlsByFamily(prefix="AC")`, returns control list |
| `What does AC-2 say?` | Calls `getSecurityControl(identifier="AC-2")`, returns full text and discussion |
| `Find controls about encryption` | Calls `listControls(description="encrypt")`, returns paginated results |
| `Explain SI-4(2)` | Calls `getSecurityControl(identifier="SI-4(2)")`, returns enhancement detail |
| `What controls cover multi-factor authentication?` | Calls `listControls(description="multi-factor")` |

---

## API operations reference

| Operation | Endpoint | Purpose |
|---|---|---|
| `listFamilies` | `GET /families` | List all 20 control families with prefix, name, and control count |
| `getControlsByFamily` | `GET /families/{prefix}` | List all controls in a family by two-letter prefix (e.g. AC, SI) |
| `listControls` | `GET /controls` | Search controls by name or description text, with pagination |
| `getSecurityControl` | `GET /controls/{identifier}` | Retrieve full control text, discussion, and related controls |

---

## Supporting assets

<section class="latest-release-card-grid">
    <article class="latest-release-card">
        <div class="latest-release-card-icon"><i class="bi bi-filetype-yaml"></i></div>
        <h2>OpenAPI spec</h2>
        <p>Ready-to-upload YAML spec for the Security Controls Azure Function, including all four endpoints and optional function-key authentication.</p>
        <p><a href="open_api_specs/sample_security_controls_openapi.yaml">View spec</a></p>
    </article>
    <article class="latest-release-card">
        <div class="latest-release-card-icon"><i class="bi bi-journal-text"></i></div>
        <h2>Agent instructions</h2>
        <p>Pre-written agent instructions that enforce immediate API calls, correct operation selection, and clear response formatting for compliance use cases.</p>
        <p><a href="agent_instructions/security_controls_agent_instructions.txt">View instructions</a></p>
    </article>
</section>

---

## Notes

- The NIST SP 800-53 Rev 5 catalog contains approximately 1,000 controls and enhancements across 20 families.
- The `listControls` endpoint returns 50 results per page by default (maximum 200). For families with many controls (e.g. SC, SA), the agent will paginate automatically.
- Control identifiers are case-insensitive (`ac-1`, `AC-1`, and `Ac-1` are equivalent).
- This guide covers single-action, single-agent setup. For multi-agent patterns (e.g. a compliance review agent paired with a controls lookup agent), see the [two-agent ServiceNow guide](/how-to/agents/ServiceNow/two_agent_setup/) for a reference pattern.
