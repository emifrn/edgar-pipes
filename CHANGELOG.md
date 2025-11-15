# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
