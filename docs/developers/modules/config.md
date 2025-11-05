# Configuration module

The configuration system provides hierarchical configuration management with
environment variable overrides, TOML config files, and sensible defaults.

## config.py - Configuration management

Configuration loading with three-level precedence:

1. **Environment variables** (highest priority)
2. **Config file** (~/.config/edgar-pipes/config.toml)
3. **Built-in defaults** (lowest priority)

### Configuration structure

```python
{
    "edgar": {
        "user_agent": "Name email@example.com"
    },
    "database": {
        "path": "~/.local/share/edgar-pipes/store.db"
    },
    "journal": {
        "path": "~/.local/share/edgar-pipes/journals"
    },
    "output": {
        "theme": "nobox-minimal"
    }
}
```

### Core functions

**load_config()** - Load configuration with precedence

Returns merged configuration dict:
1. Starts with DEFAULT_CONFIG
2. Loads and merges config file if it exists
3. Applies environment variable overrides
4. Returns final configuration

Environment variable mappings:
- `EDGAR_PIPES_USER_AGENT` → edgar.user_agent
- `EDGAR_PIPES_DB_PATH` → database.path
- `EDGAR_PIPES_JOURNAL_PATH` → journal.path
- `EDGAR_PIPES_THEME` → output.theme

**init_config_interactive()** - First-run setup

Interactive prompt for user-agent configuration:
1. Checks if config file already exists (returns False if so)
2. Prompts user for name and email
3. Creates config directory if needed
4. Writes config.toml with user-provided user-agent
5. Returns True on successful creation

Called from main.py when default user-agent is detected.

**ensure_data_dirs(config)** - Create data directories

Ensures required directories exist:
- Database directory (parent of database path)
- Journal directory

Called once at startup in main.py.

**Helper functions:**

- `get_config_path()`: Returns Path to config.toml using XDG_CONFIG_HOME
- `get_user_agent(config)`: Extract user agent string
- `get_database_path(config)`: Get database path with ~ expansion
- `get_journal_path(config)`: Get journal directory with ~ expansion
- `get_theme(config)`: Get configured theme name

### Configuration precedence example

```python
# defaults.py (built-in)
theme = "nobox-minimal"

# ~/.config/edgar-pipes/config.toml (config file)
[output]
theme = "financial-light"

# Environment (highest priority)
$ export EDGAR_PIPES_THEME=grid-dark

# Result: theme = "grid-dark"
```

### First-run experience

When edgar-pipes runs for the first time:

1. `main()` calls `load_config()`
2. Config loaded with default user_agent = "edgar-pipes/0.1.0"
3. `main()` detects default user_agent
4. Calls `init_config_interactive()`
5. User provides name and email
6. Config file created at ~/.config/edgar-pipes/config.toml
7. `load_config()` called again to reload with user's settings

If user skips interactive setup (empty input), they'll be prompted again on
next run. The default user-agent is a signal that configuration is needed.

## cli/config.py - Config command

Command-line interface for viewing configuration.

### Commands

**ep config show** - Display current configuration

Shows:
- Config file path and existence status
- All configuration sections with current values
- Database file path and size (if exists)
- Journal directory path and count (if exists)

**ep config env** - Display environment variables

Shows which EDGAR_PIPES environment variables are currently set:
- EDGAR_PIPES_USER_AGENT
- EDGAR_PIPES_DB_PATH
- EDGAR_PIPES_JOURNAL_PATH
- EDGAR_PIPES_THEME
- XDG_CONFIG_HOME

Useful for debugging configuration precedence and checking which values
are being overridden by environment variables

Output example for `ep config env`:

```
Environment Variables
==================================================
  EDGAR_PIPES_USER_AGENT (not set)
  EDGAR_PIPES_DB_PATH=/home/user/project/data.db
  EDGAR_PIPES_JOURNAL_PATH (not set)
  EDGAR_PIPES_THEME (not set)
  XDG_CONFIG_HOME (not set)
```

Output example for `ep config show`:

```
Edgar-pipes Configuration
==================================================

Config file: ~/.config/edgar-pipes/config.toml ✓

[edgar]
  user_agent = "John Doe john@example.com"

[database]
  path = ~/.local/share/edgar-pipes/store.db (2.4 MB)

[journal]
  path = ~/.local/share/edgar-pipes/journals (3 journal(s))

[output]
  theme = "nobox-minimal"
```

### Implementation

**run_show(cmd, args)** - Show configuration handler

1. Loads current configuration
2. Gets file paths from configuration
3. Checks file/directory existence
4. Formats and displays configuration
5. Shows additional info (file sizes, journal counts)

**run_show_env(cmd, args)** - Show environment variables handler

1. Checks which EDGAR_PIPES environment variables are set
2. Displays each variable with its value or "(not set)"
3. Useful for debugging configuration precedence issues

**format_size(size_bytes)** - Human-readable file sizes

Converts bytes to appropriate units (B, KB, MB, GB, TB) with one decimal place.

## Configuration file format

The config file uses TOML format (~/.config/edgar-pipes/config.toml):

```toml
# Edgar-pipes configuration file

[edgar]
# Your identity for SEC EDGAR API requests
user_agent = "John Doe john@example.com"

[database]
# Database file location
path = "~/.local/share/edgar-pipes/store.db"

[journal]
# Journal storage location
path = "~/.local/share/edgar-pipes/journals"

[output]
# Default table theme
theme = "nobox-minimal"
```

Users can edit this file directly or use environment variables for temporary
overrides.

## XDG Base Directory compliance

The configuration follows XDG Base Directory specification:

- **Config**: `$XDG_CONFIG_HOME/edgar-pipes/` (default: ~/.config/edgar-pipes/)
- **Data**: `$XDG_DATA_HOME/edgar-pipes/` (default: ~/.local/share/edgar-pipes/)

This ensures edgar-pipes plays nicely with other Linux/Unix applications and
respects user preferences for directory organization.
