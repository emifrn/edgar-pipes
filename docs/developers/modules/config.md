# Configuration module

The configuration system provides unified workspace configuration through a single `ep.toml` file at the workspace root.

## config.py - Configuration management

### Single configuration file

**ep.toml** at workspace root contains:
- User preferences (user agent, theme)
- Database path (relative to ep.toml)
- Company identification (ticker, CIK, name)
- XBRL schema (roles, concepts, groups, targets)
- Auto-discovered by walking up directory tree

### Configuration structure

```toml
# User preferences
user_agent = "John Doe john@example.com"
theme = "nobox-minimal"

# Database and company identification
database = "db/edgar.db"  # Relative to ep.toml
ticker = "AAPL"
cik = "0000320193"
name = "Apple Inc."
description = "Financial data extraction from SEC XBRL filings"

# XBRL Roles - Define where to find data in filings
[roles.balance]
pattern = "(?i)^CONSOLIDATEDBALANCESHEETS$"
note = "Balance sheet statement"

# Concepts - Financial metrics to extract
[concepts.Cash]
uid = 1
pattern = "^CashAndCashEquivalentsAtCarryingValue$"
note = "Cash and cash equivalents"

# Groups - Organize concepts for extraction
[groups.Balance]
role = "balance"
concepts = [1]

# Targets - Common extraction patterns
[targets.all]
description = "Extract all financial data"
groups = ["Balance", "Operations"]
```

### Core functions

**find_toml(start_dir: Path | None = None) -> Path | None**

Discovers ep.toml by walking up directory tree:
1. Starts from `start_dir` (defaults to current working directory)
2. Checks for `ep.toml` in current directory
3. Walks up to parent directory
4. Repeats until `ep.toml` found or filesystem root reached
5. Returns Path to `ep.toml` or None

Similar to how git finds `.git` directory.

**load_toml(context_workspace: str | None = None) -> tuple[Path, dict]**

Loads workspace configuration:
1. If `context_workspace` provided (from pipeline), use it as workspace root
2. Otherwise, call `find_toml()` to discover `ep.toml`
3. Raises RuntimeError with helpful message if `ep.toml` not found
4. Loads TOML file and validates structure
5. Returns `(workspace_root, ep_config)` tuple

Validation checks:
- `database` key exists
- `ticker` key exists
- `cik` key exists
- Raises clear errors if validation fails

**get_db_path(workspace_root: Path, ep_config: dict) -> Path**

Resolves database path from configuration:
1. Reads `ep_config["database"]`
2. Interprets as relative to `workspace_root`
3. Returns resolved absolute path

Example:
```python
# ep.toml contains: database = "db/edgar.db"
# workspace_root = /home/user/aapl
# Returns: /home/user/aapl/db/edgar.db
```

**get_ticker(ep_config: dict) -> str**

Extracts ticker from configuration:
```python
return ep_config["ticker"]
```

**get_cik(ep_config: dict) -> str**

Extracts CIK from configuration:
```python
return ep_config["cik"]
```

**get_user_agent(ep_config: dict) -> str**

Extracts user agent from configuration:
```python
return ep_config["user_agent"]
```

**get_theme(ep_config: dict) -> str**

Extracts theme from configuration with default fallback:
```python
return ep_config.get("theme", "nobox-minimal")
```

### Workspace discovery example

```bash
# Directory structure:
/home/user/projects/aapl/
  ep.toml
  db/
    edgar.db
  analysis/
    scripts/

# Run from any subdirectory:
cd /home/user/projects/aapl/analysis/scripts
ep select filings -t AAPL

# find_toml() walks up:
# 1. Check /home/user/projects/aapl/analysis/scripts/ep.toml (not found)
# 2. Check /home/user/projects/aapl/analysis/ep.toml (not found)
# 3. Check /home/user/projects/aapl/ep.toml (found!)
# Returns: /home/user/projects/aapl/ep.toml
```

### Pipeline context propagation

Workspace root propagates through piped commands via pipeline context:

```bash
# Only first command needs to be in workspace directory
cd /home/user/projects/aapl
ep select filings -t AAPL | ep select roles -g Balance | ep probe concepts

# First command (select filings):
# - Discovers ep.toml in current directory
# - Loads workspace config
# - Adds workspace_root to output context

# Second command (select roles):
# - Receives workspace_root in pipeline context
# - Uses it to load workspace config (no discovery needed)

# Third command (probe concepts):
# - Receives workspace_root in pipeline context
# - Uses it to load workspace config
```

This ensures the entire pipeline operates on the same workspace even if
subsequent commands don't explicitly know where the ep.toml is located.

## Workspace initialization

**ep init** - Initialize new workspace

Interactive workspace setup:
1. Prompts for user agent (required by SEC)
2. Prompts for company ticker (e.g., AAPL)
3. Prompts for database path (optional, defaults to "db/edgar.db")
4. Fetches company data from SEC API automatically (name, CIK)
5. Creates database and initializes schema
6. Inserts company entity into database
7. Creates ep.toml with template including example roles and concepts
8. Workspace ready for exploration immediately

If ep.toml already exists, shows current workspace status (use `--force` to recreate).

**ep build** - Build database from ep.toml

Build database from declarative configuration:
1. Loads ep.toml configuration
2. Validates schema (roles, concepts, groups)
3. Extracts financial data from cached filings
4. Inserts data into database

Use `ep build -c` to validate configuration without building.

## Configuration file format

The ep.toml file uses TOML format at workspace root:

```toml
# Edgar Pipes Configuration
# Company: Apple Inc.

# User preferences
user_agent = "John Doe john@example.com"
theme = "nobox-minimal"

# Database and company identification
database = "db/edgar.db"
ticker = "AAPL"
cik = "0000320193"
name = "Apple Inc."
description = "Financial data extraction from SEC XBRL filings"

# =============================================================================
# XBRL Roles - Define where to find data in filings
# =============================================================================

[roles.balance]
pattern = "(?i)^(CONDENSED)?CONSOLIDATEDBALANCESHEETS(Unaudited)?(Parenthetical)?$"
note = "Balance sheet statement"

[roles.operations]
pattern = "(?i)^(CONDENSED)?CONSOLIDATEDSTATEMENTSOFINCOME(Unaudited)?(Parenthetical)?$"
note = "Income statement"

# =============================================================================
# Concepts - Financial metrics to extract
# =============================================================================

[concepts.Cash]
uid = 1
pattern = "^CashAndCashEquivalentsAtCarryingValue$"
note = "Cash and cash equivalents"

[concepts.Revenue]
uid = 100
pattern = "^(RevenueFromContractWithCustomerExcludingAssessedTax|SalesRevenueNet)$"
note = "Total revenue"

# =============================================================================
# Groups - Organize concepts for extraction and reporting
# =============================================================================

[groups.Balance]
role = "balance"
concepts = [1]

[groups.Operations]
role = "operations"
concepts = [100]

# =============================================================================
# Targets - Common extraction patterns
# =============================================================================

[targets.all]
description = "Extract all financial data from filings"
groups = ["Balance", "Operations"]
```

## Migration from v0.3.x

Version 0.4.0 replaced the dual-file configuration system with unified ep.toml:

**Removed:**
- `~/.config/edgar-pipes/config.toml` - user settings moved to ep.toml
- `ft.toml` - workspace paths moved to ep.toml
- `setup.json` - schema moved to ep.toml (now TOML with comments)
- Journal system (complete purge):
  - `edgar/cli/journal.py` - entire module removed
  - `ep journal` command - replaced by declarative ep.toml
  - `ep history` command - use bash `history` instead
  - `-j/--journal` flag - no longer recording commands
- `ep config` command - settings now in ep.toml
- `ep setup` command - replaced by `ep init` + `ep build`
- `scripts/validate_setup.py` - validation integrated into `ep build -c`
- `schemas/` directory - JSON Schema not needed for TOML

**Migration:**
```bash
# Manual migration from old workspace
cd bke/
cp ft.toml ep.toml  # Start from ft.toml, add schema
# Edit ep.toml to add user_agent, roles, concepts, groups
ep build -c         # Validate
ep build           # Build database
```

See CHANGELOG.md and ADR 010 for complete migration guide.
