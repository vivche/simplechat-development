# Tabular Plugin: GPT-4.1 vs GPT-5.1 Evaluation

**Version documented:** 0.241.014  
**Branch tested:** `fix/tabular-plugin-return-columns-pagination-autotrim`  
**Test file:** `NIST_SP-800-53_rev5_catalog_load` (1,189 rows)  
**Purpose:** Validate the slot-exhaustion and schema-rediscovery problems described in [TABULAR_PLUGIN_REDESIGN_GPT51.md](./TABULAR_PLUGIN_REDESIGN_GPT51.md) using real queries before and after the `execute_pandas` redesign.

---

## Test Configuration

| Parameter | Value |
|---|---|
| `maximum_auto_invoke_attempts` (force_tool_use) | 8 |
| `maximum_auto_invoke_attempts` (auto) | 7 |
| Auto-trim limit | 50,000 chars |
| Default page size (`filter_rows`) | 100 rows |
| Dataset | NIST SP 800-53 Rev 5 catalog |
| Row count | 1,189 |

---

## Test 1 — "Give me a CSV table of all security control identifiers and name"

**Intent:** Full export of two columns across all 1,189 rows.  
**Minimum slots required:** 1 (schema) + 12 (pagination at 100 rows/page) = **13 slots**  
**Slot cap:** 7

### GPT-4.1 — Excel file (`.xlsx`)

**Result:** ❌ Partial — model apologised for limitation

> *"Due to a technical limitation in directly exporting only the identifier and name columns at this moment, I can provide a sample of the data in CSV format here. If you need the full list, I can supply it in multiple smaller pieces or explain how to retrieve it manually."*

**Root cause:** Slot exhaustion. The model consumed all 7 slots on pagination (schema + ~6 pages = ~600 rows) before reaching a synthesis step. It had received roughly 50% of the data and was forced to stop. The model masked the tool failure with user-friendly language but the data was genuinely incomplete.

**Tool call trace (inferred from slot cap):**
```
Slot 1: describe_tabular_file()           → 1,189 rows, columns discovered
Slot 2: filter_rows(start_row=0)          → rows 0–99,   has_more=true
Slot 3: filter_rows(start_row=100)        → rows 100–199, has_more=true
Slot 4: filter_rows(start_row=200)        → rows 200–299, has_more=true
Slot 5: filter_rows(start_row=300)        → rows 300–399, has_more=true
Slot 6: filter_rows(start_row=400)        → rows 400–499, has_more=true
Slot 7: filter_rows(start_row=500)        → rows 500–599, has_more=true
[CEILING HIT — auto-invoke stopped at 7]
```

**Verdict:** Architecture failure. Not a model quality issue — GPT-4.1 cannot succeed at this query regardless of how well it reasons, because the slot ceiling is hit before enough data is retrieved.

---

### GPT-4.1 — CSV file (`.csv`)

**Result:** ⚠️ Data complete, display truncated

> *"Here is a CSV table of all security control identifiers and their names based on the NIST SP 800-53 Revision 5 catalog: [AC-1 through AC-2(8) shown] ... This table contains all 1189 security controls, starting with the examples above. If you need the complete CSV file with all rows, please indicate and I can provide the full list..."*

**Root cause:** The `identifier` + `name` columns from the CSV are compact (~30 chars/row × 1,189 rows ≈ 36K chars), which fits under the 50K auto-trim limit in a **single `filter_rows` call**. The model retrieved all data in ~2 slots but then chose to truncate its *display* — a response formatting choice, not a tool failure.

**Tool call trace (inferred):**
```
Slot 1: describe_tabular_file()           → 1,189 rows, columns discovered
Slot 2: filter_rows(return_columns=["identifier","name"], start_row=0)
         → all 1,189 rows fit in one page (36K chars < 50K limit), has_more=false
```

**Verdict:** Tool succeeded. The truncation is the model deciding not to dump 1,189 rows of inline text — which is arguably correct UX. The user asked for a CSV *table* and the model offered to continue if needed.

---

### GPT-4.1 — Summary

| File type | Tool outcome | Data completeness | User experience |
|---|---|---|---|
| `.xlsx` | ❌ Slot exhaustion | ~50% (600/1,189 rows) | Misleading partial answer |
| `.csv` | ✅ All data retrieved | 100% (1,189/1,189 rows) | Display truncated but data available |

**Key insight:** The same query, same model, same dataset — different outcome based purely on whether the data fit in one page. The Excel path forces an extra schema overhead that consumes a slot before pagination begins, and the richer workbook metadata increases per-call token cost, both of which tighten the ceiling.

---

## Test 2 — GPT-5.1, same query, OLD architecture (no `execute_pandas`)

**Branch:** `fix/tabular-plugin-return-columns-pagination-autotrim` (v0.241.014 — same branch as GPT-4.1 tests, no `execute_pandas`)  
**Purpose:** Isolate whether the slot-exhaustion problem is model-specific or architectural.

### GPT-5.1 — Excel file (`.xlsx`)

**Result:** ❌ Partial — more rows than GPT-4.1 but still incomplete

GPT-5.1 returned controls from AC-1 through approximately CP-18 (~800–900 of 1,189 rows) before hitting the ceiling. Its closing note:

> *"Note: This CSV includes the rows that are present in the computed tabular results shared in this context. The underlying workbook contains additional controls beyond CP-18 that are not included in the truncated data I have here, so I cannot list those further entries. (Source: NIST_SP_800-53_rev5_catalog_load.xlsx, Page: N/A - tabular export)"*

**Root cause:** Same slot ceiling (7), same architectural constraint. GPT-5.1 made smarter tool calls — likely requesting larger page sizes or specifying `return_columns=["identifier","name"]` explicitly, which kept each page payload smaller and let it retrieve more rows per slot. But 7 slots is still 7 slots; it exhausted them before reaching the end.

**Key differences from GPT-4.1:**

| Aspect | GPT-4.1 | GPT-5.1 |
|---|---|---|
| Rows retrieved | ~600 (AC–AU range) | ~800–900 (AC–CP range) |
| Tone on failure | Vague apology ("technical limitation") | Precise acknowledgement (names the last control: CP-18) |
| Self-awareness | Low — implied it had all data | High — explicitly said more entries exist |
| Tool efficiency | Standard page calls | Smarter column filtering or larger page requests |

**Verdict:** Still an architecture failure, not a model quality issue. GPT-5.1 mitigates the symptom (gets more rows per slot) but cannot overcome the ceiling. The failure mode is identical — it just runs out of slots later.

---

### GPT-5.1 — CSV file (`.csv`)

**Result:** ⚠️ Third failure mode — model response token limit

GPT-5.1 received all 1,189 rows from the tool (same as GPT-4.1 + CSV — the compact `identifier`+`name` columns fit under the 50K auto-trim limit in a single call). Unlike GPT-4.1, which received all the data but chose to display only a short sample and offer to continue, GPT-5.1 attempted to output *everything* inline as a wall of CSV text.

The response dumps hundreds of rows — AC through CP families are visible — then ends abruptly around `CP-14, Alternative Physical Protection` with no closing note. The last control visible is in the CP family; the remaining families (IA, IR, MA, MP, PE, PL, PM, PS, PT, RA, SA, SC, SI, SR) are absent.

**Root cause:** Model response token/character output limit. The tool succeeded — all 1,189 rows were retrieved. The failure is that GPT-5.1 attempted to write every row into its response verbatim and hit the per-response output cap before finishing. This is entirely distinct from slot exhaustion.

**Comparison with GPT-4.1 + CSV:**

| Aspect | GPT-4.1 + CSV | GPT-5.1 + CSV |
|---|---|---|
| Tool outcome | ✅ All 1,189 rows retrieved | ✅ All 1,189 rows retrieved |
| Model display choice | Show ~10 rows, offer to continue | Attempt to dump all rows inline |
| Failure point | Model verbosity (display truncation) | Model output token limit |
| Rows visible to user | ~10 (AC-1 to AC-2(8)) | ~600–700 (AC-1 to CP-14) |
| Closing message | "This table contains all 1189 controls..." ✅ | Abrupt cutoff, no note ❌ |
| User experience | Conservative but informative | Aggressive but incomplete and confusing |

GPT-4.1's conservative display was actually *better UX* here — it was honest about having all 1,189 rows and offered to continue in chunks. GPT-5.1's attempt to dump everything inline resulted in a silent truncation with no acknowledgement that the output is incomplete.

**Verdict:** Tool architecture succeeded for both models on CSV. The failure is purely in model output behaviour, not retrieval. This is a separate problem from slot exhaustion and would not be fixed by `execute_pandas`.

---

### GPT-5.1 — Summary (old architecture, both files tested)

| File type | Tool outcome | Data completeness | User experience |
|---|---|---|---|
| `.xlsx` | ❌ Slot exhaustion | ~75% (~900/1,189 rows) | Partial but transparent (names last control: CP-18) |
| `.csv` | ✅ All data retrieved | 100% in tool, ~60% displayed | Silent truncation — no closing note, no offer to continue |

---

## Side-by-Side Comparison (GPT-4.1 vs GPT-5.1, OLD architecture)

| Test | GPT-4.1 | GPT-5.1 |
|---|---|---|
| Excel — branch | fix/tabular-plugin-return-columns-pagination-autotrim | fix/tabular-plugin-return-columns-pagination-autotrim |
| Excel — slots used | 7 (ceiling hit) | 7 (ceiling hit) |
| Excel — rows returned to model | ~600 / 1,189 (~50%) | ~900 / 1,189 (~75%) |
| Excel — failure type | Slot exhaustion | Slot exhaustion |
| Excel — answer correct | ❌ No | ❌ No |
| Excel — failure language | Vague apology | Precise acknowledgement (names last control) |
| CSV — slots used | ~2 | ~2 |
| CSV — rows returned to model | 1,189 / 1,189 (100%) | 1,189 / 1,189 (100%) |
| CSV — failure type | Model display choice (conservative) | Model output token limit (aggressive) |
| CSV — rows displayed to user | ~10 + offer to continue | ~600–700, then silent cutoff |
| CSV — answer correct | ⚠️ Technically yes, practically no | ❌ No — silently incomplete |

**Three distinct failure modes identified across these four tests:**

1. **Slot exhaustion (Excel, both models)** — architectural ceiling; cannot retrieve all data regardless of model quality. The only fix is `execute_pandas` collapsing N pagination calls into one.
2. **Model display truncation (GPT-4.1 + CSV)** — data fully retrieved, model chose to show a sample. Fixable with a system prompt instruction to output all retrieved rows.
3. **Model output token limit (GPT-5.1 + CSV)** — data fully retrieved, model tried to output everything and hit per-response cap. The tool result was correct; the failure is in response generation. Fixable with the same system prompt instruction (paginate in tool calls, not in the response text).

**Conclusion from old-architecture tests:** Increasing `maximum_auto_invoke_attempts` would only delay the Excel failure mode. A 1,189-row full export needs ~13 pagination slots which no reasonable cap can accommodate. The correct fix for Excel is `execute_pandas`. The CSV failure modes are model output behaviour issues, not architecture issues.

---

## Additional Tests to Run

These queries are designed to stress the slot ceiling in different ways:

| # | Query | Why it's interesting |
|---|---|---|
| 3 | "For each control family, count how many controls exist" | Group-by aggregation — single tool should handle it |
| 4 | "List all HIGH baseline controls that are not in the AC family" | Filter + exclusion — tests `filter_rows` with multi-condition |
| 5 | "What percentage of controls have a non-empty 'related' field?" | Requires count + conditional — likely 3+ tool calls today |
| 6 | "Give me all controls for the AU and IR families, sorted by identifier" | Multi-family filter + sort — tests pagination on medium result set |
| 7 | Follow-up on same file: "Now just the SA family" | Tests schema rediscovery cost on second turn |

---

## Notes

- Logs attached for GPT-4.1 tests show only app startup (plugin decoration) — the actual tool call trace does not appear in stdout at default log level. Enable `DEBUG` logging or check Application Insights to see per-slot call details.
- The NIST catalog has 5 columns: `identifier`, `name`, `control_text`, `discussion`, `related`. The `control_text` column alone averages ~500 chars/row, making full-row exports always exceed auto-trim even with `execute_pandas`.
