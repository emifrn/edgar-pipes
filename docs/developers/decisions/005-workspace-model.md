# ADR 005: Workspace-Based Storage Model

## Context

Originally, edgar-pipes used separate configuration for database and journal paths:
- Database path configurable via `--db`, `EDGAR_PIPES_DB_PATH`, or config file
- Journal path configurable via `EDGAR_PIPES_JOURNAL_PATH` or config file
- Users could create multiple named journals in a shared directory
- Journal switching via `ep journal use <name>`

This created friction:
- Database and journal could get out of sync (different analysis states)
- Managing multiple analyses required coordinating separate db/journal paths
- Six configuration points for specifying locations
- Journal switching added cognitive overhead
- No clear filesystem organization for multi-company analysis

## Decision

Introduce the **workspace** concept: a directory containing both database and journal as a single logical unit.

### Workspace Structure

```
workspace/
  ├── store.db              # SQLite database
  └── journal/
      ├── journal.jsonl     # Command history
      └── silence           # Optional flag file
```

### Resolution Priority

1. `-w/--ws` flag (explicit)
2. Context from pipeline (propagated)
3. Current directory (default)

### Key Changes

- Removed `--db` flag → replaced with `-w/--ws`
- Removed `EDGAR_PIPES_DB_PATH` and `EDGAR_PIPES_JOURNAL_PATH` env vars
- Removed `ep journal use/list/current` commands
- Journal is per-workspace, not globally switchable
- Database and journal always live together

### Context Propagation

Workspace propagates through pipeline via JSON envelope:

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

Only the first command in a pipeline needs `-w`; subsequent commands inherit from context.

## Consequences

### Positive

- **Single source of truth**: Database and journal cannot get out of sync
- **Filesystem IS state**: `cd ../aapl` switches analysis context
- **Self-contained**: Each workspace is complete (easy to backup, share, version control)
- **Reduced friction**: One concept instead of six configuration points
- **Clear organization**: Natural directory structure for multi-company analysis
- **Pipeline efficiency**: Workspace specified once, propagates automatically

### Negative

- **Breaking change**: Existing workflows must adapt to workspace model
- **No backward compatibility**: Clean break from old configuration model
- **Migration burden**: Users must reorganize existing databases and journals

## Examples

### Before (old model)

```bash
# Heavy configuration
export EDGAR_PIPES_DB_PATH=/path/to/aapl.db
export EDGAR_PIPES_JOURNAL_PATH=/path/to/journals
ep journal use aapl
ep probe filings -t aapl

# Or explicit flags
ep --db /path/to/aapl.db probe filings -t aapl
```

### After (workspace model)

```bash
# Natural filesystem navigation
mkdir aapl && cd aapl
ep probe filings -t aapl  # Auto-creates store.db and journal/

# Or explicit workspace
ep -w aapl probe filings -t aapl

# Pipeline with context propagation
ep -w aapl probe filings -t aapl | ep select filings | ep select roles
# Only first command needs -w
```

## Notes

This decision aligns with the XDG Base Directory Specification principle that
user data belongs in user-managed directories, not hidden application data
directories. Workspaces are projects, not application state.

The workspace model reduces the conceptual surface area and makes filesystem
operations (copy, backup, version control) intuitive and reliable.
