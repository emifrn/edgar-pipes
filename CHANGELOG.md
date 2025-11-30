# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2025-11-29

### ⚠️ Breaking Changes

**Unified TOML Configuration (ep.toml)**

Replaced three-file configuration system with single `ep.toml` file:

**Removed:**
- `~/.config/edgar-pipes/config.toml` (user configuration)
- `ft.toml` (workspace paths)
- `setup.json` (XBRL schema)
- **Entire journal system:**
  - `ep journal` command
  - `ep history` command
  - `-j/--journal` flag
  - `edgar/cli/journal.py` module
- `ep config` command (settings now in ep.toml)
- `ep setup` command (replaced by `ep init` + `ep build`)
- `scripts/validate_setup.py` (validation integrated into `ep build -c`)
- `schemas/` directory (JSON Schema no longer needed)

**Why this change:**

Three separate configuration files (config.toml, ft.toml, setup.json) created confusion and required users to manage multiple formats (TOML, JSON, JSONL journals). The imperative journal system was hard to read and modify. By unifying everything into a single declarative `ep.toml` file, we provide a clearer, more maintainable configuration approach that supports comments and is version-controllable.

### Added

**ep init command** - Interactive workspace initialization
- Prompts for user-agent (required by SEC)
- Prompts for company ticker
- Prompts for database path (defaults to "db/edgar.db")
- **Automatically fetches company data from SEC API** (name, CIK)
- Creates database and initializes schema
- Inserts company entity into database
- Creates `ep.toml` with template including example roles and concepts
- Workspace ready for exploration immediately
- If `ep.toml` exists, shows current workspace status (use `--force` to recreate)

**ep build command** - Build database from ep.toml schema
- Reads declarative configuration from `ep.toml`
- Validates XBRL schema (roles, concepts, groups)
- Extracts financial data from cached filings
- Inserts data into database
- Use `ep build -c` to validate configuration without building
- Use `ep build [target]` to build specific target groups

**Unified ep.toml Configuration:**
- **User preferences**: user_agent, theme
- **Database and company**: database path, ticker, CIK, name
- **XBRL schema**: roles, concepts, groups (with regex patterns, UIDs, notes)
- **Targets**: named extraction patterns for common workflows
- Single file, human-readable TOML format with comments
- Auto-discovered by walking up directory tree
- Version-controllable and easily shared

### Changed

**Declarative over Imperative:**
- Define roles, concepts, and groups directly in `ep.toml` using declarative TOML syntax
- Edit `ep.toml` to modify patterns (replaced imperative journal commands)
- Run `ep build` to apply changes to database

**Simplified Workflow:**

Before (v0.3.0):
```bash
# Required three config files plus journals
~/.config/edgar-pipes/config.toml  # User identity
ft.toml                             # Workspace paths
journals/setup.jsonl                # Imperative commands
setup.json                          # XBRL schema
```

After (v0.4.0):
```bash
# Single ep.toml file
ep init                # Initialize workspace interactively
ep probe filings       # Explore filings
ep probe concepts      # Explore XBRL concepts
vi ep.toml            # Define roles and concepts declaratively
ep build -c           # Validate configuration
ep build              # Extract financial data
```

### Migration Guide

**From v0.3.0 to v0.4.0:**

Manual migration for existing workspaces:

```bash
cd bke/

# Start from ft.toml, create ep.toml
cp ft.toml ep.toml

# Edit ep.toml to add:
# - user_agent (from ~/.config/edgar-pipes/config.toml)
# - company details (ticker, cik, name, description)
# - roles, concepts, groups (from journals or setup.json)

# Validate new configuration
ep build -c

# Build database from declarative schema
ep build
```

**New workspace (v0.4.0):**

```bash
mkdir apple && cd apple
ep init
# Prompts for: user-agent, ticker (AAPL), database path
# Fetches company data from SEC automatically
# Creates database and ep.toml - ready to use!

ep probe filings        # Explore SEC filings
ep probe concepts       # Discover XBRL concepts
vi ep.toml             # Define roles and concepts
ep build -c            # Validate configuration
ep build               # Extract financial data
```

**Configuration Structure:**

```toml
# User preferences
user_agent = "John Doe john@example.com"
theme = "nobox-minimal"

# Database and company identification
database = "db/edgar.db"
ticker = "AAPL"
cik = "0000320193"
name = "Apple Inc."

# XBRL Roles
[roles.balance]
pattern = "(?i)^CONSOLIDATEDBALANCESHEETS$"
note = "Balance sheet statement"

# Concepts
[concepts.Cash]
uid = 1
pattern = "^CashAndCashEquivalentsAtCarryingValue$"
note = "Cash and cash equivalents"

# Groups
[groups.Balance]
role = "balance"
concepts = [1]

# Targets
[targets.all]
description = "Extract all financial data"
groups = ["Balance", "Operations"]
```

See [ADR 010: Unified TOML Configuration](docs/developers/decisions/010-unified-toml-configuration.md) for complete rationale and examples.

## [0.3.0] - 2025-11-22

### ⚠️ Breaking Changes

**Workspace Configuration via ft.toml**
- Removed `-w / --ws` workspace flag
- Removed `EDGAR_PIPES_DB_PATH` environment variable
- Removed `EDGAR_PIPES_JOURNALS` environment variable
- Added `ft.toml` workspace configuration file
- `ep` now searches for `ft.toml` by walking up directory tree from current directory

**Why this change:**
Environment variables don't persist across separate command invocations (problematic for AI agents and scripts). The `-w` flag was awkward and didn't support flexible project layouts. The new `ft.toml` model provides a single, discoverable, version-controllable configuration file that naturally supports both simple and complex project structures.

### Added

**`ft.toml` Workspace Configuration**
- Workspace discovery: walks up directory tree to find `ft.toml`
- Supports custom project layouts (separate `db/`, `src/journals/`, `output/` directories)
- Optional default ticker setting in `[workspace]` section
- Clear error messages when `ft.toml` not found
- Full TOML format with validation

**Default Ticker Support**
- Optional `ticker = "AAPL"` in `[workspace]` section of `ft.toml`
- Lowest priority (command-line and pipeline context override)
- Simplifies repetitive commands in single-company workspaces

### Changed

**Configuration Precedence** (from highest to lowest):
1. Command-line arguments (e.g., `-t AAPL`)
2. Pipeline context (propagated from previous command)
3. `ft.toml` workspace defaults
4. Error if required value not found

**Pipeline Context Propagation:**
- Workspace root (directory containing `ft.toml`) propagates through pipelines
- Only the first command needs to be in a workspace directory
- Subsequent piped commands inherit workspace automatically

### Migration Guide

**From v0.2.1 to v0.3.0:**

Create `ft.toml` in your workspace:

```bash
# Simple workspace (database and journals in same directory)
cd aapl
cat > ft.toml <<EOF
[edgar-pipes]
database = "store.db"
journals = "journals"
EOF

# Build-system workspace (separated source/build/output)
cd financial-terminal/bke
cat > ft.toml <<EOF
[workspace]
ticker = "BKE"

[edgar-pipes]
database = "db/edgar.db"
journals = "src/journals"
EOF
```

**Old commands (v0.2.1):**
```bash
export EDGAR_PIPES_DB_PATH=db/edgar.db
export EDGAR_PIPES_JOURNALS=src/journals
ep -w ~/projects/aapl probe filings -t AAPL
```

**New commands (v0.3.0):**
```bash
cd ~/projects/aapl
ep probe filings -t AAPL  # Finds ft.toml automatically
```

## [0.2.1] - 2025-11-17

### ⚠️ Breaking Changes

**Command Interface Cleanup**
- `ep history` now ONLY shows system-wide ephemeral log from `/tmp` (no arguments accepted)
- Removed `ep history <journal_name>` - use `ep journal <name>` instead to view workspace journals
- Migration: Replace `ep history setup` with `ep journal setup`

### Added

**Workspace Path Overrides**
- `EDGAR_PIPES_DB_PATH` environment variable to override database location
- `EDGAR_PIPES_JOURNALS` environment variable to override journals directory
- Supports custom workspace layouts (e.g., separate src/journals from build/store.db)
- Enables build system paradigm: journals as source, database as build artifact

**Journal Viewing**
- `ep journal` command now views default journal (in addition to replay subcommand)
- `ep journal <name>` views named journals (setup, daily, etc.)
- Supports same filters as history: `--limit`, `--errors`, `--success`, `--pattern`

### Changed

**Clearer Command Separation**
- `ep history`: System-wide, ephemeral, cross-workspace command log
- `ep journal`: Workspace-specific, persistent journals (view or replay)
- Improved help text and documentation to clarify distinction

### Migration Guide

**From v0.2.0 to v0.2.1:**

```bash
# Old command
ep history setup

# New command
ep journal setup

# Custom workspace layout (new capability)
export EDGAR_PIPES_DB_PATH=build/store.db
export EDGAR_PIPES_JOURNALS=src/journals
ep -j setup probe filings -t AAPL
```

## [0.2.0] - 2025-11-15

### ⚠️ Breaking Changes

**Workspace-Based Storage Model**
- Introduced workspace concept: database and journals now live together in a single directory
- Removed `EDGAR_PIPES_DB_PATH` and `EDGAR_PIPES_JOURNAL_PATH` environment variables
- Replaced `--db` flag with `-w/--ws` for workspace selection
- Workspace propagates through pipelines via context (only first command needs `-w`)
- Migration: Move your database and journal files into a workspace directory

**Explicit Journaling System**
- Journaling now requires explicit opt-in with `-j` flag (automatic recording removed)
- Removed commands: `ep journal on`, `ep journal off`, `ep journal status`
- Changed directory: `journal/` → `journals/` (plural)
- Default journal: `journals/default.jsonl` instead of `journal/journal.jsonl`
- Migration: Move `journal/journal.jsonl` to `journals/default.jsonl` if needed

**Option Shortcuts Removed**
- Removed `-j` and `-t` shortcuts to prevent naming collisions with new global flags
- Use full flag names: `--json`, `--table`

### Added

**Output Formats**
- Gnuplot format output via `--gp` flag for TSV with comment headers
- Auto-scaling for numeric columns in table output
- Column renaming in output display

**Journaling Features**
- System-level ephemeral history: all commands automatically saved to `/tmp/edgar-pipes-{uid}.jsonl`
- Named journals: `-j setup`, `-j daily`, `-j experiment` for organizing workflows
- `ep history` reads from system history by default
- `ep history <journal_name>` reads from specific journal

**Pattern Management**
- `ep modify group --remove-concept` for unlinking concept patterns from groups
- `ep modify group --remove-role` for unlinking role patterns from groups
- `--note` option for documenting pattern rationale (roles and concepts)

**Calc Command**
- `--null-as-zero` flag to treat NULL values as 0 in calculations

**Config Command**
- `ep config env` subcommand to display environment variables

**Documentation**
- Added CHEATSHEET.md with quick reference for common commands
- Added workspace model decision document (ADR 005)

### Changed

**Query Improvements**
- Harmonized date filtering: all commands now use `--date` flag consistently
- `select patterns`: ticker and group are now optional (previously required)
- `select filings`: returns all records when ticker not specified (previously returned none)
- Improved help text grouping and organization

**Performance**
- Optimized instant facts update based on matching DEI end-of-period

**Code Quality**
- Removed `--ignore-case` flag (use standard regex modifier `(?i)` instead)
- Removed timestamps from journal entries for cleaner format
- Standardized argparse conventions across commands
- Removed `gid` from user-facing interface

### Fixed

- CSV output now uses Unix line endings (LF) instead of Windows (CRLF)
- Journal status bar now properly disabled when journal is off
- Select concepts column defaults improved
- Pattern selection help menu formatting
- Various README.md typos and clarifications
- Help message accuracy and consistency

### Migration Guide

**From v0.1.0 to v0.2.0:**

1. **Workspace migration:**
   ```bash
   # Old structure
   ~/data/aapl.db
   ~/.local/share/edgar-pipes/journals/aapl.jsonl

   # New structure
   mkdir ~/workspaces/aapl
   mv ~/data/aapl.db ~/workspaces/aapl/store.db
   mkdir ~/workspaces/aapl/journals
   mv ~/.local/share/edgar-pipes/journals/aapl.jsonl ~/workspaces/aapl/journals/default.jsonl
   ```

2. **Journal recording:**
   ```bash
   # Old (automatic)
   ep probe filings -t AAPL

   # New (explicit)
   ep -j probe filings -t AAPL          # Records to journals/default.jsonl
   ep -j setup probe filings -t AAPL    # Records to journals/setup.jsonl
   ```

3. **Output flags:**
   ```bash
   # Old
   ep report -t AAPL -g Balance -j

   # New
   ep report -t AAPL -g Balance --json
   ```

## [0.1.0] - 2025-12-XX

Initial release.

### Added
- Progressive discovery workflow for SEC EDGAR XBRL financial data extraction
- CLI commands: `probe`, `select`, `new`, `add`, `update`, `report`, `calc`, `stats`, `modify`, `delete`, `journal`, `history`, `config`
- Pattern-based matching system for roles and concepts
- Hierarchical group organization (Balance, Operations, CashFlow, Equity)
- SQLite database for persistent storage
- Pipeline architecture with Unix pipes support
- Journal system for reproducible workflows
- Multiple output formats (table, CSV, JSON)
- XDG-compliant configuration system
- Optional `--note` field for role and concept patterns to document pattern rationale

### Known Limitations
- US companies only (Form 10-Q/10-K)
- Consolidated facts only (no segment/dimensional data)
- Alpha software - expect rough edges

---

[0.2.0]: https://github.com/emifrn/edgar-pipes/releases/tag/v0.2.0
[0.1.0]: https://github.com/emifrn/edgar-pipes/releases/tag/v0.1.0
