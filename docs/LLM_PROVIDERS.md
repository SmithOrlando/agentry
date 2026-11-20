# LLM providers

`app/llm/providers.py` holds one client per API shape:

| Provider id | Client | Endpoint (default base URL) | Auth header |
|---|---|---|---|
| `openai` | OpenAICompatible | `https://api.openai.com/v1/chat/completions` | `Authorization: Bearer` |
| `deepseek` | OpenAICompatible | `https://api.deepseek.com/v1/chat/completions` | Bearer |
| `qwen` | OpenAICompatible | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions` (mainland China accounts: set base URL `https://dashscope.aliyuncs.com/compatible-mode/v1`) | Bearer |
| `openai_compatible` | OpenAICompatible | **base URL required**: Azure (via proxy), OpenRouter, Ollama `http://host:11434/v1`, vLLM, LM Studio… | Bearer |
| `anthropic` | Anthropic | `https://api.anthropic.com/v1/messages`, `anthropic-version: 2023-06-01` | `x-api-key` |
| `gemini` | Gemini | `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` | `x-goog-api-key` |
| `mock` | Mock | **tests only** (needs `ENABLE_TEST_TOOLS=true`): echoes the first retrieved source; `[[FAIL]]` in the message raises | — |

`list_models()` (used by **Test key**) calls each provider's models endpoint.

## Which model answers? (`app/llm/router.py`)
1. Agent's own override (Settings › Models › Per-agent model), if its provider has a saved key
2. Workspace model, if **Model source = Your own API key**
3. Hidden platform default (`PLATFORM_LLM_*` env), used first when source = Platform, or as fallback when "Fallback to platform default" is on

Each failure is logged at WARNING with the provider's message. If all fail: WhatsApp chats get a system
note ("The agent could not reply"), and the Playground returns 502 with the reasons.

## Prompt shape (`services/agents.py::build_messages`)
```
system: <agent instructions with {business} replaced>
        Rules: reply in customer's language… use only sources… WhatsApp: short, plain text…
               if a human is needed reply exactly [HANDOFF]… never discuss: <topics>
        Knowledge sources:
        <source file="FAQ.docx" where="Shipping">…chunk text…</source> ×k
user/assistant: last 12 turns
user: <current message>
```
`[HANDOFF]` in a model reply is caught by the pipeline and turns into a human handoff. It is never sent to the customer.

## Adding a provider
1. Write a class with `chat(messages, model, temperature, max_tokens) -> LLMResult` and `list_models()`. Raise `LLMError` for any failure, and never put the key in the error text.
2. Register it in `make_client()`, `PROVIDERS` and `PROVIDER_LABELS`.
3. Migration: widen the `provider_keys.provider` CHECK constraint (MAINTENANCE.md › Widening a CHECK).
4. Add a colour in `frontend/src/views/settings/ModelsSettings.vue` (`COLORS`), and a request-shape test like `test_provider_request_shapes`.

## Costs & usage
Token counts from each response are stored in `usage_events` (`platform_tokens` vs `byok_tokens`)
and shown under Settings › Billing & usage. That's the hook for plan limits or billing.
