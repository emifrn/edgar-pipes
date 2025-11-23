# Configuration module

The configuration system provides two-tier configuration management:
1. **User configuration** - Identity and preferences (~/.config/edgar-pipes/config.toml)
2. **Workspace configuration** - Database and journal paths (ft.toml)

## config.py - Configuration management

### Two configuration files

**User config** (~/.config/edgar-pipes/config.toml):
- User agent (name and email for SEC API)
- Output theme preference
- XDG-compliant location

**Workspace config** (ft.toml):
- Database path (relative to ft.toml)
- Journals directory (relative to ft.toml)
- Optional default ticker
- Auto-discovered by walking up directory tree

### User configuration structure

```python
{
    "edgar": {
        "user_agent": "Name email@example.com"
    },
    "output": {
        "theme": "nobox-minimal"
    }
}
```

### Workspace configuration structure

```toml
[workspace]
ticker = "AAPL"  # Optional default ticker
name = "Apple Inc."

[edgar-pipes]
database = "store.db"      # Path relative to ft.toml
journals = "journals"      # Path relative to ft.toml
```

### Core functions

**load_user_config()** - Load user configuration

Returns merged configuration dict:
1. Starts with DEFAULT_CONFIG
2. Loads and merges config file if it exists (~/.config/edgar-pipes/config.toml)
3. Applies environment variable overrides (EDGAR_PIPES_USER_AGENT, EDGAR_PIPES_THEME)
4. Returns final configuration

Environment variable mappings:
- `EDGAR_PIPES_USER_AGENT` → edgar.user_agent
- `EDGAR_PIPES_THEME` → output.theme

**find_workspace_config(start_dir: Path | None = None) -> Path | None**

Discovers ft.toml by walking up directory tree:
1. Starts from `start_dir` (defaults to current working directory)
2. Checks for `ft.toml` in current directory
3. Walks up to parent directory
4. Repeats until `ft.toml` found or filesystem root reached
5. Returns Path to `ft.toml` or None

Similar to how git finds `.git` directory.

**load_workspace_config(context_workspace: str | None = None) -> tuple[Path, dict]**

Loads workspace configuration:
1. If `context_workspace` provided (from pipeline), use it as workspace root
2. Otherwise, call `find_workspace_config()` to discover `ft.toml`
3. Raises error with helpful message if `ft.toml` not found
4. Loads TOML file and validates structure
5. Returns `(workspace_root, workspace_config)` tuple

Validation checks:
- `[edgar-pipes]` section exists
- `database` key exists
- `journals` key exists
- Raises clear errors if validation fails

**get_db_path(workspace_root: Path, workspace_config: dict) -> Path**

Resolves database path from workspace configuration:
1. Reads `workspace_config["edgar-pipes"]["database"]`
2. Interprets as relative to `workspace_root`
3. Returns resolved absolute path

Example:
```python
# ft.toml contains: database = "db/edgar.db"
# workspace_root = /home/user/aapl
# Returns: /home/user/aapl/db/edgar.db
```

**get_journal_path(workspace_root: Path, workspace_config: dict, journal_name: str) -> Path**

Resolves journal file path:
1. Reads `workspace_config["edgar-pipes"]["journals"]`
2. Interprets as relative to `workspace_root`
3. Appends `{journal_name}.jsonl`
4. Returns resolved absolute path

Example:
```python
# ft.toml contains: journals = "src/journals"
# workspace_root = /home/user/aapl
# journal_name = "setup"
# Returns: /home/user/aapl/src/journals/setup.jsonl
```

**get_default_ticker(workspace_config: dict) -> str | None**

Extracts optional default ticker from workspace configuration:
1. Checks if `[workspace]` section exists
2. Returns `ticker` value if present
3. Returns None if not configured

Default ticker has lowest precedence:
1. Command-line arguments (highest)
2. Pipeline context
3. Workspace default (lowest)

**init_config_interactive()** - First-run setup

Interactive prompt for user-agent configuration:
1. Checks if config file already exists (returns False if so)
2. Prompts user for name and email
3. Creates config directory if needed
4. Writes config.toml with user-provided user-agent
5. Returns True on successful creation

Called from main.py when default user-agent is detected.

**Helper functions:**

- `get_config_path()`: Returns Path to config.toml using XDG_CONFIG_HOME
- `get_user_agent(config)`: Extract user agent string
- `get_theme(config)`: Get configured theme name

### Workspace discovery example

```bash
# Directory structure:
/home/user/projects/aapl/
  ft.toml
  db/
    edgar.db
  src/
    journals/
      default.jsonl
  analysis/
    scripts/

# Run from any subdirectory:
cd /home/user/projects/aapl/analysis/scripts
ep report -t AAPL -g Balance

# find_workspace_config() walks up:
# 1. Check /home/user/projects/aapl/analysis/scripts/ft.toml (not found)
# 2. Check /home/user/projects/aapl/analysis/ft.toml (not found)
# 3. Check /home/user/projects/aapl/ft.toml (found!)
# Returns: /home/user/projects/aapl/ft.toml
```

### Pipeline context propagation

Workspace root propagates through piped commands via pipeline context:

```bash
# Only first command needs to be in workspace directory
cd /home/user/projects/aapl
ep select filings -t AAPL | ep select roles -g Balance | ep probe concepts

# First command (select filings):
# - Discovers ft.toml in current directory
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
subsequent commands don't explicitly know where the ft.toml is located.

### First-run experience

When edgar-pipes runs for the first time:

1. `main()` calls `load_user_config()`
2. Config loaded with default user_agent = "edgar-pipes/0.3.0"
3. `main()` detects default user_agent
4. Calls `init_config_interactive()`
5. User provides name and email
6. Config file created at ~/.config/edgar-pipes/config.toml
7. `load_user_config()` called again to reload with user's settings

If user skips interactive setup (empty input), they'll be prompted again on
next run. The default user-agent is a signal that configuration is needed.

For workspace configuration, users must create ft.toml manually or copy from
a template. See examples in README.md and CHEATSHEET.md.

## cli/config.py - Config command

Command-line interface for viewing configuration.

### Commands

**ep config show** - Display current configuration

Shows two sections:

1. **User Configuration** (~/.config/edgar-pipes/config.toml):
   - Config file path and existence status
   - User agent string
   - Output theme

2. **Workspace Configuration** (ft.toml):
   - Workspace root directory
   - Database path and size (if exists)
   - Journals directory
   - Default ticker (if configured)

If no workspace found, displays message: "No workspace found (ft.toml not found in current directory tree)"

**ep config env** - Display environment variables

Shows which EDGAR_PIPES environment variables are currently set:
- EDGAR_PIPES_USER_AGENT
- EDGAR_PIPES_THEME

Useful for debugging configuration precedence and checking which values
are being overridden by environment variables.

Output example for `ep config show`:

```
Edgar-pipes Configuration
==================================================

User Configuration: ~/.config/edgar-pipes/config.toml ✓

[edgar]
  user_agent = "John Doe john@example.com"

[output]
  theme = "nobox-minimal"

Workspace Configuration
==================================================

Workspace root: /home/user/projects/aapl

[workspace]
  ticker = "AAPL"
  name = "Apple Inc."

[edgar-pipes]
  database = db/edgar.db
    → /home/user/projects/aapl/db/edgar.db (2.4 MB)
  journals = src/journals
    → /home/user/projects/aapl/src/journals (3 journal files)
```

Output example when no workspace found:

```
Edgar-pipes Configuration
==================================================

User Configuration: ~/.config/edgar-pipes/config.toml ✓

[edgar]
  user_agent = "John Doe john@example.com"

[output]
  theme = "nobox-minimal"

Workspace Configuration
==================================================

No workspace found (ft.toml not found in current directory tree)

To create a workspace, create a ft.toml file:

  [workspace]
  ticker = "AAPL"  # Optional

  [edgar-pipes]
  database = "store.db"
  journals = "journals"
```

### Implementation

**run_show(cmd, args)** - Show configuration handler

1. Loads user configuration
2. Displays user config section
3. Attempts to load workspace configuration
4. If workspace found:
   - Displays workspace root
   - Shows workspace config sections
   - Resolves and displays database path with size
   - Resolves and displays journals path with file count
5. If no workspace:
   - Shows helpful message with example ft.toml

**run_show_env(cmd, args)** - Show environment variables handler

1. Checks which EDGAR_PIPES environment variables are set
2. Displays each variable with its value or "(not set)"
3. Useful for debugging configuration precedence issues

**format_size(size_bytes)** - Human-readable file sizes

Converts bytes to appropriate units (B, KB, MB, GB, TB) with one decimal place.

## Configuration file formats

### User config file

The user config file uses TOML format (~/.config/edgar-pipes/config.toml):

```toml
# Edgar-pipes user configuration

[edgar]
# Your identity for SEC EDGAR API requests
user_agent = "John Doe john@example.com"

[output]
# Default table theme
theme = "nobox-minimal"
```

Users can edit this file directly or use environment variables for temporary
overrides.

### Workspace config file

The workspace config file uses TOML format (ft.toml in workspace root):

```toml
# Financial Terminal Workspace Configuration

[workspace]
# Optional default ticker (lowest precedence)
ticker = "AAPL"
name = "Apple Inc."

[edgar-pipes]
# Paths relative to this ft.toml file
database = "store.db"
journals = "journals"
```

For build-system layouts with separated source/build/output:

```toml
[workspace]
ticker = "AAPL"
name = "Apple Inc."

[edgar-pipes]
database = "db/edgar.db"      # Build artifact
journals = "src/journals"     # Source files
```

## XDG Base Directory compliance

User configuration follows XDG Base Directory specification:

- **Config**: `$XDG_CONFIG_HOME/edgar-pipes/` (default: ~/.config/edgar-pipes/)

Workspace configuration uses ft.toml files in project directories, similar
to how version control systems use .git directories.

This ensures edgar-pipes plays nicely with other Linux/Unix applications and
respects user preferences for directory organization.

## Migration from v0.2.1

Version 0.3.0 removed:
- `-w, --ws` workspace flag
- `EDGAR_PIPES_DB_PATH` environment variable
- `EDGAR_PIPES_JOURNALS` environment variable

Users must create `ft.toml` files in their workspace directories:

```bash
# Old (v0.2.1)
export EDGAR_PIPES_DB_PATH=db/edgar.db
export EDGAR_PIPES_JOURNALS=src/journals
ep -w ~/projects/aapl probe filings -t AAPL

# New (v0.3.0)
cd ~/projects/aapl
# Create ft.toml with database and journals paths
ep probe filings -t AAPL  # Auto-discovers ft.toml
```

See CHANGELOG.md for complete migration guide.
