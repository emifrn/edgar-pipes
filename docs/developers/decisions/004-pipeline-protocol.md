# ADR 004: JSON Pipeline Protocol

## Context

Financial analysis is exploratory, not linear. Users need to refine queries
iteratively, drilling down from broad searches to specific data. Traditional
CLI tools with fixed workflows don't support this exploration pattern.

## Decision

Implement a JSON-based pipeline protocol where commands compose via stdin/stdout:

```bash
ep select filings --ticker AAPL |
   select roles --group balance |
   probe concepts --pattern ".*Assets.*"
```

### Packet Format

```json
{
  "ok": true,
  "name": "filings",
  "data": [...],
  "context": {
    "pipeline": ["probe filings -t aapl"],
    "workspace": "/path/to/workspace"
  }
}
```

Each command:
- Reads structured JSON from stdin (optional)
- Outputs structured JSON to stdout
- Displays formatted tables when output is a terminal
- Carries context (pipeline history, workspace) for provenance and propagation

## Consequences

**Positive:**
- Progressive disclosure - start broad, refine iteratively
- Composability - combine commands in unexpected ways
- Interactive exploration workflow
- Command output can drive subsequent commands
- Provenance tracking enables replay and debugging

**Negative:**
- More complex implementation than simple CLI
- Requires careful packet format design
- stdin/stdout coordination adds complexity
- Format detection logic needed (table vs JSON)

## Notes

The pipeline architecture is fundamental to Edgar's user experience.

### Context Propagation (added v0.1.0)

The `context` object in packets enables execution state to flow through pipelines without requiring explicit flags on every command. When a user specifies `-w workspace` on the first command, subsequent commands in the pipeline inherit the workspace automatically.

This significantly reduces friction for multi-stage pipelines:
```bash
ep -w aapl probe filings -t aapl | ep select filings | ep select roles
# Only first command needs -w, rest inherit from context
```

See ADR 005 for full workspace model details.
