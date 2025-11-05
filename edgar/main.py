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
    parser.add_argument("--db", metavar="FILE", help="select database")
    parser.add_argument("-d", "--debug", action="store_true", help="print pipeline data to stderr")

    # Add mutually exclusive format options as global flags
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument("-j", "--json", action="store_true", help="output in JSON format (JSONL)")
    format_group.add_argument("-t", "--table", action="store_true", help="output in table format")
    format_group.add_argument("--csv", action="store_true", help="output in CSV format")
    
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
    else:
        # Automatic detection
        return pipeline.output_format()


def cli_main(args):
    """
    CLI entry point with centralized packet handling, journaling, and format control.
    """
    try:
        current_cmd = pipeline.build_current_command()
        if cli.journal.should_journal_command(current_cmd) and sys.stdin.isatty():
            status_bar = cli.journal.get_status_bar()
            if status_bar:
                print(status_bar, file=sys.stderr)

        # Read packet from previous pipeline stage
        stdin_result = pipeline.read()
        if is_not_ok(stdin_result):
            error_msg = stdin_result[1]
            if not cli.journal.is_silent():
                cli.journal.write_entry([current_cmd], "ERROR", error_msg)
            
            if pipeline.output_format() == 'packet':
                print(pipeline.err(error_msg))
            else:
                print(error_msg, file=sys.stderr)
            return

        # Build packet with pipeline history
        input_packet = stdin_result[1]  # None if start of pipeline
        packet = pipeline.add(input_packet, current_cmd)
        
        # Execute command with Cmd pattern
        cmd = packet["cmd"] if input_packet else {"name": "", "data": []}
        result = args.func(cmd, args)
        
        # Handle command result
        if is_not_ok(result):
            error_msg = result[1]
            if cli.journal.should_journal_command(current_cmd) and not cli.journal.is_silent():
                cli.journal.write_entry(packet["pipeline"], "ERROR", error_msg)
            
            if pipeline.output_format() == 'packet':
                print(pipeline.err(error_msg))
            else:
                print(error_msg, file=sys.stderr)
                
        elif result[1] is None:
            # Command completed with no data output
            if cli.journal.should_journal_command(current_cmd) and not cli.journal.is_silent():
                cli.journal.write_entry(packet["pipeline"], "OK", None)

        else:
            # Command returned data - handle format override or continue pipeline
            output_packet = {
                "cmd": result[1],
                "pipeline": packet["pipeline"]
            }

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
                # Continue pipeline - output JSON packet
                pipeline.write(output_packet)
            else:
                # Terminal output - format according to user preference or auto-detection
                if output_format == 'json':
                    print(cli.format.as_json(result[1]["data"]))
                elif output_format == 'csv':
                    print(cli.format.as_csv(result[1]["data"]))
                else:  # table or default
                    theme_name = args.theme if args.theme else None
                    print(cli.format.as_table(result[1]["data"], theme_name))
                
                if cli.journal.should_journal_command(current_cmd) and not cli.journal.is_silent():
                    cli.journal.write_entry(packet["pipeline"], "OK", None)

    except KeyboardInterrupt:
        print("main: keyboard interrupt", file=sys.stderr)
    except Exception as e:
        error_msg = f"main: unexpected error: {e}"
        try:
            if not cli.journal.is_silent():
                cli.journal.write_entry([current_cmd], "ERROR", error_msg)
        except:
            pass  # Don't fail on journal errors during exception handling
        print(error_msg, file=sys.stderr)


def main():
    """Entry point for console script."""
    # Load configuration
    cfg = config.load_config()

    # Check if user_agent is still default (first run - needs setup)
    if cfg["edgar"]["user_agent"] == "edgar-pipes/0.1.0":
        config.init_config_interactive()
        # Reload config after interactive setup
        cfg = config.load_config()

    # Ensure data directories exist
    config.ensure_data_dirs(cfg)

    # Get paths from config
    db_path = str(config.get_database_path(cfg))
    journal_path_str = str(config.get_journal_path(cfg))

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
  EDGAR_PIPES_DB_PATH       Database file location
  EDGAR_PIPES_JOURNAL_PATH  Journal storage directory
  EDGAR_PIPES_THEME         Default table theme (default: financial-light)

Configuration:
  Config file: ~/.config/edgar-pipes/config.toml
  Use "ep config show" to view configuration
  Use "ep config env" to view environment variables

Examples:
  ep probe filings -t AAPL --force
  ep select patterns -t AEO -g Balance
  ep new group "Current Assets" --from Balance -t AEO --uid 1 2 3
  ep select concepts -t AAPL | ep delete -y
  ep select filings -t AEO | select roles -g Balance | probe concepts

Use "ep COMMAND -h" for command-specific help''',  formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.set_defaults(
        db=db_path,
        func=lambda cmd, args: err("No command specified. Use -h for help")
    )
    add_arguments(parser)
    args = parser.parse_args()

    # Store config in args for commands that need it
    args.config = cfg

    cli_main(args)


if __name__ == "__main__":
    main()
