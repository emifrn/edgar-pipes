"""
CLI: config

Manage edgar-pipes configuration.
"""

import os
import sys
from pathlib import Path
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
    user_config = cfg.load_config()
    config_path = cfg.get_config_path()

    # Check if config file exists
    config_status = "✓" if config_path.exists() else "✗ (not created yet)"

    # Get workspace paths
    db_path = args.db_path
    workspace_root = args.workspace_root

    # Find journals directory
    journals_dir = workspace_root / args.workspace_config["edgar-pipes"]["journals"]

    # Get database size if it exists
    db_info = ""
    if db_path.exists():
        size_bytes = db_path.stat().st_size
        db_info = f" ({format_size(size_bytes)})"

    # Get journal count if directory exists
    journal_info = ""
    if journals_dir.exists():
        journal_files = list(journals_dir.glob("*.jsonl"))
        if journal_files:
            journal_info = f" ({len(journal_files)} journal(s))"

    # Get ft.toml location
    ft_config_path = cfg.find_workspace_config(workspace_root)
    ft_status = "✓" if ft_config_path else "✗ (not found)"

    # Get default ticker if set
    default_ticker = cfg.get_default_ticker(args.workspace_config)

    # Print configuration
    print("\nEdgar-pipes Configuration", file=sys.stderr)
    print("=" * 50, file=sys.stderr)

    print(f"\nUser config: {config_path} {config_status}", file=sys.stderr)
    print(f"[edgar]", file=sys.stderr)
    print(f"  user_agent = \"{user_config['edgar']['user_agent']}\"", file=sys.stderr)
    print(f"[output]", file=sys.stderr)
    print(f"  theme = \"{user_config['output']['theme']}\"", file=sys.stderr)

    print(f"\nWorkspace config: {ft_config_path} {ft_status}", file=sys.stderr)
    if default_ticker:
        print(f"[workspace]", file=sys.stderr)
        print(f"  ticker = \"{default_ticker}\"", file=sys.stderr)
    print(f"[edgar-pipes]", file=sys.stderr)
    print(f"  database = {db_path}{db_info}", file=sys.stderr)
    print(f"  journals = {journals_dir}{journal_info}\n", file=sys.stderr)

    return ok(None)


def run_show_env(cmd: Cmd, args) -> Result[None, str]:
    """Show environment variables."""
    # Check which environment variables are set (only user-agent and theme now)
    env_vars = {
        "EDGAR_PIPES_USER_AGENT": os.getenv("EDGAR_PIPES_USER_AGENT"),
        "EDGAR_PIPES_THEME": os.getenv("EDGAR_PIPES_THEME"),
        "XDG_CONFIG_HOME": os.getenv("XDG_CONFIG_HOME"),
    }

    # Print environment variables
    print("\nEnvironment Variables", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    print("\nNote: Database and journal paths are now configured via ft.toml", file=sys.stderr)
    print("      (not environment variables)\n", file=sys.stderr)
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
