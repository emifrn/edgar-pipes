# ADR 010: Unified TOML Configuration

**Date:** 2025-11-29

## Problem

- Three config files: `~/.config/edgar-pipes/config.toml`, `ft.toml`, `setup.json`
- Imperative JSONL journal hard to read/modify
- JSON doesn't support comments
- Confusing for users

## Solution

Single `ep.toml` file at workspace root with all configuration.

### Structure

```toml
# User preferences
user_agent = "John Doe john@example.com"
theme = "nobox-minimal"

# Database and company
database = "db/edgar.db"  # Relative to this file
ticker = "BKE"
cik = "0000885245"

# Roles, concepts, groups
[roles.balance]
pattern = "(?i)^CONSOLIDATEDBALANCESHEETS$"

[concepts.Cash]
uid = 1
pattern = "^CashAndCashEquivalents$"

[groups.Balance]
role = "balance"
concepts = [1, 2, 3]

[targets.quick]
groups = ["Balance.Summary", "Operations.ProfitLoss"]
```

### Commands

**`ep init`** - Initialize workspace (interactive)
- Prompts for:
  - User agent (required by SEC)
  - Company ticker (e.g., AAPL)
  - Database path (optional, defaults to "db/edgar.db")
- **Fetches company data from SEC API automatically** (name, CIK)
- Creates database and initializes schema
- Inserts company entity
- Creates ep.toml with template
- Workspace ready for exploration immediately
- If ep.toml exists → Show status (use `--force` to recreate)

**`ep build [target]`** - Create/update database
- No target → Build all groups
- With target → Build specific target (e.g., `quick`, `statements`)

**`ep build -c, --check`** - Validate ep.toml and report status

### Database Discovery

1. Walk up directory tree looking for `ep.toml`
2. Read `database` path from ep.toml
3. Resolve relative to ep.toml location

### Removed

- `~/.config/edgar-pipes/config.toml` - user settings moved to ep.toml
- `ft.toml` - workspace paths moved to ep.toml
- `setup.json` - schema moved to ep.toml (now TOML with comments)
- `scripts/validate_setup.py` - validation integrated into `ep build -c`
- `schemas/` directory - JSON Schema not needed for TOML
- `ep config` command - settings now in ep.toml
- `ep setup` command - replaced by `ep init` + `ep build`
- **Journal system (complete purge):**
  - `edgar/cli/journal.py` - entire module removed
  - `ep journal` command - replaced by declarative ep.toml
  - `ep history` command - use bash `history` instead
  - `-j/--journal` flag - no longer recording commands
  - Imperative JSONL approach - replaced by declarative TOML

### Migration

```bash
# Manual migration from old workspace
cd bke/
cp ft.toml ep.toml  # Start from ft.toml, add schema
# Edit ep.toml to add roles, concepts, groups from journal
ep build -c         # Validate
ep build           # Build database
```

## Implementation

- Rename `edgar/cli/setup.py` → `edgar/cli/init.py` (interactive setup)
- Create `edgar/cli/build.py` (build database with -c/--check flag)
- Update `edgar/config.py` to find ep.toml instead of ft.toml
- Remove config.toml and ft.toml logic
- Remove `scripts/validate_setup.py` and `schemas/` directory
- Update all documentation

## Example Workflows

**New workspace (simplified):**
```bash
$ mkdir apple && cd apple
$ ep init
# Prompts for: user-agent, ticker (AAPL), database path
# Fetches company data from SEC automatically
# Creates database and ep.toml - ready to use!

$ ep probe filings        # Explore SEC filings
$ ep probe concepts       # Discover XBRL concepts
$ vi ep.toml             # Define roles and concepts
$ ep build -c            # Validate configuration
$ ep build               # Extract financial data
```

**Copy existing workspace:**
```bash
$ cp ../bke/ep.toml .
$ vi ep.toml             # Modify ticker, concepts
$ ep init                # Shows current workspace status
$ ep build -c            # Validate changes
$ ep build               # Build database
```

**Partial build with targets:**
```bash
$ ep build quick         # Build only "quick" target
$ ep build statements    # Build only core statements
```
