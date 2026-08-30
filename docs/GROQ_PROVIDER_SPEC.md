# Groq Provider Support Spec

Status: Spec only. Researcher-verified against the installed litellm (1.98.0),
the Groq models page, and the Groq OpenAI-compat docs. Nothing here is
implemented. The implementer must fulfill it and run the End-to-End Verification
Contract at the end, then report the phrase "I have verified this completely
end to end."

## Goal

Add Groq as a first-class LLM provider in the fallback chain, using only the
free models listed by the merchant, with `openai/gpt-oss-120b` as the default
active model. Groq is an OpenAI-compatible gateway, so it must route through the
existing litellm seam in `backend/src/app/llm/client.py` with no direct Groq SDK
import.

## The six free models and the routing subtlety

The merchant wants these exact model strings:

- `groq/compound`
- `groq/compound-mini`
- `openai/gpt-oss-120b`
- `openai/gpt-oss-20b`
- `qwen/qwen3.6-27b`
- `qwen/qwen3.8-27b`

These are the literal Groq wire model IDs (verified against
console.groq.com/docs/models). Groq's API accepts the model id as a single
string, so `openai/gpt-oss-120b` is one id, and `groq/compound` is one id.

### How litellm routes `groq/<x>`

Verified against litellm 1.98.0 via `get_llm_provider`:

```
groq/gpt-oss-120b      -> base https://api.groq.com/openai/v1, wire model gpt-oss-120b
groq/compound          -> base https://api.groq.com/openai/v1, wire model compound
groq/groq/compound     -> base https://api.groq.com/openai/v1, wire model groq/compound
groq/openai/gpt-oss-120b -> base https://api.groq.com/openai/v1, wire model openai/gpt-oss-120b
groq/qwen/qwen3.6-27b  -> base https://api.groq.com/openai/v1, wire model qwen/qwen3.6-27b
```

Rule: litellm strips exactly one leading `groq/` and sends the rest to Groq's
OpenAI-compatible base URL `https://api.groq.com/openai/v1`.

### Consequence

Because the merchant's model IDs themselves may begin with `openai/`, `qwen/`,
or `groq/`, every stored model must be prefixed with `groq/` at call time so the
full real id survives the strip:

| Stored UI model | Sent to litellm | Groq wire model (correct) |
| --- | --- | --- |
| `groq/compound` | `groq/groq/compound` | `groq/compound` |
| `groq/compound-mini` | `groq/groq/compound-mini` | `groq/compound-mini` |
| `openai/gpt-oss-120b` | `groq/openai/gpt-oss-120b` | `openai/gpt-oss-120b` |
| `openai/gpt-oss-20b` | `groq/openai/gpt-oss-20b` | `openai/gpt-oss-20b` |
| `qwen/qwen3.6-27b` | `groq/qwen/qwen3.6-27b` | `qwen/qwen3.6-27b` |
| `qwen/qwen3.8-27b` | `groq/qwen/qwen3.8-27b` | `qwen/qwen3.8-27b` |

So the implementation is a simple `actual_model = f"groq/{model}"` for the groq
provider. Do not try to normalize or strip provider prefixes from the stored
strings; that would corrupt ids like `openai/gpt-oss-120b`.

## Files to change

### 1. `backend/src/app/core/config.py`

Add one field to `Settings`:

- `groq_api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")`

Follow the existing pattern (anthropic/openai keys). No operations logic on
`os.environ`; it must be a Settings field.

### 2. `backend/src/app/llm/settings_store.py`

- Add `DEFAULT_MODELS["groq"]` with exactly the six model strings from the
  table above (stored in their real, unwrapped form - e.g. `groq/compound`,
  `openai/gpt-oss-120b`).
- Add a `ProviderSetting` for `groq` in `_default_state()`:
  - `name="groq"`
  - `label="Groq (Fast OpenAI-Compat, Free Models)"`
  - `enabled=True`
  - `priority=3` (insert between openrouter/anthropic and openai; exact slot is
    an operator choice but it must be below openrouter)
  - `active_model="openai/gpt-oss-120b"` (the merchant-default GPT-OSS)
  - `available_models=DEFAULT_MODELS["groq"]`
  - `has_api_key=has_groq` where `has_groq` is derived from the config key
- In `_load_or_default()`, add groq to the `key_map` dict so a persisted config
  gets an accurate `has_api_key`, exactly like the other providers.

### 3. `backend/src/app/llm/client.py`

Three coordinated edits:

- `_resolve_provider_name()`: add a clean rule for groq, e.g.
  `if lowered.startswith("groq/") or "groq" in lowered: return "groq"`.
  Place it before the openai guard. (Note: `groq/groq/compound` starts with
  `groq/`, and `groq/compound` contains `groq`, so both resolve to `groq`.)
- `configured_providers()`: add `("groq", settings.groq_api_key)` to the
  iteration so a configured Groq key shows up.
- `complete()`:
  - Add groq to the `key_map` dict: `"groq": groq_key`.
  - In both the explicit-model branch and the fallback-chain branch, when the
    resolved/routed provider is `groq`, build
    `actual_model = f"groq/{target_model}"` before the litellm call so the wire
    id is preserved. Mirror the existing openrouter special-casing structure,
    but do not let the literal `groq/` check re-enter (the stored models that
    already start with `groq/` must still be double-prefixed to
    `groq/groq/...`).

### 4. `backend/.env.example`

Add under the LLM providers section:

```
# Groq API Key (https://console.groq.com/keys) - OpenAI-compatible gateway
GROQ_API_KEY=
```

Dummy value only, never a real key.

### 5. Frontend

No change required. SettingsView renders providers generically from
`GET /api/settings/llm-config`, so the `groq` ProviderSetting appears
automatically with its label, model selector, enable toggle, and priority
reorder. Verify only.

## Notes and constraints

- Groq's OpenAI-compat surface rejects `temperature=0` (it is coerced to 1e-8)
  and does not support `logprobs`/`logit_bias`/`messages[].name`. The engine's
  default temperature is 0.2, so no special handling is needed unless a caller
  passes 0. Keep `litellm.drop_params = True` (already set) so unsupported
  params are dropped rather than erroring.
- Do not import a Groq SDK. All requests go through `litellm.acompletion`, the
  single provider seam.
- `cost_usd` comes back from litellm hidden params; Groq's free tier reports
  zero cost, which is correct. Token accounting stays integer.
- Two models are "systems" (`groq/compound`, `groq/compound-mini`) with tool
  support; the engine only needs text completion, which is compatible.
- The provider is a normal member of the fallback chain: if Groq fails (auth,
  rate limit, timeout), litellm raises and `complete()` records a failed
  telemetry row then moves to the next enabled provider. Verify fallback order
  still holds after adding groq.

## End-to-End Verification Contract

1. With `GROQ_API_KEY` set in `.env`, restart the backend and confirm the groq
   provider appears in `GET /api/settings/llm-config` with the six models,
   `has_api_key=true`, and default `openai/gpt-oss-120b`.
2. Confirm `GET /api/settings` reports groq among `configured_llm_providers`.
3. Temporarily set groq as the only enabled provider (priority 1) and trigger a
   recovery decision so `complete()` runs; confirm a successful
   `model_telemetry` row appears with `provider="groq"` and the response model
   resolves to one of the six ids.
4. Trigger a failure by setting a bogus `GROQ_API_KEY`; confirm a failed
   telemetry row is recorded and the chain falls through to the next enabled
   provider (deterministic_rules at minimum), with the planner degrading to
   rules rather than crashing.
5. Confirm each of the six model ids can be selected in the Settings UI model
   dropdown and, when selected, the litellm wire id matches the table above.
6. Run the backend test suite plus `make check` and confirm green.

Report: state which of these you have verified completely end to end.
