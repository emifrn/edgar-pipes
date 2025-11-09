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

Each command:
- Reads structured JSON from stdin (optional)
- Outputs structured JSON to stdout
- Displays formatted tables when output is a terminal
- Carries provenance (command history) for journaling

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
