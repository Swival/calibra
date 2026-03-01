# Campaign Configuration

Campaigns are defined in TOML files, typically stored in `experiments/`.

## Minimal config

The smallest working config needs a campaign name, a tasks directory, one model, and one set of agent instructions:

```toml
[campaign]
name = "minimal"
tasks_dir = "tasks"

[[matrix.model]]
provider = "anthropic"
model = "claude-sonnet-4.6"
label = "sonnet"

[[matrix.agent_instructions]]
label = "default"
agents_md = "AGENTS.md"
```

The three optional dimensions (skills, mcp, environment) get defaults: `skills=none`, `mcp=none`, `environment=base`.

## [campaign] section

Top-level campaign settings.

| Field         | Type   | Default    | Description                                                                                         |
| ------------- | ------ | ---------- | --------------------------------------------------------------------------------------------------- |
| `name`        | string | *required* | Campaign identifier. Used in output paths.                                                          |
| `description` | string | `""`       | Human-readable description.                                                                         |
| `tasks_dir`   | string | *required* | Path to the tasks directory (relative to config file or absolute).                                  |
| `repeat`      | int    | `1`        | Number of times to repeat each variant+task pair. Higher values give better statistical confidence. |
| `max_turns`   | int    | `50`       | Maximum turns the agent can take per trial.                                                         |
| `timeout_s`   | int    | `300`      | Wall-clock timeout per trial in seconds.                                                            |
| `seed`        | int    | `42`       | Base seed for deterministic trial seeds.                                                            |

Here's an example using most of these fields:

```toml
[campaign]
name = "model-shootout"
description = "Compare three models on Python coding tasks"
tasks_dir = "tasks"
repeat = 5
max_turns = 30
timeout_s = 180
seed = 123
```

## Matrix dimensions

The matrix defines what you're testing. Calibra takes the Cartesian product of all dimensions to produce variants.

### [[matrix.model]] (required)

At least one model entry is required. Each entry specifies a provider, a model identifier, and a label. You can also attach per-model session options either directly on the model entry or via an inline `session` sub-table (see [Session options](#session-options) below).

| Field                | Type   | Description                                                       |
| -------------------- | ------ | ----------------------------------------------------------------- |
| `provider`           | string | Provider name (e.g., `"anthropic"`, `"openrouter"`)               |
| `model`              | string | Model identifier (e.g., `"claude-sonnet-4.6"`)                    |
| `label`              | string | Unique label within models (used in variant names and file paths) |
| `session`            | table  | Per-model session option overrides (optional, see below)          |
| *any session option* | varies | Session options can also be placed directly on the model entry    |

```toml
[[matrix.model]]
provider = "anthropic"
model = "claude-sonnet-4.6"
label = "sonnet"

[[matrix.model]]
provider = "anthropic"
model = "claude-haiku-4.5"
label = "haiku"

[[matrix.model]]
provider = "lmstudio"
model = "qwen3.5-35b-a3b"
label = "qwen"
base_url = "http://max.local:1234"

[[matrix.model]]
provider = "openrouter"
model = "openai/gpt-5.3-codex"
label = "codex"
session = { extra_body = { chat_template_kwargs = { enable_thinking = false } } }
```

Session options placed directly on the model entry (like `base_url` above) are merged with the `session` sub-table. If the same key appears in both, the `session` sub-table wins.

### [[matrix.agent_instructions]] (required)

At least one entry is required. This controls the `AGENTS.md` file copied into each trial workspace.

| Field       | Type   | Description                      |
| ----------- | ------ | -------------------------------- |
| `label`     | string | Unique label within instructions |
| `agents_md` | string | Path to the AGENTS.md file       |

```toml
[[matrix.agent_instructions]]
label = "default"
agents_md = "agents/default.md"

[[matrix.agent_instructions]]
label = "detailed"
agents_md = "agents/detailed-instructions.md"
```

### [[matrix.skills]] (optional)

Skill directories available to the agent. If omitted, defaults to a single entry with label `"none"` and no skills.

| Field         | Type         | Default | Description                |
| ------------- | ------------ | ------- | -------------------------- |
| `label`       | string       |         | Unique label within skills |
| `skills_dirs` | list[string] | `[]`    | Paths to skill directories |

```toml
[[matrix.skills]]
label = "none"
skills_dirs = []

[[matrix.skills]]
label = "full"
skills_dirs = ["skills/coding", "skills/testing"]
```

### [[matrix.mcp]] (optional)

MCP server configurations. If omitted, defaults to a single entry with label `"none"` and no config.

| Field    | Type   | Default | Description                            |
| -------- | ------ | ------- | -------------------------------------- |
| `label`  | string |         | Unique label within mcp                |
| `config` | string | `""`    | Path to MCP config file (TOML or JSON) |

```toml
[[matrix.mcp]]
label = "none"
config = ""

[[matrix.mcp]]
label = "with-search"
config = "mcp/search-server.toml"
```

### [[matrix.environment]] (optional)

File overlays applied to the workspace after copying `env/` files. If omitted, defaults to a single entry with label `"base"` and no overlay.

| Field     | Type   | Default | Description                      |
| --------- | ------ | ------- | -------------------------------- |
| `label`   | string |         | Unique label within environments |
| `overlay` | string | `""`    | Path to overlay directory        |

```toml
[[matrix.environment]]
label = "base"
overlay = ""

[[matrix.environment]]
label = "with-config"
overlay = "envs/production-config"
```

Files in the overlay directory are copied on top of the workspace, overwriting any files from `env/` that have the same name. The overlay is applied after `env/` but before `AGENTS.md`.

## Variant labels

Each variant gets a label by joining dimension labels with underscores in a fixed order: `{model}_{agent_instructions}_{skills}_{mcp}_{environment}`. So with `model=sonnet`, `agent_instructions=default`, `skills=full`, `mcp=none`, `environment=base`, the resulting label is `sonnet_default_full_none_base`. These labels are used in file paths, API endpoints, and filter expressions.

## [budget] section

Controls total resource usage across all trials.

| Field                    | Type  | Default          | Description                                    |
| ------------------------ | ----- | ---------------- | ---------------------------------------------- |
| `max_total_tokens`       | int   | `0` (disabled)   | Cancel remaining trials after this many tokens |
| `max_cost_usd`           | float | `0.0` (disabled) | Cancel remaining trials after this cost        |
| `require_price_coverage` | bool  | `false`          | Require `prices.toml` entries for all models   |

```toml
[budget]
max_cost_usd = 50.0
require_price_coverage = true
```

When a budget limit is hit, Calibra cancels all remaining trials and reports which limit was exceeded.

### prices.toml

If you use budget tracking or `require_price_coverage`, create a `prices.toml` file alongside your campaign config:

```toml
[prices]
"anthropic/claude-sonnet-4.6" = 3.0
"anthropic/claude-haiku-4.5" = 0.25
"openrouter/openai/gpt-5.3-codex" = 1.25
```

Keys are `"provider/model"` strings. Values are cost per 1,000 tokens. Calibra converts these to `(provider, model)` tuples internally.

## [retry] section

Controls retry behavior per failure class. Each failure class has its own retry limit.

| Field            | Type  | Default | Description                                            |
| ---------------- | ----- | ------- | ------------------------------------------------------ |
| `infra`          | int   | `2`     | Retries for infrastructure errors (OS, permissions)    |
| `provider`       | int   | `3`     | Retries for provider errors (rate limits, 429/502/503) |
| `tool`           | int   | `1`     | Retries for tool errors                                |
| `timeout`        | int   | `0`     | Retries for timeouts                                   |
| `task`           | int   | `0`     | Retries for task failures (wrong answer)               |
| `backoff_base_s` | float | `1.0`   | Base seconds for exponential backoff                   |
| `backoff_max_s`  | float | `60.0`  | Maximum backoff seconds                                |

```toml
[retry]
provider = 5
timeout = 1
backoff_base_s = 2.0
backoff_max_s = 120.0
```

Backoff formula: `min(base * 2^(attempt-1), max)` seconds between retries.

See [Advanced Topics](advanced.md) for details on failure classification.

## [sampling] section

Controls how many variants to actually run from the full matrix.

| Field          | Type   | Default         | Description                                          |
| -------------- | ------ | --------------- | ---------------------------------------------------- |
| `mode`         | string | `"full"`        | Sampling mode: `"full"`, `"random"`, or `"ablation"` |
| `max_variants` | int    | `0` (unlimited) | Maximum number of variants to run                    |

```toml
[sampling]
mode = "ablation"
max_variants = 20
```

See [Advanced Topics](advanced.md) for details on each sampling mode.

## [[constraints]] section

Constraints exclude specific variant combinations from the matrix. Each constraint has a `when` table (conditions that must all match) and an `exclude` table (additional dimensions to check). A variant is excluded only if it matches both `when` and `exclude`.

```toml
[[constraints]]
when = { model = "haiku" }
exclude = { skills = "full" }
```

This removes all variants where `model=haiku` AND `skills=full`. Useful when the full skill set might be too complex for a smaller model.

Multiple constraints can be stacked:

```toml
[[constraints]]
when = { model = "haiku" }
exclude = { skills = "full" }

[[constraints]]
when = { environment = "production" }
exclude = { mcp = "none" }
```

## [session] options

The `[session]` table lets you pass additional parameters to Swival's `Session` constructor. These control agent behavior that isn't part of the matrix, things like command allowlists, temperature, API keys, and sandbox settings. Campaign-wide defaults go in a top-level `[session]` table, while per-model overrides go either directly on the `[[matrix.model]]` entry or in an inline `session` sub-table. Per-model values are deep-merged on top of campaign defaults, so nested dicts like `extra_body` combine rather than replace.

```toml
[session]
allowed_commands = ["python", "uv", "git"]
temperature = 0.0

[[matrix.model]]
provider = "lmstudio"
model = "qwen3.5-35b-a3b"
label = "qwen"
base_url = "http://max.local:1234"

[[matrix.model]]
provider = "openrouter"
model = "z-ai/glm-5"
label = "glm"
session = { extra_body = { chat_template_kwargs = { enable_thinking = false } } }

[[matrix.model]]
provider = "anthropic"
model = "claude-sonnet-4.6"
label = "sonnet"
# inherits campaign [session] as-is
```

For the `qwen` model, the effective session options are `allowed_commands = ["python", "uv", "git"]`, `temperature = 0.0`, and `base_url = "http://max.local:1234"`. For the `glm` model, the effective options include the campaign defaults plus `extra_body`. The `sonnet` model inherits only the campaign defaults.

### Allowed options

Any `Session.__init__` parameter that isn't managed by Calibra internally:

| Option                 | Type      | Description                                       |
| ---------------------- | --------- | ------------------------------------------------- |
| `api_key`              | string    | Provider API key (overrides environment variable) |
| `base_url`             | string    | Custom API endpoint                               |
| `max_output_tokens`    | int       | Max tokens per LLM response                       |
| `max_context_tokens`   | int       | Max context window size                           |
| `temperature`          | float     | Sampling temperature                              |
| `top_p`                | float     | Nucleus sampling threshold                        |
| `allowed_commands`     | list[str] | Whitelist of shell commands the agent may run     |
| `yolo`                 | bool      | Skip command approval (see below)                 |
| `verbose`              | bool      | Enable verbose agent output                       |
| `no_skills`            | bool      | Disable skills loading                            |
| `allowed_dirs`         | list[str] | Directories the agent may read and write          |
| `allowed_dirs_ro`      | list[str] | Directories the agent may only read               |
| `sandbox`              | string    | Sandbox mode                                      |
| `sandbox_session`      | string    | Sandbox session identifier                        |
| `sandbox_strict_read`  | bool      | Strict read sandboxing                            |
| `sandbox_auto_session` | bool      | Auto-create sandbox sessions                      |
| `read_guard`           | bool      | Enable read guards                                |
| `proactive_summaries`  | bool      | Enable proactive context summaries                |
| `extra_body`           | dict      | Extra fields passed to the LLM API request body   |

### Rejected options

These parameters are set by Calibra internally and cannot appear in session options:

`base_dir`, `provider`, `model`, `max_turns`, `seed`, `history`, `skills_dir`, `mcp_servers`, `config_dir`.

### Blocked options

`system_prompt`, `no_system_prompt`, and `no_instructions` are unconditionally blocked because they conflict with the agent instructions dimension.

### yolo and allowed_commands

By default, Calibra sets `yolo=true` so the agent runs without interactive command approval. When you set `allowed_commands`, Calibra automatically flips `yolo` to `false` so the allowlist takes effect. If you explicitly set both `allowed_commands` and `yolo = true`, the allowlist becomes a no-op. Calibra will warn about this but not reject it.

### no_skills guard

Setting `no_skills = true` is allowed only when all skills variants in the matrix have empty `skills_dirs`. If any skills variant has actual directories, `no_skills` would silently neutralize the skills dimension, so Calibra rejects it.

### Type validation

Session option values are type-checked against Swival's `Session.__init__` annotations. For example, `temperature` must be a number, `allowed_commands` must be a list of strings, and `verbose` must be a boolean. Mismatches produce a clear error at config validation time.

## Complete example

Here's a realistic campaign config using most features:

```toml
[campaign]
name = "model-shootout"
description = "Compare models on Python coding tasks with different instruction styles"
tasks_dir = "tasks"
repeat = 5
max_turns = 40
timeout_s = 240
seed = 42

[session]
allowed_commands = ["python", "uv", "git"]
temperature = 0.0

[budget]
max_cost_usd = 100.0
require_price_coverage = true

[retry]
provider = 5
timeout = 1
backoff_base_s = 2.0

[sampling]
mode = "full"

[[matrix.model]]
provider = "anthropic"
model = "claude-sonnet-4.6"
label = "sonnet"

[[matrix.model]]
provider = "anthropic"
model = "claude-haiku-4.5"
label = "haiku"

[[matrix.model]]
provider = "openrouter"
model = "openai/gpt-5.3-codex"
label = "codex"
session = { extra_body = { chat_template_kwargs = { enable_thinking = false } } }

[[matrix.agent_instructions]]
label = "minimal"
agents_md = "agents/minimal.md"

[[matrix.agent_instructions]]
label = "detailed"
agents_md = "agents/detailed.md"

[[matrix.skills]]
label = "none"
skills_dirs = []

[[matrix.skills]]
label = "full"
skills_dirs = ["skills/all"]

[[matrix.environment]]
label = "base"

[[constraints]]
when = { model = "haiku" }
exclude = { skills = "full" }

# 3 models × 2 instructions × 2 skills × 1 mcp × 1 environment = 12 variants
# minus 2 (haiku+full constraint) = 10 variants
# × 5 repeats × N tasks = total trials
```
