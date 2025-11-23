"""
CLI: journal and history

Provides two separate command systems:
- history: System-wide ephemeral command log (from /tmp)
- journal: Workspace-specific persistent journals (view and replay)
"""

import os
import re
import sys
import json
import argparse
import subprocess
from pathlib import Path
from typing import Any, Optional

# Local modules
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


# =============================================================================
# CORE JOURNAL I/O FUNCTIONS
# =============================================================================

# Removed: get_journals_dir, get_current_journal_name, set_current_journal_name, get_journal_path
# Journal paths are now resolved from workspace via config.get_journal_path(workspace)


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


def write_entry(journal_path: Path, pipeline: list[str], status: str, error_msg: Optional[str] = None) -> None:
    """
    Write a pipeline command to the journal with status.

    Args:
        journal_path: Path to journal file
        pipeline: List of command strings that make up the pipeline
        status: "OK" or "ERROR"
        error_msg: Error message if status is "ERROR"
    """
    if not pipeline:
        return  # Nothing to journal

    try:
        # Ensure journal directory exists
        journal_path.parent.mkdir(parents=True, exist_ok=True)

        next_index = get_next_index(journal_path)

        pipeline_str = " | ".join(pipeline)

        entry = {
            "index": next_index,
            "status": status,
            "command": pipeline_str }

        if status == "ERROR" and error_msg:
            entry["error"] = error_msg

        # Write as single line of JSON
        with open(journal_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + '\n')

    except Exception as e:
        # Don't fail the main command if journaling fails
        print(f"journal: failed to write entry: {e}", file=sys.stderr)


def read_entries(journal_path: Path) -> Result[list[dict], str]:
    """Read all journal entries from journal file."""
    try:
        if not journal_path.exists():
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




# =============================================================================
# JOURNAL MANAGEMENT FUNCTIONS
# =============================================================================

def get_journal_entries(journal_path: Path, indices: list[int] | None, lenient: bool = False) -> Result[list[dict], str]:
    """
    Get entries from journal, either all or specific indices.

    Args:
        journal_path: Path to journal file
        indices: Specific indices to retrieve, or None for all
        lenient: If True, skip missing/error entries with warnings (for ranges).
                 If False, fail on missing/error entries (for explicit indices).
    """
    # Read all entries
    result = read_entries(journal_path)
    if is_not_ok(result):
        return result

    all_entries = result[1]
    if not all_entries:
        return err("get_journal_entries: no entries found in journal")

    # Parse entries
    parsed_entries = []
    for entry in all_entries:
        parsed = parse_journal_entry(entry)
        if parsed:
            parsed_entries.append(parsed)

    if indices is None:
        # Return all valid entries
        valid_entries = [e for e in parsed_entries if e["status"] == "OK"]
        return ok(valid_entries)
    else:
        # Return specific indices
        entry_map = {e["index"]: e for e in parsed_entries}
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
                return err("get_journal_entries: no valid entries found in specified range")
        else:
            # Strict mode - fail on missing/error entries
            for idx in indices:
                if idx not in entry_map:
                    return err(f"get_journal_entries: index {idx} not found")

                entry = entry_map[idx]
                if entry["status"] != "OK":
                    return err(f"get_journal_entries: cannot replay ERROR command at index {idx}")

                selected.append(entry)

        return ok(selected)


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


def journal_replay(workspace_root: Path, workspace_config: dict, journal_name: str, targets: list[str]) -> Result[None, str]:
    """Replay journal commands from workspace."""
    from edgar import config

    journal_path = config.get_journal_path(workspace_root, workspace_config, journal_name)

    # Parse indices if provided
    indices = None
    is_lenient = False
    if targets:
        # Join all targets and parse as single spec
        indices_str = ','.join(targets)
        result = parse_indices(indices_str)
        if is_not_ok(result):
            return result
        indices, is_lenient = result[1]

    # Get entries to replay
    result = get_journal_entries(journal_path, indices, is_lenient)
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
# JOURNAL COMMAND HANDLERS
# =============================================================================

def run_journal_view(cmd: Cmd, args) -> Result[None, str]:
    """Display workspace journal entries."""
    # If 'replay' subcommand was used, delegate to replay handler
    if hasattr(args, 'journal_cmd') and args.journal_cmd == 'replay':
        return run_journal_replay(cmd, args)

    try:
        from edgar import config

        # Read from workspace journal
        journal_path = config.get_journal_path(args.workspace_root, args.workspace_config, args.journal_name)

        # Read entries
        result = read_entries(journal_path)
        if is_not_ok(result):
            return result

        entries = result[1]
        if not entries:
            print(f"No entries found in journal '{args.journal_name}'.", file=sys.stderr)
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
            print(f"Journal: {args.journal_name}", file=sys.stderr)
            display_entries(filtered)
        else:
            print("No matching entries found.", file=sys.stderr)

        return ok(None)

    except Exception as e:
        return err(f"cli.journal.run_journal_view: {e}")


def run_journal_replay(cmd: Cmd, args) -> Result[None, str]:
    """Handle journal replay command."""
    journal_name = args.journal_name if hasattr(args, 'journal_name') else "default"
    targets = args.targets if hasattr(args, 'targets') else []
    return journal_replay(args.workspace_root, args.workspace_config, journal_name, targets)


# =============================================================================
# CLI COMMAND REGISTRATION
# =============================================================================

def add_arguments(subparsers):
    """Add history and journal commands to argument parser."""

    # History command - simplified, system-wide only
    parser_history = subparsers.add_parser(
        "history",
        help="show system-wide command history (ephemeral, from /tmp)",
        epilog='''
Location:
  History is always stored in /tmp (or XDG_RUNTIME_DIR if set).
  Path: /tmp/edgar-pipes-{uid}.jsonl

  Note: Not affected by workspace or environment variables.
        For workspace-specific persistent logs, use 'ep journal'.''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser_history.add_argument("-e", "--errors", action="store_true",
                               help="show only error entries")
    parser_history.add_argument("-s", "--success", action="store_true",
                               help="show only successful entries")
    parser_history.add_argument("-p", "--pattern", metavar="REXP",
                               help="filter commands matching regex pattern")
    parser_history.add_argument("-l", "--limit", metavar="N", type=int, default=20,
                               help="number of recent entries to show (default: 20)")
    parser_history.set_defaults(func=run_history)

    # Journal command - view or replay workspace journals
    parser_journal = subparsers.add_parser(
        "journal",
        help="view or replay workspace journals",
        epilog='''
Location resolution:
  Workspace discovery:
    1. Pipeline context (when piped from previous command)
    2. Current directory - searches for ft.toml walking up directory tree
    3. Workspace root is directory containing ft.toml

  Journal files location:
    Defined in ft.toml [edgar-pipes] section: journals = "path/to/journals"
    Final path: {workspace_root}/{journals_path}/{journal_name}.jsonl

Examples:
  ep journal                      # View default journal in current workspace
  ep journal setup                # View setup journal
  cd ~/workspaces/aapl && ep journal   # View journal in aapl workspace
  ep journal replay setup 1:10    # Replay commands 1-10 from setup journal''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Journal supports both view mode (default) and replay subcommand
    parser_journal.add_argument("journal_name", nargs="?", default="default",
                               help="journal name to view (default: default)")
    parser_journal.add_argument("-e", "--errors", action="store_true",
                               help="show only error entries")
    parser_journal.add_argument("-s", "--success", action="store_true",
                               help="show only successful entries")
    parser_journal.add_argument("-p", "--pattern", metavar="REXP",
                               help="filter commands matching regex pattern")
    parser_journal.add_argument("-l", "--limit", metavar="N", type=int, default=20,
                               help="number of recent entries to show (default: 20)")
    parser_journal.set_defaults(func=run_journal_view)

    # Replay subcommand
    journal_subparsers = parser_journal.add_subparsers(dest='journal_cmd')
    parser_replay = journal_subparsers.add_parser(
        "replay",
        help="replay commands from journal"
    )
    parser_replay.add_argument("journal_name", nargs="?", default="default",
                              help="journal name (default: default)")
    parser_replay.add_argument("targets", nargs="*",
                              help="index specifications like '1:10' or '5,8,12'")
    parser_replay.set_defaults(func=run_journal_replay)


# =============================================================================
# HISTORY COMMAND IMPLEMENTATION
# =============================================================================

def run_history(cmd: Cmd, args) -> Result[None, str]:
    """Display system-wide command history (from /tmp only)."""
    try:
        from edgar import config

        # Always read from system history (tmp)
        history_path = config.get_history_path()

        # Read entries
        result = read_entries(history_path)
        if is_not_ok(result):
            return result

        entries = result[1]
        if not entries:
            print("No system command history found.", file=sys.stderr)
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
            "command": entry.get("command", "") }

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
        # Build command field with optional error on second line
        command_text = entry["command"]
        if entry.get("error_msg"):
            command_text += f" | Error: {entry['error_msg']}"

        table_data.append({
            "Index": entry["index"],
            "S": "✓" if entry["status"] == "OK" else "✗",
            "Command": command_text
        })

    # Use themed table
    theme_name = cli.themes.get_default_theme()
    output = cli.themes.themed_table(table_data, headers=None, theme_name=theme_name)
    print(output)
