"""
CLI: config

Manage edgar-pipes configuration.
"""

import sys
from edgar import config as cfg
from edgar.cli.shared import Cmd
from edgar.result import Result, ok


def add_arguments(subparsers):
    """Add config command to argument parser."""
    parser_config = subparsers.add_parser("config", help="manage configuration")
    config_subparsers = parser_config.add_subparsers(dest='config_cmd', help='config commands')

    # config show
    parser_show = config_subparsers.add_parser("show", help="show current configuration")
    parser_show.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """Route to appropriate config subcommand."""
    if args.config_cmd == 'show':
        return run_show(cmd, args)
    else:
        print("Usage: ep config show", file=sys.stderr)
        return ok(None)


def run_show(cmd: Cmd, args) -> Result[None, str]:
    """Show current configuration and data locations."""
    config = cfg.load_config()
    config_path = cfg.get_config_path()
    db_path = cfg.get_database_path(config)
    journal_path = cfg.get_journal_path(config)

    # Check if config file exists
    config_status = "✓" if config_path.exists() else "✗ (not created yet)"

    # Get database size if it exists
    db_info = ""
    if db_path.exists():
        size_bytes = db_path.stat().st_size
        db_info = f" ({format_size(size_bytes)})"

    # Get journal count if directory exists
    journal_info = ""
    if journal_path.exists():
        journal_files = list(journal_path.glob("*.jsonl"))
        if journal_files:
            journal_info = f" ({len(journal_files)} journal(s))"

    # Print configuration
    print("\nEdgar-pipes Configuration", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print(f"\nConfig file: {config_path} {config_status}", file=sys.stderr)
    print(f"\n[edgar]", file=sys.stderr)
    print(f"  user_agent = \"{config['edgar']['user_agent']}\"", file=sys.stderr)
    print(f"\n[database]", file=sys.stderr)
    print(f"  path = {db_path}{db_info}", file=sys.stderr)
    print(f"\n[journal]", file=sys.stderr)
    print(f"  path = {journal_path}{journal_info}", file=sys.stderr)
    print(f"\n[output]", file=sys.stderr)
    print(f"  theme = \"{config['output']['theme']}\"\n", file=sys.stderr)

    return ok(None)


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
