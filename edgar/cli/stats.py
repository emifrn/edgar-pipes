"""
CLI: stats

Statistical analysis of concepts, showing frequency across filings.
"""
import sys
import sqlite3
from typing import Any

# Local
from edgar import config
from edgar import db
from edgar import config
from edgar import db
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """Add stats command to argument parser."""
    parser_stats = subparsers.add_parser("stats", help="show statistical analysis")
    subparsers_stats = parser_stats.add_subparsers(dest="stats_command", required=True)

    # stats concepts
    parser_concepts = subparsers_stats.add_parser("concepts", help="show concept frequency analysis")
    parser_concepts.add_argument("-t", "--ticker", help="company ticker symbol")
    parser_concepts.add_argument("-g", "--group", help="group name")
    parser_concepts.add_argument("-p", "--pattern", help="role name pattern (regex)")
    parser_concepts.add_argument("--limit", type=int, default=1,
                                 help="minimum number of filings (default: 1)")
    parser_concepts.add_argument("--sort", choices=["count", "tag", "first", "last"],
                                 default="count", help="sort by field (default: count)")
    parser_concepts.set_defaults(func=run_concepts)


def run_concepts(cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Show concept frequency analysis.

    Displays how often each concept appears across filings, including:
    - Filing count and percentage
    - First and last appearance dates
    - Concept name

    Can be used with direct arguments or piped role data.
    """
    conn = sqlite3.connect(args.db_path)
    conn.row_factory = sqlite3.Row

    try:
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Get CIK from ticker
        cik = None
        if args.ticker:
            result = db.queries.entities.select(conn, [args.ticker])
            if is_not_ok(result):
                conn.close()
                return result

            entities = result[1]
            if not entities:
                conn.close()
                return err(f"ticker '{args.ticker}' not found")

            cik = entities[0]["cik"]

        # Determine role filter
        role_filter = None

        # Option 1: Use piped role data
        if cmd["data"]:
            # Extract role names from piped data
            role_names = set()
            for item in cmd["data"]:
                if "role_name" in item:
                    role_names.add(item["role_name"])

            if role_names:
                role_filter = list(role_names)

        # Option 2: Use group
        elif args.group:
            if not cik:
                conn.close()
                return err("--ticker required when using --group")

            # Get role patterns for group
            result = db.queries.role_patterns.match_groups(conn, cik)
            if is_not_ok(result):
                conn.close()
                return result

            role_map = result[1]
            group_roles = role_map.get(args.group, [])

            if not group_roles:
                conn.close()
                return err(f"no roles found for group '{args.group}'")

            role_filter = group_roles

        # Option 3: Use role pattern
        elif args.pattern:
            if not cik:
                conn.close()
                return err("--ticker required when using --pattern")

            # First, get all filings for this CIK
            result = db.queries.filings.select_by_entity(conn, ciks=[cik])
            if is_not_ok(result):
                conn.close()
                return result

            filings = result[1]
            if not filings:
                conn.close()
                return err(f"no filings found for ticker '{args.ticker}'")

            access_nos = [f["access_no"] for f in filings]

            # Get all roles matching pattern
            result = db.queries.roles.select_with_entity(
                conn,
                access_nos=access_nos,
                pattern=args.pattern
            )
            if is_not_ok(result):
                conn.close()
                return result

            role_data = result[1]
            role_filter = list(set(r["role_name"] for r in role_data))

            if not role_filter:
                conn.close()
                return err(f"no roles match pattern '{args.pattern}'")

        else:
            conn.close()
            return err("must specify --group, --pattern, or pipe role data")

        # Ensure we have CIK
        if not cik and cmd["data"]:
            # Try to get CIK from piped data
            for item in cmd["data"]:
                if "cik" in item:
                    cik = item["cik"]
                    break

        if not cik:
            conn.close()
            return err("could not determine CIK (use --ticker or pipe data with cik)")

        # Get concept frequency analysis
        result = db.queries.concepts.frequency(
            conn,
            cik,
            role_filter,
            min_count=args.limit,
            sort_by=args.sort
        )
        if is_not_ok(result):
            conn.close()
            return result

        stats = result[1]

        conn.close()
        return ok({"name": "stats concepts", "data": stats})

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.stats.run_concepts: {e}")
