---
title: Free Cloud Models via OpenRouter
description: Run OpenJarvis with no local GPU using OpenRouter's free-tier hosted models
---

# Free Cloud Models via OpenRouter

You can run OpenJarvis without a local GPU, without Ollama, and without a paid
API by routing through [OpenRouter](https://openrouter.ai). OpenRouter is an
OpenAI-compatible gateway to 70+ hosted models — many of which have a **free
tier** that works well for chat and coding.

OpenRouter support is built in: when `OPENROUTER_API_KEY` is set and your model
is an OpenRouter model ID, OpenJarvis routes requests to
`https://openrouter.ai/api/v1` automatically.

!!! info "Local-first is still the default"
    OpenJarvis is local-first by design. This guide is for people who want to
    get going quickly without local hardware, or who want to mix in cloud
    models. You can switch back to a local engine at any time.

## 1. Get an OpenRouter API key

1. Sign up at [openrouter.ai](https://openrouter.ai).
2. Create a key at [openrouter.ai/keys](https://openrouter.ai/keys) — it looks
   like `sk-or-...`.

## 2. Set the key in your environment

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

Add that line to your `~/.bashrc` or `~/.zshrc` so it persists across sessions.

!!! tip "Installer auto-detects the key"
    If `OPENROUTER_API_KEY` is set when you run the installer or `jarvis init`,
    OpenJarvis proposes OpenRouter as the default provider and writes it into
    `config.toml` for you. Precedence is OpenRouter > Anthropic > OpenAI >
    Google.

## 3. Point OpenJarvis at a free model

Free OpenRouter model IDs use the `org/model:free` format. OpenJarvis detects
the `/` and routes them to OpenRouter. A ready-made config lives at
[`configs/openjarvis/examples/openrouter-free.toml`](https://github.com/open-jarvis/OpenJarvis/blob/main/configs/openjarvis/examples/openrouter-free.toml):

```toml
[intelligence]
default_model = "deepseek/deepseek-chat-v3-0324:free"
provider = "openrouter"

[agent]
default_agent = "simple"
```

Copy it to `~/.openjarvis/config.toml` (or pass it with `--config`).

## 4. Run it

```bash
jarvis ask "Explain quantum computing in one paragraph"
jarvis chat                  # interactive session
jarvis serve                 # API server for the browser / desktop app
```

## Choosing a free model

The free catalog changes over time, and free models are rate-limited. Browse the
current free list (price = $0) at
[openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0).
Some popular free choices:

| Model ID | Good for |
|---|---|
| `deepseek/deepseek-chat-v3-0324:free` | General + coding |
| `deepseek/deepseek-r1:free` | Reasoning |
| `meta-llama/llama-3.3-70b-instruct:free` | General |
| `qwen/qwen-2.5-coder-32b-instruct:free` | Coding |
| `google/gemini-2.0-flash-exp:free` | Fast, long context |

!!! warning "Free tiers change and are rate-limited"
    Model availability and rate limits on OpenRouter's free tier can change
    without notice. If a model stops responding, pick another `:free` model from
    the catalog above.
