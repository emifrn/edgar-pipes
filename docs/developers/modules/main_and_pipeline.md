# Main and Pipeline components

The main entry point (`main.py`) and pipeline orchestration (`pipeline.py`) work
together to provide command composition through JSON packet envelopes.

## main.py - Entry point and CLI orchestration

The main module serves as the primary entry point for the `ep` command. It
handles configuration loading, argument parsing, command execution, output
formatting, and journaling.

### Key functions

**main()** - Console script entry point

1. Load configuration from `~/.config/edgar-pipes/config.toml`
2. Run interactive setup on first use (if user_agent is default)
3. Ensure data directories exist
4. Parse command-line arguments
5. Delegate to `cli_main()` for execution

**cli_main(args)** - Command execution orchestrator

Core execution flow:
1. Build current command string from sys.argv
2. Display journal status bar (if terminal and journalable)
3. Read packet from stdin (if piped from previous command)
4. Execute command function with Cmd pattern
5. Handle result: error, no output, or data output
6. Format output based on context (table/json/csv/packet)
7. Journal successful and failed commands

**add_arguments(parser)** - CLI interface definition

Registers all subcommands from CLI modules and defines global options:
- `--db FILE`: Database path override
- `-d, --debug`: Show pipeline data to stderr
- `-j, --json`: Force JSON output
- `-t, --table`: Force table output
- `--csv`: Force CSV output
- `--theme THEME`: Table theme selection

**get_output_format(args)** - Format detection

Determines output format from flags or automatic detection:
- Explicit flags (`--json`, `--table`, `--csv`) override auto-detection
- Falls back to `pipeline.output_format()` for smart detection

### Journaling integration

Commands are journaled with full pipeline history:
- Entry written on command completion (success or error)
- Meta commands (config, history, journal) are not journaled
- Journal entries include: index, status, command, optional error
- Status bar shows current journal and recording state

### Error handling

Three levels of error handling:
1. **Command errors**: Return `err()` with message, journaled, output to stderr
2. **Keyboard interrupt**: Graceful exit with message
3. **Unexpected exceptions**: Catch-all with journal attempt

## pipeline.py - Packet envelope protocol

The pipeline module implements JSON packet envelopes for command composition.
Commands can be chained with Unix pipes, passing structured data between stages.

### Packet format

JSON envelope structure for inter-command communication:

```json
{
  "ok": true,
  "name": "entities",
  "data": [...],
  "pipeline": ["probe filings -t AAPL", "select entities"]
}
```

Fields:
- `ok`: Success flag (true/false)
- `name`: Command name that produced this data
- `data`: Array of records (success) or error message (failure)
- `pipeline`: Command history for this data flow

### Core functions

**output_format()** - Smart format detection

Returns format based on terminal context:
- `'table'` if stdout is a terminal (human-readable)
- `'packet'` if stdout is piped/redirected (machine-readable JSON)

**read()** - Read packet from stdin

Reads single JSON packet from previous pipeline stage:
- Returns `Ok(None)` if no piped input (start of pipeline)
- Returns `Ok(Packet)` with parsed cmd and pipeline history
- Returns `Err(message)` on JSON parse error or error packet
- Validates envelope structure and required fields

**write(packet)** - Write packet to stdout

Outputs JSON packet for next pipeline stage:
- Serializes packet with ok=true, cmd data, and pipeline history
- Used when continuing pipeline (not terminal output)

**build_current_command()** - Command string builder

Constructs properly shell-quoted command from sys.argv:
- Quotes arguments with spaces/special characters
- Used for journal entries and pipeline history

**add(packet, current_command)** - Pipeline builder

Appends current command to pipeline history:
- If packet is None: starts new pipeline with current command
- If packet exists: appends to existing pipeline history
- Returns updated packet with extended history

### Usage patterns

**Pipeline composition:**

```bash
# Each stage passes data via JSON packet envelope
ep probe filings -t AAPL | ep select roles -g Balance | ep probe concepts
```

**Format override:**

```bash
# Force JSON output even at terminal (bypass auto-detection)
ep select entities -t AAPL --json

# Force table output even when piped (for debugging)
ep select filings -t MSFT --table | less
```

**Debug mode:**

```bash
# Show intermediate data at each pipeline stage
ep -d probe filings -t AAPL | ep -d select roles -g Balance
```

## Data flow example

```
Terminal input:  ep select entities -t AAPL | ep select filings | ep select roles

Stage 1: select entities -t AAPL
  - Read stdin: None (terminal start)
  - Execute: get entities for AAPL
  - Output format: packet (stdout is pipe)
  - Write packet: {"ok": true, "name": "entities", "data": [...], "pipeline": ["select entities -t AAPL"]}

Stage 2: select filings
  - Read stdin: Packet from stage 1
  - Execute: get filings for entities from packet data
  - Output format: packet (stdout is pipe)
  - Write packet: {"ok": true, "name": "filings", "data": [...], "pipeline": ["select entities -t AAPL", "select filings"]}

Stage 3: select roles
  - Read stdin: Packet from stage 2
  - Execute: get roles for filings from packet data
  - Output format: table (stdout is terminal)
  - Display: Formatted table with roles data
  - Journal: Write full pipeline to journal
```
