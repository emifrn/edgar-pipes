"""
CLI: journal

Unified journaling module providing journal I/O, history display, and journal management.
"""

import os
import re
import sys
import json
import subprocess
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timezone

# Local modules
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


# =============================================================================
# CORE JOURNAL I/O FUNCTIONS
# =============================================================================

def get_journals_dir() -> Path:
    """Get the directory where journals are stored."""
    # Import here to avoid circular dependency
    from edgar import config
    cfg = config.load_config()
    journals_dir = config.get_journal_path(cfg)
    journals_dir.mkdir(parents=True, exist_ok=True)
    return journals_dir


def get_current_journal_name() -> str:
    """Get the active journal name from current.txt."""
    current_file = get_journals_dir() / 'current.txt'
    if current_file.exists():
        try:
            name = current_file.read_text().strip()
            return name if name else 'default'
        except Exception:
            return 'default'
    return 'default'


def set_current_journal_name(name: str) -> None:
    """Set the active journal name in current.txt."""
    current_file = get_journals_dir() / 'current.txt'
    current_file.write_text(name.strip())


def get_journal_path(journal_name: Optional[str] = None) -> Path:
    """Get path to a journal file. Uses current journal if name not specified."""
    if journal_name is None:
        journal_name = get_current_journal_name()

    journals_dir = get_journals_dir()

    if journal_name == 'default':
        return journals_dir / 'journal.jsonl'
    else:
        return journals_dir / f'journal-{journal_name}.jsonl'


def get_next_index(journal_path: Path) -> int:
    """Get the next sequential index for journal entries."""
    if not journal_path.exists():
        return 1

    try:
        with open(journal_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if not lines:
            return 1

        # Get index from last JSON entry
        last_line = lines[-1].strip()
        if last_line:
            try:
                entry = json.loads(last_line)
                return entry.get("index", 0) + 1
            except json.JSONDecodeError:
                pass

        return len(lines) + 1

    except Exception:
        return 1


def write_entry(pipeline: list[str], status: str, error_msg: Optional[str] = None) -> None:
    """
    Write a pipeline command to the journal with timestamp and status.

    Args:
        pipeline: List of command strings that make up the pipeline
        status: "OK" or "ERROR"
        error_msg: Error message if status is "ERROR"
    """
    if not pipeline:
        return  # Nothing to journal

    try:
        journal_path = get_journal_path()
        next_index = get_next_index(journal_path)

        # Create JSON entry
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        pipeline_str = " | ".join(pipeline)

        entry = {
            "index": next_index,
            "timestamp": timestamp,
            "status": status,
            "command": pipeline_str
        }

        if status == "ERROR" and error_msg:
            entry["error"] = error_msg

        # Write as single line of JSON
        with open(journal_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

    except Exception as e:
        # Don't fail the main command if journaling fails
        print(f"journal: failed to write entry: {e}", file=sys.stderr)


def read_entries(journal_name: Optional[str] = None) -> Result[list[dict], str]:
    """Read all journal entries from specified journal, creating if it doesn't exist."""
    try:
        journal_path = get_journal_path(journal_name)

        if not journal_path.exists():
            # Auto-create journal and notify user
            journal_path.touch()
            display_name = journal_name if journal_name else get_current_journal_name()
            print(f"Created new journal: {display_name}", file=sys.stderr)
            return ok([])

        entries = []
        with open(journal_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        entries.append(entry)
                    except json.JSONDecodeError as e:
                        print(f"Warning: Skipping malformed entry at line {line_num}: {e}", file=sys.stderr)
                        continue

        return ok(entries)

    except Exception as e:
        return err(f"cli.journal.read_entries: {e}")


def is_silent() -> bool:
    """Check if journal recording is silenced."""
    silence_file = get_journals_dir() / 'silence'
    return silence_file.exists()


def journal_on() -> Result[None, str]:
    """Enable journal recording."""
    try:
        silence_file = get_journals_dir() / 'silence'

        if silence_file.exists():
            silence_file.unlink()
            print("Journal recording enabled", file=sys.stderr)
        else:
            print("Journal recording already enabled", file=sys.stderr)

        return ok(None)
    except Exception as e:
        return err(f"cli.journal.journal_on: {e}")


def journal_off() -> Result[None, str]:
    """Disable journal recording."""
    try:
        silence_file = get_journals_dir() / 'silence'

        if silence_file.exists():
            print("Journal recording already disabled", file=sys.stderr)
        else:
            silence_file.touch()
            print("Journal recording disabled", file=sys.stderr)

        return ok(None)
    except Exception as e:
        return err(f"cli.journal.journal_off: {e}")


def journal_status() -> Result[None, str]:
    """Show journal recording status."""
    try:
        current = get_current_journal_name()
        recording_state = "disabled (off)" if is_silent() else "enabled (on)"

        print(f"Current journal: {current}", file=sys.stderr)
        print(f"Recording: {recording_state}", file=sys.stderr)

        return ok(None)
    except Exception as e:
        return err(f"cli.journal.journal_status: {e}")

def get_status_bar() -> str:
    """
    Generate status bar line showing current journal and recording state.
    Returns colored string ready for stderr output, or empty string if recording is off.
    """
    # Only show status bar when recording is enabled
    if is_silent():
        return ""

    current_journal = get_current_journal_name()
    indicator = "\033[90m●\033[0m"  # Dim gray filled circle

    # Format: ● journal: name
    return f"{indicator} \033[90mjournal: {current_journal}\033[0m"


# =============================================================================
# JOURNAL MANAGEMENT FUNCTIONS
# =============================================================================

def journal_use(name: str = "") -> Result[None, str]:
    """Switch to a different journal. Empty name switches to default."""
    try:
        journals_dir = get_journals_dir()
        
        # Clean the name, default to "default" if empty
        name = name.strip() if name else "default"
        
        # Set current journal name
        set_current_journal_name(name)
        
        # Create the journal file if it doesn't exist
        journal_path = get_journal_path(name)
        
        if not journal_path.exists():
            journal_path.touch()
            print(f"Created new journal: {name}", file=sys.stderr)
        else:
            print(f"Switched to journal: {name}", file=sys.stderr)
        
        return ok(None)
        
    except Exception as e:
        return err(f"cli.journal.journal_use: {e}")


def journal_list() -> Result[None, str]:
    """List available journals."""
    try:
        journals_dir = get_journals_dir()
        current = get_current_journal_name()

        # Find all journal files
        journals = set()

        # Check for default journal
        if (journals_dir / 'journal.jsonl').exists():
            journals.add('default')

        # Find named journals
        for file in journals_dir.glob('journal-*.jsonl'):
            name = file.stem.replace('journal-', '')
            journals.add(name)
        
        if not journals:
            print("No journals found.", file=sys.stderr)
            return ok(None)
        
        # Show configuration and journal list
        print(f"Journal directory: {journals_dir}", file=sys.stderr)
        if os.environ.get('EDGAR_PIPES_JOURNAL_PATH'):
            print("  (set by EDGAR_PIPES_JOURNAL_PATH environment variable)", file=sys.stderr)
        else:
            print("  (from config file, override with EDGAR_PIPES_JOURNAL_PATH)", file=sys.stderr)
        
        print("\nAvailable journals:", file=sys.stderr)
        for name in sorted(journals):
            marker = " (current)" if name == current else ""
            if name == 'default':
                filename = "journal.jsonl"
            else:
                filename = f"journal-{name}.jsonl"

            print(f"  {name:<15}{marker:<10} {filename}", file=sys.stderr)
        
        return ok(None)
        
    except Exception as e:
        return err(f"cli.journal.journal_list: {e}")


def journal_current() -> Result[None, str]:
    """Show current journal and recording state."""
    try:
        current = get_current_journal_name()
        journals_dir = get_journals_dir()
        recording_state = "disabled (off)" if is_silent() else "enabled (on)"

        print(f"Current journal: {current}", file=sys.stderr)
        print(f"Recording: {recording_state}", file=sys.stderr)
        print(f"Journal directory: {journals_dir}", file=sys.stderr)

        return ok(None)

    except Exception as e:
        return err(f"cli.journal.journal_current: {e}")


def journal_migrate(journal_name: Optional[str] = None) -> Result[None, str]:
    """Migrate old .txt journal format to new .jsonl format."""
    try:
        journals_dir = get_journals_dir()

        if journal_name is None:
            journal_name = get_current_journal_name()

        # Determine old and new paths
        if journal_name == 'default':
            old_path = journals_dir / 'journal.txt'
            new_path = journals_dir / 'journal.jsonl'
        else:
            old_path = journals_dir / f'journal-{journal_name}.txt'
            new_path = journals_dir / f'journal-{journal_name}.jsonl'

        # Check if old journal exists
        if not old_path.exists():
            return err(f"journal migrate: old journal '{journal_name}' not found at {old_path}")

        # Check if new journal already exists
        if new_path.exists():
            return err(f"journal migrate: new journal already exists at {new_path}. Delete it first if you want to re-migrate.")

        # Read old format
        with open(old_path, 'r', encoding='utf-8') as f:
            old_lines = f.readlines()

        # Convert each line
        converted_count = 0
        with open(new_path, 'w', encoding='utf-8') as f:
            for line in old_lines:
                line = line.strip()
                if not line or ' │ ' not in line:
                    continue

                # Parse old format: "  1  2025-10-12  04:07:48  ✓  │  command"
                try:
                    fixed_part, command_part = line.split(' │ ', 1)
                    fixed_fields = fixed_part.strip().split()

                    if len(fixed_fields) < 4:
                        continue

                    index = int(fixed_fields[0])
                    date = fixed_fields[1]
                    time = fixed_fields[2]
                    status_char = fixed_fields[3]

                    status = "OK" if status_char == "✓" else "ERROR"
                    command = command_part.strip()

                    # Extract error message if present
                    error_msg = None
                    if status == "ERROR" and command.startswith('[') and ']' in command:
                        end_bracket = command.find(']')
                        error_msg = command[1:end_bracket]
                        command = command[end_bracket + 1:].strip()

                    # Create new JSON entry
                    timestamp = f"{date}T{time}Z"
                    entry = {
                        "index": index,
                        "timestamp": timestamp,
                        "status": status,
                        "command": command
                    }

                    if error_msg:
                        entry["error"] = error_msg

                    # Write as JSON line
                    f.write(json.dumps(entry) + '\n')
                    converted_count += 1

                except Exception as e:
                    print(f"Warning: Skipping malformed line: {line[:50]}... ({e})", file=sys.stderr)
                    continue

        print(f"Successfully migrated {converted_count} entries from {old_path.name} to {new_path.name}", file=sys.stderr)
        print(f"Old journal preserved at: {old_path}", file=sys.stderr)
        print(f"New journal created at: {new_path}", file=sys.stderr)

        return ok(None)

    except Exception as e:
        return err(f"cli.journal.journal_migrate: {e}")


def parse_replay_targets(targets: list[str]) -> Result[list[tuple[str, list[int] | None, bool]], str]:
    """
    Parse targets into (journal_name, indices_or_none, is_lenient) tuples.
    Lenient mode applies ONLY to single pure ranges (e.g., '1:50').
    """
    if not targets:
        current = get_current_journal_name()
        return ok([(current, None, False)])
    
    specs = []
    for target in targets:
        target = target.strip()
        
        # Check if it's pure indices (no journal name)
        if re.match(r'^[0-9,:]+$', target):
            current = get_current_journal_name()
            result = parse_indices(target)
            if is_not_ok(result):
                return err(f"parse_replay_targets: {result[1]}")
            indices, is_lenient = result[1]
            specs.append((current, indices, is_lenient))
            continue
        
        # Extract journal name
        journal_match = re.match(r'^([A-Za-z0-9_-]+)', target)
        if not journal_match:
            return err(f"parse_replay_targets: invalid target format '{target}'")
        
        journal_name = journal_match.group(1)
        
        # Check for brackets
        bracket_match = re.search(r'\[\s*([0-9,:]*)\s*\]$', target)
        if bracket_match:
            indices_str = bracket_match.group(1)
            if indices_str == '' or indices_str == ':':
                specs.append((journal_name, None, False))
            else:
                result = parse_indices(indices_str)
                if is_not_ok(result):
                    return err(f"parse_replay_targets: {result[1]}")
                indices, is_lenient = result[1]
                specs.append((journal_name, indices, is_lenient))
        else:
            # Simple journal name
            specs.append((journal_name, None, False))
    
    return ok(specs)


def collect_entries_to_replay(specs: list[tuple[str, list[int] | None, bool]]) -> Result[list[dict], str]:
    """Collect entries based on journal specs."""
    all_entries = []
    
    for journal_name, indices, is_lenient in specs:
        result = get_journal_entries(journal_name, indices, is_lenient)
        if is_not_ok(result):
            return result
        all_entries.extend(result[1])
    
    return ok(all_entries)


def get_journal_entries(journal_name: str, indices: list[int] | None, lenient: bool = False) -> Result[list[dict], str]:
    """
    Get entries from a journal, either all or specific indices.
    
    Args:
        journal_name: Name of the journal to read from
        indices: Specific indices to retrieve, or None for all
        lenient: If True, skip missing/error entries with warnings (for single pure ranges).
                 If False, fail on missing/error entries (for explicit indices).
    """
    # Read and parse all entries
    result = read_and_parse_journal(journal_name)
    if is_not_ok(result):
        return result
    
    all_parsed = result[1]
    
    if indices is None:
        # Return all valid entries
        valid_entries = [e for e in all_parsed if e["status"] == "OK"]
        return ok(valid_entries)
    else:
        # Return specific indices
        entry_map = {e["index"]: e for e in all_parsed}
        selected = []
        
        if lenient:
            # Lenient mode - skip missing/error entries with warnings
            skipped_missing = []
            skipped_errors = []
            
            for idx in indices:
                if idx not in entry_map:
                    skipped_missing.append(idx)
                    continue
                    
                entry = entry_map[idx]
                if entry["status"] != "OK":
                    skipped_errors.append(idx)
                    continue
                    
                selected.append(entry)
            
            # Report what was skipped
            if skipped_missing:
                indices_str = ','.join(map(str, skipped_missing))
                print(f"Warning: Skipped missing indices: {indices_str}", file=sys.stderr)
            
            if skipped_errors:
                indices_str = ','.join(map(str, skipped_errors))
                print(f"Warning: Skipped ERROR entries: {indices_str}", file=sys.stderr)
            
            if not selected:
                return err(f"get_journal_entries: no valid entries found in specified range for journal '{journal_name}'")
        else:
            # Strict mode - fail on missing/error entries
            for idx in indices:
                if idx not in entry_map:
                    return err(f"get_journal_entries: index {idx} not found in journal '{journal_name}'")
                
                entry = entry_map[idx]
                if entry["status"] != "OK":
                    return err(f"get_journal_entries: cannot replay ERROR command at index {idx}")
                
                selected.append(entry)
        
        return ok(selected)


def read_and_parse_journal(journal_name: str) -> Result[list[dict], str]:
    """Read a journal and parse all entries."""
    # Check if journal exists
    journal_path = get_journal_path(journal_name)
    if not journal_path.exists():
        return err(f"read_and_parse_journal: journal '{journal_name}' not found")
    
    # Read entries from journal
    result = read_entries(journal_name)
    if is_not_ok(result):
        return result
    
    entries = result[1]
    if not entries:
        return err(f"read_and_parse_journal: no entries found in journal '{journal_name}'")
    
    # Parse entries
    parsed_entries = []
    for entry in entries:
        parsed = parse_journal_entry(entry)
        if parsed:
            parsed_entries.append(parsed)
    
    return ok(parsed_entries)


def parse_indices(indices_str: str) -> Result[tuple[list[int], bool], str]:
    """
    Parse index string into list of integers.
    Returns (indices, is_lenient) where is_lenient=True only for single pure ranges.
    
    Examples:
        '1:50' -> lenient (single pure range)
        '1,2,3' -> strict (explicit indices)
        '1:10,20:30' -> strict (multiple ranges)
        '1:10,38' -> strict (mixed)
    """
    if not indices_str.strip():
        return err("parse_indices: empty index specification")
    
    parts = [p.strip() for p in indices_str.split(',')]
    
    # Lenient ONLY if: exactly 1 part AND it contains ':'
    is_lenient = (len(parts) == 1 and ':' in parts[0])
    
    indices = []
    
    try:
        for part in parts:
            if ':' in part:
                # Range specification
                start, end = part.split(':', 1)
                start_idx = int(start.strip())
                end_idx = int(end.strip())
                if start_idx > end_idx:
                    return err(f"parse_indices: invalid range '{part}': start > end")
                indices.extend(range(start_idx, end_idx + 1))
            else:
                # Single index
                indices.append(int(part))
    except ValueError as e:
        return err(f"parse_indices: invalid number in index specification: {e}")
    
    return ok((indices, is_lenient))


def journal_replay(targets: list[str]) -> Result[None, str]:
    """Main replay orchestration."""
    # Parse what the user wants to replay
    result = parse_replay_targets(targets)
    if is_not_ok(result):
        return result
    
    replay_specs = result[1]  # List of (journal_name, indices_or_none, is_lenient)
    
    # Collect entries to replay
    result = collect_entries_to_replay(replay_specs)
    if is_not_ok(result):
        return result
    
    entries = result[1]
    
    if not entries:
        print("No commands to replay.", file=sys.stderr)
        return ok(None)
    
    # Execute entries
    return execute_entries(entries)


def execute_entries(entries: list[dict]) -> Result[None, str]:
    """Execute a list of parsed journal entries."""
    print(f"Replaying {len(entries)} command(s)...", file=sys.stderr)

    for i, parsed in enumerate(entries, 1):
        cmd = parsed["command"]
        print(f"[{i}/{len(entries)}] {cmd}", file=sys.stderr)
        pipeline_parts = cmd.split(' | ')
        full_cmd = ' | '.join(f"ep {part.strip()}" for part in pipeline_parts)
        result = subprocess.run(full_cmd, shell=True)
        if result.returncode != 0:
            return err(f"cli.journal.journal_replay: replay failed on command {i}/{len(entries)} - {cmd}")

    print("Replay completed successfully.", file=sys.stderr)
    return ok(None)


# =============================================================================
# JOURNAL MANAGEMENT COMMAND HANDLER
# =============================================================================

def run_journal(cmd: Cmd, args) -> Result[None, str]:
    """Handle journal management subcommands."""
    if args.journal_cmd == 'use':
        return journal_use(args.target)
    elif args.journal_cmd == 'list':
        return journal_list()
    elif args.journal_cmd == 'current':
        return journal_current()
    elif args.journal_cmd == 'migrate':
        return journal_migrate(args.name if hasattr(args, 'name') else None)
    elif args.journal_cmd == 'replay':
        return journal_replay(args.targets)
    elif args.journal_cmd == 'on':
        return journal_on()
    elif args.journal_cmd == 'off':
        return journal_off()
    elif args.journal_cmd == 'status':
        return journal_status()
    else:
        return err("cli.journal.run_journal: unknown journal subcommand")


# =============================================================================
# CLI COMMAND REGISTRATION
# =============================================================================

def add_arguments(subparsers):
    """Add history and journal management commands to argument parser."""
    
    # History command
    parser_history = subparsers.add_parser("history", help="show command history from journal")
    parser_history.add_argument("name", nargs="?", help="journal name (optional, defaults to current)")
    parser_history.add_argument("--limit", type=int, default=20, help="number of recent entries to show (default: 20)")
    parser_history.add_argument("--errors", action="store_true", help="show only error entries")
    parser_history.add_argument("--success", action="store_true", help="show only successful entries")
    parser_history.add_argument("--pattern", help="filter commands matching regex pattern")
    parser_history.set_defaults(func=run_history)
    
    # Journal management commands
    parser_journal = subparsers.add_parser("journal", help="manage journals")
    journal_subparsers = parser_journal.add_subparsers(dest='journal_cmd')
    
    parser_use = journal_subparsers.add_parser("use", help="switch to journal")
    parser_use.add_argument("target", nargs="?", default="", help="journal name (empty = default)")
    parser_use.set_defaults(func=run_journal)
    
    parser_list = journal_subparsers.add_parser("list", help="list journals")
    parser_list.set_defaults(func=run_journal)
    
    parser_current = journal_subparsers.add_parser("current", help="show current journal")
    parser_current.set_defaults(func=run_journal)

    parser_migrate = journal_subparsers.add_parser("migrate", help="migrate old .txt journal to .jsonl format")
    parser_migrate.add_argument("name", nargs="?", help="journal name (optional, defaults to current)")
    parser_migrate.set_defaults(func=run_journal)

    parser_replay = journal_subparsers.add_parser("replay", help="replay commands from journal")
    parser_replay.add_argument("targets", nargs="*", help="journal specifications like 'journal[indices]' or simple indices")
    parser_replay.set_defaults(func=run_journal)

    parser_on = journal_subparsers.add_parser("on", help="enable journal recording")
    parser_on.set_defaults(func=run_journal)

    parser_off = journal_subparsers.add_parser("off", help="disable journal recording")
    parser_off.set_defaults(func=run_journal)

    parser_status = journal_subparsers.add_parser("status", help="show journal recording status")
    parser_status.set_defaults(func=run_journal)


# =============================================================================
# HISTORY COMMAND IMPLEMENTATION
# =============================================================================

def should_journal_command(current_cmd: str) -> bool:
    """Determine if a command should be journaled."""
    # Commands that shouldn't be journaled (meta/inspection commands)
    skip_commands = [
        "config",   # Configuration management
        "history",  # History inspection
        "journal",  # All journal subcommands
    ]

    return not any(current_cmd.startswith(cmd) for cmd in skip_commands)


def run_history(cmd: Cmd, args) -> Result[None, str]:
    """Display command history from journal."""
    
    try:
        # Read journal entries (from specified journal or current)
        result = read_entries(args.name)
        if is_not_ok(result):
            return result
        
        entries = result[1]
        if not entries:
            print("No command history found.", file=sys.stderr)
            return ok(None)
        
        # Parse and filter entries
        parsed_entries = []
        for entry in entries:
            parsed = parse_journal_entry(entry)
            if parsed:
                parsed_entries.append(parsed)
        
        # Apply filters
        filtered = apply_filters(parsed_entries, args)
        
        # Apply limit
        if args.limit and len(filtered) > args.limit:
            filtered = filtered[-args.limit:]
        
        # Display results
        if filtered:
            display_entries(filtered)
        else:
            print("No matching entries found.", file=sys.stderr)
        
        return ok(None)
        
    except Exception as e:
        return err(f"cli.journal.run_history: {e}")


def parse_journal_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    """
    Parse a journal entry (already a dict from JSON).
    Normalizes the format for display functions.
    """
    try:
        # Entry is already parsed JSON, just normalize field names
        normalized = {
            "index": entry.get("index", 0),
            "timestamp": entry.get("timestamp", ""),
            "status": entry.get("status", "OK"),
            "error_msg": entry.get("error"),
            "command": entry.get("command", "")
        }

        return normalized

    except Exception:
        return None


def apply_filters(entries: list[dict], args) -> list[dict]:
    """Apply command-line filters to journal entries."""
    filtered = entries
    
    # Status filters
    if args.errors:
        filtered = [e for e in filtered if e["status"] == "ERROR"]
    elif args.success:
        filtered = [e for e in filtered if e["status"] == "OK"]
    
    # Pattern filter
    if args.pattern:
        try:
            pattern = re.compile(args.pattern)
            filtered = [e for e in filtered if pattern.search(e["command"])]
        except re.error as e:
            print(f"cli.journal.apply_filters: invalid regex pattern: {e}", file=sys.stderr)
            return []
    
    return filtered


def display_entries(entries: list[dict]) -> None:
    """Display journal entries in themed table format."""
    if not entries:
        return

    # Convert to table format
    table_data = []
    for entry in entries:
        # Parse ISO 8601 timestamp (2025-10-12T04:07:48Z)
        timestamp = entry.get("timestamp", "")
        if 'T' in timestamp:
            parts = timestamp.split('T')
            date = parts[0]
            time = parts[1].rstrip('Z') if len(parts) > 1 else ""
        else:
            # Fallback for space-separated format
            timestamp_parts = timestamp.split()
            date = timestamp_parts[0] if len(timestamp_parts) > 0 else ""
            time = timestamp_parts[1] if len(timestamp_parts) > 1 else ""

        # Build command field with optional error on second line
        command_text = entry["command"]
        if entry.get("error_msg"):
            command_text += f" | Error: {entry['error_msg']}"

        table_data.append({
            "Index": entry["index"],
            "Date": date,
            "Time": time,
            "S": "✓" if entry["status"] == "OK" else "✗",
            "Command": command_text
        })

    # Use themed table
    theme_name = cli.themes.get_default_theme()
    output = cli.themes.themed_table(table_data, headers=None, theme_name=theme_name)
    print(output)
