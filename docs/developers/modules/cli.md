# CLI component

The CLI component implements all user-facing commands for edgar-pipes. It
follows a consistent pattern: each command module handles argument parsing,
validation, database operations, and output formatting.

## Module overview

### Command modules

Each command module follows the same structure:
- `add_arguments(subparsers)`: Register command with argparse
- `run(cmd, args)`: Main entry point, returns `Result[Cmd | None, str]`
- `run_<subcommand>(cmd, args)`: Subcommand handlers for commands with variants

**Discovery and caching:**
- `probe.py`: Discover and cache entities, filings, roles, and concepts from SEC

**Data selection:**
- `select.py`: Query database for entities, filings, groups, roles, concepts, and patterns

**Data definition:**
- `new.py`: Create groups, roles, and concepts with patterns (supports `--note` for role and concept patterns)
- `add.py`: Link existing entities (roles/concepts) to groups
- `modify.py`: Update patterns and metadata (supports `--note` for role and concept patterns)
- `delete.py`: Remove groups, roles, concepts, and their relationships

**Data extraction:**
- `update.py`: Extract facts from XBRL filings using defined patterns

**Analysis and reporting:**
- `report.py`: Generate financial reports from extracted facts
- `calc.py`: Perform calculations on financial data
- `stats.py`: Show database statistics

**Utilities:**
- `config.py`: Manage configuration settings
- `journal.py`: Command history, replay, and filtering

### Utility modules

**shared.py** - Common validators and utilities

Core exports:
- `Cmd`: TypedDict for pipeline data structure
- `PROBE_FORMS`: Supported SEC form types
- `check_date()`: Date validation for argparse
- `process_cols()`: Column selection, sorting, and filtering
- `merge_stdin_field()`: Merge piped data with command arguments

Internal helpers for column processing:
- `_cols_grep()`: Filter columns by availability
- `_cols_parse()`: Parse column specs with sort indicators (+/-)
- `_cols_reverse()`: Type-aware reverse sorting
- `_cols_make_sort()`: Create sort key functions

**format.py** - Output formatting

Converts data to different formats for display or piping:
- `as_csv(data)`: CSV output
- `as_json(data)`: JSON lines (JSONL)
- `as_table(data, theme)`: Formatted tables with themes
- `as_packets(packet_type, data)`: JSON envelope for piping

**themes.py** - Table styling

Provides themed table rendering with color support:
- `get_theme(name)`: Load theme by name
- `themed_table(data, headers, theme)`: Render styled table
- `should_use_color()`: Detect terminal color support
- `list_available_themes()`: Get available theme names

Themes include financial, minimal, grid, and nobox variants with light/dark modes.

**journal.py** - Command history and replay

Explicit journal recording (via `-j` flag) with replay functionality:
- `write_entry()`: Write command to journal or history
- `read_entries()`: Read journal/history file
- `journal_replay()`: Re-execute commands from journal
- `run_history()`: Display command history (system or named journals)

System history automatically stored in `/tmp/edgar-pipes-{uid}.jsonl` (ephemeral).
User journals stored in `workspace/journals/NAME.jsonl` (explicit with `-j` flag).

## Command patterns

### Pipeline integration

Commands receive data from stdin and output to stdout, enabling composition:

```python
def run(cmd: Cmd, args) -> Result[Cmd | None, str]:
    # cmd["data"] contains piped input from previous command
    # Process and return new Cmd with updated data
    return ok({"name": "command_name", "data": results})
```

Returning `None` indicates success with no data output (e.g., probe commands).

### Data merging

Commands merge explicit arguments with piped data:

```python
tickers = shared.merge_stdin_field("ticker", cmd["data"],
                                   [args.ticker] if args.ticker else None)
```

This enables: `select entities | select filings | probe roles`

## Error handling

All command functions return `Result[T, str]` types:
- Success: `ok(cmd_data)` or `ok(None)` for no output
- Failure: `err("error message")` with descriptive context

Errors are journaled with ERROR status and displayed to stderr.
