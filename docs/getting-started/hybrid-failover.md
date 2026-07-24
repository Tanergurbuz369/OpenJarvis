---
title: Local + Cloud Failover
description: Run a local model as primary and automatically fail over to free cloud models when you hit a rate limit
---

# Local + Cloud Failover

[Free OpenRouter models](openrouter-free.md) are rate-limited, and limits can
run out quickly under real use. If you have a GPU capable of running a local
model, you don't have to choose between "local only" and "cloud only" — set
an ordered **failover chain**: a local model first (no limits — it's your own
hardware), then one or more free cloud models as automatic backup.

!!! info "What actually triggers a failover"
    A hop fails over to the next one on a **retryable** error — rate limits,
    timeouts, connection failures (Ollama not running, network blip). It does
    **not** fail over on a fatal error like an invalid API key: masking a
    broken credential by silently trying the next hop would hide a
    configuration problem you actually need to fix. See
    `openjarvis.agents.errors.classify_error` for the exact classification.

## 1. Set up the primary (local) hop

Make sure Ollama is running and has the model you want as primary:

```bash
ollama pull qwen3.5:9b
```

Pick a size that fits your VRAM — see the model tiers in
[`configs/openjarvis/examples/code-assistant.toml`](https://github.com/open-jarvis/OpenJarvis/blob/main/configs/openjarvis/examples/code-assistant.toml)
for smaller/larger alternatives.

## 2. Set up the backup (cloud) hops

Follow [Free Cloud Models via OpenRouter](openrouter-free.md) to get an
`OPENROUTER_API_KEY`. Remember: OpenRouter model ids need the `openrouter/`
prefix in config (`openrouter/org/model:free`), and go through the `cloud`
engine — not a made-up `openrouter` engine key.

## 3. Configure the chain

`intelligence.fallback_chain` is a comma-separated, ordered list of
`engine:model` hops. Splitting happens on the *first* colon per entry, so
model ids that themselves contain colons (Ollama tags, OpenRouter's `:free`
suffix) parse correctly:

```toml
[engine]
default = "ollama"

[intelligence]
default_model = "qwen3.5:9b"          # keep this in sync with hop 1
fallback_chain = "ollama:qwen3.5:9b,cloud:openrouter/deepseek/deepseek-chat-v3-0324:free,cloud:openrouter/qwen/qwen-2.5-coder-32b-instruct:free"
```

A ready-made version of this lives at
[`configs/openjarvis/examples/hybrid-local-cloud-free.toml`](https://github.com/open-jarvis/OpenJarvis/blob/main/configs/openjarvis/examples/hybrid-local-cloud-free.toml) —
copy it to `~/.openjarvis/config.toml` (or pass it with `--config`).

!!! tip "Keep `default_model` in sync with hop 1"
    `default_model` is still used for display and cost-estimation purposes.
    Set it to the same model as the first hop in `fallback_chain` so they
    don't disagree.

## 4. Run it

```bash
jarvis ask "Explain quantum computing in one paragraph"
jarvis chat
```

Requests try Ollama first. If Ollama is unreachable or the model errors out
in a retryable way, the request automatically retries against the next hop —
no manual switching. Add as many cloud hops as you like; each one is tried in
order until one succeeds or the chain is exhausted.

## Notes and limits

- **Streaming responses don't fail over mid-stream.** If a hop starts
  streaming tokens and then fails partway through, the partial output has
  already reached you — switching to another hop at that point would produce
  a corrupted, mixed response, so the error surfaces instead. Failover only
  happens for errors that occur *before* any output was sent.
- **This wires into `jarvis ask`, `jarvis chat`, and `jarvis serve`.** For
  `jarvis serve` (the API server used by the browser/desktop app), the
  resilience applies to the **primary model only**
  (`intelligence.default_model` — hop 1 of the chain). Requesting that exact
  model id gets the full failover chain; requesting any other model id
  explicitly (e.g. picking a different cloud model from the UI) is served
  directly and isn't part of the chain. This is different from `jarvis ask`,
  where there's only ever one model per invocation.
- Explicitly passing `-e/--engine` on the command line always overrides the
  chain for that one call/session.
