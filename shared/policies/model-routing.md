# Model Routing

The shared workflow names capability roles, never provider products or model
identifiers. Platform adapters supplied by EM-005 translate these roles into
host capabilities at runtime.

```json
{
  "roles": {
    "strong": {
      "use_for": ["architecture", "decomposition", "difficult debugging", "integration", "final review"],
      "do_not_use_for": ["fully specified mechanical edits"]
    },
    "standard": {
      "use_for": ["normal multi-file implementation", "ordinary code review"],
      "do_not_use_for": ["architecture-critical judgment", "simple transcription"]
    },
    "fast": {
      "use_for": ["fully specified mechanical work", "isolated targeted test execution"],
      "do_not_use_for": ["ambiguous work", "cross-component decisions", "integration review"]
    }
  }
}
```

## Runtime selection

1. Ask the platform adapter for the host's actual available models and
   capabilities. Never infer availability from documentation or a remembered
   identifier.
2. Select the preferred semantic tier for the work. If it is unavailable,
   try each next lower available tier in order, at most once per tier.
3. Record the fallback in the dispatch checkpoint and agent report, including
   the requested role, selected role, unavailable tiers, and reason. If no
   suitable tier is available, execute sequentially in the coordinator or
   record a blocker.
4. When the host cannot change the main model, it may delegate judgment through
   its platform adapter, but the workflow must not claim that the main model
   changed.

## Delegation economics

Optimize completed-task turns, including context transfer, retries, review, and
integration—not token price alone. Use `fast` only for fully specified
mechanical work, `standard` for normal multi-file work and review, and `strong`
for design judgment, difficult debugging, integration, and final review. A
cheaper tier is not economical when predictable rework costs more turns.
