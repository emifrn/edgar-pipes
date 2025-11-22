"""
CLI: config

Manage edgar-pipes configuration.
"""

import os
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

    # config env
    parser_env = config_subparsers.add_parser("env", help="show environment variables and configuration sources")
    parser_env.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """Route to appropriate config subcommand."""
    if args.config_cmd == 'show':
        return run_show(cmd, args)
    elif args.config_cmd == 'env':
        return run_show_env(cmd, args)
    else:
        print("Usage: ep config show|env", file=sys.stderr)
        return ok(None)


def run_show(cmd: Cmd, args) -> Result[None, str]:
    """Show current configuration and workspace info."""
    config = cfg.load_config()
    config_path = cfg.get_config_path()
    workspace = args.workspace

    # Check if config file exists
    config_status = "✓" if config_path.exists() else "✗ (not created yet)"

    # Get workspace paths
    db_path = cfg.get_db_path(workspace)
    journal_path = cfg.get_journal_path(workspace)

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


def run_show_env(cmd: Cmd, args) -> Result[None, str]:
    """Show environment variables."""
    # Check which environment variables are set
    env_vars = {
        "EDGAR_PIPES_USER_AGENT": os.getenv("EDGAR_PIPES_USER_AGENT"),
        "EDGAR_PIPES_THEME": os.getenv("EDGAR_PIPES_THEME"),
        "EDGAR_PIPES_DB_PATH": os.getenv("EDGAR_PIPES_DB_PATH"),
        "EDGAR_PIPES_JOURNALS": os.getenv("EDGAR_PIPES_JOURNALS"),
        "XDG_CONFIG_HOME": os.getenv("XDG_CONFIG_HOME"),
    }

    # Print environment variables
    print("\nEnvironment Variables", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    for var_name, var_value in env_vars.items():
        if var_value:
            print(f"  {var_name}={var_value}", file=sys.stderr)
        else:
            print(f"  {var_name} (not set)", file=sys.stderr)
    print(file=sys.stderr)

    return ok(None)


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"
