#!/usr/bin/env python
import sys
import argparse
from pathlib import Path

# Local modules
from . import cli
from . import config
from . import pipeline
from .cli.shared import Cmd
from .result import Result, ok, err, is_ok, is_not_ok


def add_arguments(parser):
    """Define the CLI interface and register all available subcommands."""

    # Global options for main edgar command
    parser.add_argument("-w", "--ws", metavar="PATH", help="workspace directory (default: current directory)")
    parser.add_argument("-j", "--journal", nargs="?", const="default", metavar="NAME",
                       help="record command to journal (default: journals/default.jsonl, or journals/NAME.jsonl)")
    parser.add_argument("-d", "--debug", action="store_true", help="print pipeline data to stderr")

    # Add mutually exclusive format options as global flags
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument("--json", action="store_true", help="output in JSON format (JSONL)")
    format_group.add_argument("--table", action="store_true", help="output in table format")
    format_group.add_argument("--csv", action="store_true", help="output in CSV format")
    format_group.add_argument("--tsv", action="store_true", help="output in TSV format (gnuplot native format)")
    
    parser.add_argument("--theme", metavar="X", 
                        choices=["default", "financial", "financial-light", 
                                 "financial-dark", "minimal", "minimal-light",
                                 "minimal-dark", "grid", "grid-light",
                                 "grid-dark", "nobox", "nobox-light",
                                 "nobox-dark", "nobox-minimal",
                                 "nobox-minimal-light", "nobox-minimal-dark"], 
                        help="table theme for output formatting")   

    # Subcommand parsers
    subparsers = parser.add_subparsers()
    
    # Register subcommands from their respective modules
    cli.add.add_arguments(subparsers)
    cli.new.add_arguments(subparsers)
    cli.probe.add_arguments(subparsers)
    cli.select.add_arguments(subparsers)
    cli.delete.add_arguments(subparsers)
    cli.journal.add_arguments(subparsers)
    cli.modify.add_arguments(subparsers)
    cli.update.add_arguments(subparsers)
    cli.report.add_arguments(subparsers)
    cli.calc.add_arguments(subparsers)
    cli.stats.add_arguments(subparsers)
    cli.config.add_arguments(subparsers)


def get_output_format(args):
    """
    Determine output format based on flags or automatic detection.
    """
    if args.json:
        return 'json'
    elif args.table:
        return 'table'
    elif args.csv:
        return 'csv'
    elif args.tsv:
        return 'tsv'
    else:
        # Automatic detection
        return pipeline.output_format()


def cli_main(args):
    """
    CLI entry point with centralized packet handling, journaling, and format control.
    """
    try:
        current_cmd = pipeline.build_current_command()

        # Read packet and context from previous pipeline stage
        stdin_result = pipeline.read()
        if is_not_ok(stdin_result):
            error_msg = stdin_result[1]
            # Can't write to journal yet - don't have workspace
            if pipeline.output_format() == 'packet':
                print(pipeline.err(error_msg))
            else:
                print(error_msg, file=sys.stderr)
            return

        # Extract packet and context
        input_packet, input_context = stdin_result[1]

        # Resolve workspace (priority: --ws flag, context, current directory)
        try:
            workspace = config.get_workspace_path(args.ws, input_context.get("workspace"))
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            return

        # Set workspace in args for commands
        args.workspace = workspace

        # Build context for output
        context = {"workspace": str(workspace)}

        # Build packet with pipeline history
        packet = pipeline.add(input_packet, current_cmd)
        
        # Execute command with Cmd pattern
        cmd = packet["cmd"] if input_packet else {"name": "", "data": []}
        result = args.func(cmd, args)

        # Get history path for automatic recording (always on)
        history_path = config.get_history_path()

        # Handle command result
        if is_not_ok(result):
            error_msg = result[1]

            # Always write to history (tmp)
            cli.journal.write_entry(history_path, packet["pipeline"], "ERROR", error_msg)

            # Conditionally write to explicit journal
            if hasattr(args, 'journal') and args.journal:
                journal_path = config.get_journal_path(workspace, args.journal)
                cli.journal.write_entry(journal_path, packet["pipeline"], "ERROR", error_msg)

            if pipeline.output_format() == 'packet':
                print(pipeline.err(error_msg))
            else:
                print(error_msg, file=sys.stderr)

        elif result[1] is None:
            # Command completed with no data output

            # Always write to history (tmp)
            cli.journal.write_entry(history_path, packet["pipeline"], "OK", None)

            # Conditionally write to explicit journal
            if hasattr(args, 'journal') and args.journal:
                journal_path = config.get_journal_path(workspace, args.journal)
                cli.journal.write_entry(journal_path, packet["pipeline"], "OK", None)

        else:
            # Command returned data - handle format override or continue pipeline
            output_packet = {
                "cmd": result[1],
                "pipeline": packet["pipeline"]}

            # Debug output: show current data to stderr
            if args.debug:
                cmd_name = result[1]["name"]
                data_count = len(result[1]["data"])
                print(f"\n=== DEBUG: {cmd_name} ({data_count} records) ===", file=sys.stderr)
                # Use theme for debug output too
                theme_name = args.theme if args.theme else None
                print(cli.format.as_table(result[1]["data"], theme_name), file=sys.stderr)
                print("=" * 50, file=sys.stderr)

            # Determine actual output format
            output_format = get_output_format(args)

            if output_format == 'packet':
                # Continue pipeline - output JSON packet with context
                pipeline.write(output_packet, context)
            else:
                # Terminal output - format according to user preference or auto-detection
                if output_format == 'json':
                    print(cli.format.as_json(result[1]["data"]))
                elif output_format == 'csv':
                    print(cli.format.as_csv(result[1]["data"]))
                elif output_format == 'tsv':
                    print(cli.format.as_tsv(result[1]["data"]))
                else:  # table or default
                    theme_name = args.theme if args.theme else None
                    print(cli.format.as_table(result[1]["data"], theme_name))

                # Always write to history (tmp)
                cli.journal.write_entry(history_path, packet["pipeline"], "OK", None)

                # Conditionally write to explicit journal
                if hasattr(args, 'journal') and args.journal:
                    journal_path = config.get_journal_path(workspace, args.journal)
                    cli.journal.write_entry(journal_path, packet["pipeline"], "OK", None)

    except KeyboardInterrupt:
        print("main: keyboard interrupt", file=sys.stderr)
    except Exception as e:
        error_msg = f"main: unexpected error: {e}"
        # Best effort history write
        try:
            history_path = config.get_history_path()
            cli.journal.write_entry(history_path, [current_cmd], "ERROR", error_msg)

            # Also write to explicit journal if requested
            if 'args' in locals() and hasattr(args, 'journal') and args.journal and 'workspace' in locals():
                journal_path = config.get_journal_path(workspace, args.journal)
                cli.journal.write_entry(journal_path, [current_cmd], "ERROR", error_msg)
        except:
            pass  # Don't fail on journal errors during exception handling
        print(error_msg, file=sys.stderr)


def main():
    """Entry point for console script."""
    # Load configuration
    cfg = config.load_config()

    # Check if user_agent is still default (first run - needs setup)
    if cfg["edgar"]["user_agent"] == "edgar-pipes/0.2.1":
        config.init_config_interactive()
        cfg = config.load_config()

    parser = argparse.ArgumentParser(
        prog='ep',
        description='Analyze SEC XBRL financial data through progressive discovery and extraction',
        epilog='''
Available themes:
    default, financial, financial-light, financial-dark, minimal,
    minimal-light, minimal-dark, grid, grid-light, grid-dark nobox,
    nobox-light, nobox-dark, nobox-minimal, nobox-minimal-light,
    nobox-minimal-dark

Environment variables:
  EDGAR_PIPES_USER_AGENT    User agent for SEC EDGAR API requests
  EDGAR_PIPES_THEME         Default table theme
  EDGAR_PIPES_DB_PATH       Override database location (absolute or relative to CWD)
  EDGAR_PIPES_JOURNALS_DIR  Override journals directory (absolute or relative to CWD)

Configuration:
  Config file: ~/.config/edgar-pipes/config.toml
  Use "ep config show" to view configuration
  Use "ep config env" to view environment variables

Workspace:
  Workspace contains store.db and journals/ directory
  Default: current directory
  Override workspace: -w PATH or --ws PATH
  Override paths: EDGAR_PIPES_DB_PATH and EDGAR_PIPES_JOURNALS_DIR

Examples:
  # Standard workspace model
  mkdir aapl && cd aapl
  ep probe filings -t AAPL --force
  ep select patterns -t AEO -g Balance
  ep new group "Current Assets" --from Balance -t AEO --uid 1 2 3
  ep select concepts -t AAPL | ep delete -y
  ep -w aapl select filings | ep select roles -g Balance | ep probe concepts

  # Custom layout with env vars
  export EDGAR_PIPES_DB_PATH=build/store.db
  export EDGAR_PIPES_JOURNALS_DIR=src/journals
  ep -j setup probe filings -t AAPL

  # View command history
  ep history                    # System-wide history from /tmp
  ep journal                    # View default journal
  ep journal setup              # View setup journal
  ep journal replay setup       # Replay setup journal

Use "ep COMMAND -h" for command-specific help''',  formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.set_defaults(
        config=cfg,
        func=lambda cmd, args: err("No command specified. Use -h for help")
    )
    add_arguments(parser)
    args = parser.parse_args()

    cli_main(args)


if __name__ == "__main__":
    main()
