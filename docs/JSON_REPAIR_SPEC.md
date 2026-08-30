# Resilient LLM Output Parsing Spec (json_repair)

Status: Spec only. Researcher-verified against the current code. LLM responses
are parsed by `backend/src/app/llm/planner.py` in `_extract_json_block` (lines
75-95): it strips thinking tags, strips markdown fences, tries `json.loads`,
then falls back to a brittle regex brace-match. This manual error handling is
exactly the fragility that the resilient parser `json_repair` removes. This spec
recommends adding it, keeping the existing safety behavior and full audit trail.
An implementer must fulfill this and run the End-to-End Verification Contract at
the end, then report the phrase "I have verified this completely end to end."

## Why

Some LLMs return malformed JSON: trailing commas, missing quotes, stray prose,
truncated or markdown-wrapped values. The current code handles only a narrow
subset by hand. `json_repair` (github.com/mangiucugna/json_repair, PyPI
`json-repair`, MIT license, pure Python, requires Python >= 3.10, drop-in
replacement for `json.loads`) repairs these syntax errors deterministically
without an extra model call, so recovery decisions still parse even when the
model output is imperfect - without spending another token or another provider
round-trip.

## Scope

This is a parsing/resilience change only. It does not touch the provider seam
(`backend/src/app/llm/client.py` is unchanged), does not change what the agent
decides, and does not weaken the deterministic fallback classifier. It improves
how the LLM's structured output is turned into a `DiagnosisResult`.

## Design

### 1. Add the dependency

Add `json-repair` (the PyPI package name; import name is `json_repair`) to the
backend `[project].dependencies` in `backend/pyproject.toml`. Python `>=3.13`
requirement already satisfies the library's `>=3.10`. Pin it (no `latest`), and
run `uv sync --all-groups` to lock it.

### 2. Harden `_extract_json_block`

In `backend/src/app/llm/planner.py` `_extract_json_block`:

- Keep the existing `thinking ... /think` reasoning-tag stripping and the
  `removeprefix("```json")` fence stripping - those are FORTX-specific and must
  stay.
- After stripping, try `json.loads` first (fast path, no change for the common
  well-formed case).
- On `JSONDecodeError`, run the text through `json_repair.loads(...)` (the
  drop-in `loads`). Accept the repaired object only if it is a `dict`.
- Keep the existing fallback path (regex brace-match, then re-raise) as a last
  resort, so behavior degrades safely and the error still propagates to the
  existing deterministic-fallback classifier when nothing parses.
- The function still must return a `dict` or raise; consumers (`plan_recovery`)
  unchanged.

### 3. Audit and idempotency

Parsing is not a money-affecting action, so no new idempotency key. But the
repair must be observable: record in the plan's audit snapshot (the existing
decision-inputs/diagnostics block in `plan_recovery`, which already logs the raw
LLM text) whether the output was well-formed or required repair and how many
fields survived. This keeps the "Persist timestamped LLM outputs" and
"audit-before-action" rules satisfied - the repair is part of the decision input.

### 4. Constraints

- Do not use `json_repair` to "fix" a rejected/censored or empty response into a
  decision; if the parsed dict is missing required fields or fails the existing
  schema-fit check, treat it as a parse failure and fall through to the
  deterministic classifier. Repair fixes syntax, never invents the decision.
- Do not import or use `json_repair` outside the `llm/` parsing path; keep the
  provider/client seam unchanged.
- Money types still enforce: any numeric decision fields (e.g. delay_hours,
  discount_bps_suggested) are validated by the existing `DiagnosisResult`
  Pydantic model after parsing; nothing money-affecting is gated on the repair
  itself succeeding.

## End-to-End Verification Contract

1. `json-repair` is a pinned dependency in `backend/pyproject.toml` and locks
   cleanly with `uv sync --all-groups`.
2. A well-formed LLM JSON response parses via the fast path with no behavioral
   change (existing decisions, existing audit snapshot fields intact).
3. A malformed response (e.g. a stray trailing comma, or a single unquoted key)
   that previously fell through to the regex fallback (or failed) now parses via
   `json_repair.loads` and yields the same decision, or clearly falls to the
   deterministic classifier when the object is not a valid dict.
4. A rejected/empty/truncated response with no parseable decision still routes to
   the deterministic fallback classifier - repair never invents a decision.
5. The audit snapshot records whether repair occurred, and the raw LLM text is
   still persisted as before.
6. `backend/src/app/llm/client.py` and all provider calls are unchanged; no
   `json_repair` import outside the parsing path.
7. Full test suite and `make check` green, including new tests for the fast path,
   the repair path, and the fail-to-fallback path.

Report: state which of these you have verified completely end to end.
