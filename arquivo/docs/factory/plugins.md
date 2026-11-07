# Plugin system

Everything is a plugin **except the core**, and the core is video generation. This file is normative.

## Core, host and plugins

| Part | What it is | Removable? |
|---|---|---|
| **Core: video engine** | `simplicio_video`: contract → voice → render → edit, templates, motion patterns, voice providers | no: it is the product |
| **Core: plugin host** | `simplicio_video.registry`, `.plugins` (manifest, loader, lifecycle), `doctor`, `install`, `update`, `plugin` commands | no |
| **SDK** | `simplicio_factory.contracts` and `.testkit`: models, Protocols, fakes, contract suites | no: plugin authors depend on it |
| **Host services** | `simplicio_factory.{workspace,store,policy,security,runner}`: store and events, gates, auth, the simple loop runner | **no, on purpose**: they enforce the human gates, so a plugin must not be able to remove or replace them |
| **Plugins** | stages, publishers, metrics sources, surfaces (server, panel), themes, locales, integrations, agent runtimes | yes: installed, enabled, disabled, replaced |

`pip install simplicio-video` (no extras) gives the engine and the host registry: you can render videos from a contract with no plugin at all. `[factory]` adds the SDK and host services; plugins add features.

Disambiguation: `plugin.json` at the repository root is how the whole of `simplicio-video` presents itself to **Simplicio Runtime** (`simplicio.plugin/v1`, generated from the registry). The plugins described here extend `simplicio-video` itself (`simplicio.video-plugin/v1`).

## Kinds

| Kind | Provides | MVP | Later |
|---|---|---|---|
| `stage` | a `Stage` (one step of the loop) | brand, ideas, studio, review, publish, metrics | plan, library, cast, compliance, learn |
| `publisher` | a `Publisher` | realoficial, export | postiz, Meta, YouTube, TikTok |
| `metrics-source` | a `MetricsSource` | realoficial analytics, CSV | GA4, Clarity, Similarweb, Semrush, Vturb, attribution tools |
| `media-generator` | a `MediaGenerator` | — | Real Oficial media, TopView, Higgsfield |
| `agent-runtime` | an `AgentRunner` | — | CrewAI, Hermes Agent, OpenClaw |
| `orchestrator` | a `LoopRunner` | simple runner (host) | LangGraph |
| `surface` | a way in: server, panel, MCP over HTTP, notifiers | server, panel | MCP/HTTP, Telegram, Slack |
| `theme` | a `Theme` (data only, no code) | `br` | 14 more, user themes |
| `locale` | message catalogs (data only) | `en`, `pt-BR` | 13 more |
| `integration` | commerce, CRM, attribution, analytics connectors | — | Stripe, PayPal, AbacatePay, CartPanda, Kirvano, HubSpot, Utmify, RedTrack |

**No speculative abstractions:** a Protocol for a new kind is added by the first plugin of that kind, in a small `contract-change` PR, together with its contract suite. Only `Stage`, `Publisher`, `MetricsSource`, `Theme`, `LoopRunner` and the Store family exist for the MVP.

## Manifest (`plugin.yaml`, `simplicio.video-plugin/v1`)

First-party plugins live in `src/simplicio_factory/plugins/<id>/` and are discovered by scanning that package; third-party plugins are pip packages exposing the entry point group `simplicio_video.plugins` that points to a package containing a `plugin.yaml`. Both go through the same loader.

```yaml
schema: simplicio.video-plugin/v1
id: realoficial                        # [a-z0-9-]{2,40}
name: Real Oficial
version: 0.1.0
kind: [publisher]
summary: Publish and schedule through the Real Oficial MCP
status: experimental                   # stable | experimental
requires: {core: ">=0.4,<0.5", python: ">=3.10", plugins: [], extras: [mcp]}
provides:
  commands: commands:COMMANDS          # module:attribute, resolved lazily
  stages: []
  publishers: [publisher:RealOficialPublisher]
  metrics_sources: []
  health_checks: [health:CHECKS]
permissions:                           # declared, shown on install, enforced where enforceable
  network: [api.realoficial.com.br]
  secrets: [REALOFICIAL_OAUTH]
  can_publish: true
  can_spend: false
  reads_untrusted_content: false
config_schema: config.schema.json      # optional JSON Schema for this plugin's section in workspace.yaml
docs: docs/plugins/realoficial.md
license: MIT
```

Rules the loader enforces: manifest valid; `requires` satisfied; `status: experimental` plugins hidden unless `SIMPLICIO_EXPERIMENTAL=1`; every command has `summary`, `description` and at least one `examples` entry (see below); modules imported lazily so a broken plugin never breaks `--help`, `doctor` or the core render; a plugin that fails to load is reported by `doctor` and skipped.

## Honest limits of permissions

`can_publish` and `can_spend` are enforced for real: every gated action passes through the Guard and needs a payload-bound confirm token that plugins cannot mint. The `network` allowlist is enforced for fetches made through the SDK (`SafeFetcher`) and is otherwise declarative: Python cannot sandbox a plugin. **A third-party plugin runs with your privileges; install only plugins you trust.** First-party plugins are reviewed with the same gate as the core.

## Lifecycle commands

```
simplicio-video plugin list [--all] [--json]       # installed, enabled, status, kind
simplicio-video plugin info <id>                   # manifest, permissions, health
simplicio-video plugin install <name|path|git-url> # pip install, then validate manifest; shows permissions, asks to enable
simplicio-video plugin enable|disable <id>         # per workspace (workspace.yaml)
simplicio-video plugin update [<id>|--all]
simplicio-video plugin uninstall <id>
simplicio-video plugin doctor [<id>]               # manifest, requires, health checks
simplicio-video plugin new <kind> <id>             # scaffold with failing contract-suite tests (TDD starter)
simplicio-video plugin check <path>                # runs the contract suite for the plugin's kind
```

Related core commands: `simplicio-video doctor` (environment and every plugin's health checks), `simplicio-video install` (copies the bundled skills into the agent host, like the simplicio-loop `install`; the checkout's `.venv` is `scripts/dev_install.sh`, which `install.sh` wraps), `simplicio-video update` (see `docs/host/packaging.md`, owned by #43, and ADR-0020).

## Every command documents itself

A `Command` without `summary`, `description` and `examples` is rejected at load time (and fails the gate). `--help` shows description, arguments, examples and the exit codes; `docs/reference/cli.md` is generated from the same data, so help and reference cannot drift.

## Testing plugins (TDD, contract suites)

The SDK ships pytest contract suites (`simplicio_factory.testkit.contract_suites`): `StageContract`, `PublisherContract`, `MetricsSourceContract`, `StoreContract`, `ThemeContract`, `LocaleContract`. The core ships `PluginContract` (manifest valid, requires satisfied, every command documented, health checks pass, no forbidden imports) in `simplicio_video.plugins`. A plugin test file subclasses the suite for its kind and provides a factory for the subject; the same suite runs against the fake and the real implementation. `plugin new` generates that test file first, red, so work always starts from a failing contract. See [parallel-work.md](parallel-work.md#test-first).

## First-party plugin directory convention

```
src/simplicio_factory/plugins/<id>/
  plugin.yaml  commands.py  stage.py|publisher.py|...  health.py  config.schema.json  README link in docs
tests/factory/plugins/<id>/        # contract-suite subclass first, flow tests, unit tests
docs/plugins/<id>.md               # quickstart, reference, troubleshooting, last_verified
themes/<id>/                       # data-only theme plugins
locales/<lang>/                    # data-only locale plugins
```
