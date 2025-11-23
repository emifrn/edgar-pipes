# ADR 006: ft.toml Workspace Configuration

## Context

In ADR 005, we introduced the workspace concept with `-w/--ws` flag to group database and journals together. While this solved database/journal synchronization issues, it created new friction:

- **Environment variables don't persist**: Separate command invocations (common with AI agents and scripts) lose `EDGAR_PIPES_DB_PATH` and `EDGAR_PIPES_JOURNALS` environment variables
- **-w flag is awkward**: Requires every command to specify workspace path or rely on current directory default
- **No flexible layouts**: Can't separate source files (journals) from build artifacts (database) without environment variables
- **Build system friction**: Makefiles need verbose environment variable exports for custom layouts
- **Not discoverable**: No standard way to find workspace configuration when running from subdirectories

Real-world example that exposed the problem:

```bash
# This doesn't work (env vars don't persist across separate invocations)
export EDGAR_PIPES_DB_PATH=db/edgar.db
# ... later in different command ...
ep report -t BKE -g Balance  # ERROR: env var lost

# Workaround was verbose:
export EDGAR_PIPES_DB_PATH=db/edgar.db && export EDGAR_PIPES_JOURNALS=src/journals && ep report -t BKE -g Balance
```

AI agents and scripts couldn't rely on environment variables persisting across tool invocations.

## Decision

Replace `-w/--ws` flag and `EDGAR_PIPES_DB_PATH`/`EDGAR_PIPES_JOURNALS` environment variables with `ft.toml` workspace configuration file.

### ft.toml Format

```toml
[workspace]
ticker = "AAPL"  # Optional default ticker
name = "Apple Inc."

[edgar-pipes]
database = "store.db"      # Path relative to ft.toml
journals = "journals"      # Path relative to ft.toml
```

### Discovery Mechanism

Edgar-pipes discovers `ft.toml` by walking up the directory tree from the current working directory, similar to how git finds `.git`:

1. Check current directory for `ft.toml`
2. If not found, check parent directory
3. Repeat until `ft.toml` found or filesystem root reached
4. Raise helpful error if not found

This enables running `ep` commands from any subdirectory within a workspace.

### Resolution Priority

1. Command-line arguments (e.g., `-t AAPL`) - highest priority
2. Pipeline context (propagated from previous command)
3. `ft.toml` workspace defaults (optional ticker)
4. Error if required value not found

### Key Changes

- **Removed**: `-w/--ws` flag
- **Removed**: `EDGAR_PIPES_DB_PATH` environment variable
- **Removed**: `EDGAR_PIPES_JOURNALS` environment variable
- **Added**: `ft.toml` configuration file with auto-discovery
- **Added**: Optional default ticker in `[workspace]` section
- **Retained**: User configuration in `~/.config/edgar-pipes/config.toml` (identity, theme)
- **Retained**: Workspace root propagation through pipeline context

### Context Propagation

Workspace root (directory containing `ft.toml`) propagates through pipeline:

```bash
cd /path/to/aapl
ep select filings -t AAPL | ep select roles -g Balance

# First command discovers ft.toml, adds workspace_root to context
# Second command reads workspace_root from context, loads same ft.toml
```

## Consequences

### Positive

- **Configuration persists**: `ft.toml` file always available, no environment variable issues
- **Discoverable**: Works from any subdirectory (like git)
- **Version controllable**: `ft.toml` can be committed to track workspace configuration
- **Flexible layouts**: Easy to separate source/build/output directories
- **Cleaner interface**: No flags or env vars needed for workspace selection
- **Self-documenting**: Opening a workspace immediately shows configuration
- **AI/script friendly**: Reliable configuration without environment variable management
- **Default ticker**: Optional convenience for single-company workspaces

### Negative

- **Breaking change**: v0.2.1 users must create `ft.toml` files
- **No backward compatibility**: Clean break from `-w` flag and environment variables
- **Migration burden**: All existing workspaces need `ft.toml` files created
- **File proliferation**: One more dotfile in project directories

## Examples

### Before (v0.2.1 with -w flag and env vars)

```bash
# Simple workspace
mkdir aapl && cd aapl
ep -w . probe filings -t AAPL

# Custom layout required env vars
export EDGAR_PIPES_DB_PATH=db/edgar.db
export EDGAR_PIPES_JOURNALS=src/journals
ep -w ~/projects/aapl probe filings -t AAPL

# Had to repeat for every command invocation (didn't persist)
```

### After (v0.3.0 with ft.toml)

```bash
# Simple workspace
mkdir aapl && cd aapl
cat > ft.toml <<EOF
[workspace]
ticker = "AAPL"

[edgar-pipes]
database = "store.db"
journals = "journals"
EOF

ep probe filings -t AAPL  # Auto-discovers ft.toml

# Custom layout
mkdir company && cd company
cat > ft.toml <<EOF
[workspace]
ticker = "BKE"
name = "Buckle Inc."

[edgar-pipes]
database = "db/edgar.db"
journals = "src/journals"
EOF

# Works from anywhere in the tree
cd data/analysis/scripts
ep report -t BKE -g Balance  # Finds ../../../ft.toml automatically
```

### Build System Integration

```makefile
# Before (v0.2.1) - verbose env var exports
EDGAR_PIPES_DB_PATH := $(DB_DIR)/edgar.db
EDGAR_PIPES_JOURNALS := $(SRC_DIR)/journals

$(BUILD_DIR)/%.tsv:
	export EDGAR_PIPES_DB_PATH=$(EDGAR_PIPES_DB_PATH) && \
	export EDGAR_PIPES_JOURNALS=$(EDGAR_PIPES_JOURNALS) && \
	ep report -t BKE -g Balance > $@

# After (v0.3.0) - clean, no env vars needed
$(BUILD_DIR)/%.tsv:
	ep report -t BKE -g Balance > $@
```

The `ft.toml` configuration makes the Makefile dramatically simpler.

## Migration Guide

```bash
# From v0.2.1 to v0.3.0

# Old workspace
~/workspaces/aapl/
  ├── store.db
  └── journals/
      └── default.jsonl

# Create ft.toml
cd ~/workspaces/aapl
cat > ft.toml <<EOF
[workspace]
ticker = "AAPL"

[edgar-pipes]
database = "store.db"
journals = "journals"
EOF

# Old commands with -w flag
ep -w ~/workspaces/aapl probe filings -t AAPL

# New commands (auto-discovery)
cd ~/workspaces/aapl
ep probe filings -t AAPL
```

## Notes

This decision completes the workspace evolution:

1. **Pre-v0.2.0**: Separate `--db` flag and `EDGAR_PIPES_DB_PATH`
2. **v0.2.0 (ADR 005)**: Workspace concept with `-w` flag and optional env vars
3. **v0.3.0 (ADR 006)**: Configuration file with auto-discovery

The `ft.toml` approach draws inspiration from:
- **Git**: `.git` directory discovery by walking up tree
- **Cargo**: `Cargo.toml` in project root
- **Poetry**: `pyproject.toml` in project root
- **EditorConfig**: `.editorconfig` file discovery

The name `ft.toml` signals "financial-terminal" workspace configuration, making it clear this is a workspace configuration file, not a general edgar-pipes config.

This model makes edgar-pipes behave like other modern project-based tools where configuration lives with the project, not in environment variables or flags.
