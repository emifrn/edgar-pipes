import sys
import sqlite3
from typing import Any

# Local modules
from edgar import cache
from edgar import config
from edgar import db
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """
    Register the probe command with subcommands.
    """
    parser_probe = subparsers.add_parser("probe", help="discover and cache company filings")
    probe_subparsers = parser_probe.add_subparsers(dest='probe_cmd', help='probe commands')
    
    # probe filings
    parser_filings = probe_subparsers.add_parser("filings", help="find and cache SEC filings")
    parser_filings.add_argument("-t", "--ticker", metavar='X', help="ticker symbol to probe")
    parser_filings.add_argument("-c", "--cols", metavar='X', nargs="+", help="columns to include in output")
    parser_filings.add_argument("--after", type=cli.shared.check_date, help="only filings after date (YYYY-MM-DD)")
    parser_filings.add_argument("--force", action="store_true", help="bypass cache and fetch fresh filings from SEC")    
    parser_filings.set_defaults(func=run)
    
    # probe roles  
    parser_roles = probe_subparsers.add_parser("roles", help="discover XBRL roles in filings")
    parser_roles.add_argument("-a", "--access", metavar="X", help="SEC accession number (e.g., 0000320193-24-000007)")
    parser_roles.add_argument("-c", "--cols", metavar='X', nargs="+", help="columns to include in output")
    parser_roles.add_argument("--list", action="store_true", help="output role list instead of summary")
    parser_roles.set_defaults(func=run)
    
    # probe concepts
    parser_concepts = probe_subparsers.add_parser("concepts", help="extract financial concepts from roles")
    parser_concepts.add_argument("-a", "--access", metavar="X", help="SEC accession number (e.g., 0000320193-24-000007)")
    parser_concepts.add_argument("-r", "--role", metavar="X", help="specific role name")
    parser_concepts.add_argument("-c", "--cols", metavar='X', nargs="+", help="columns to include in output")
    parser_concepts.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[Cmd | None, str]:
    """
    Route to appropriate probe subcommand.
    """
    
    try:
        conn = sqlite3.connect(args.db)
        
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result
        
        # Route to subcommand handler
        if args.probe_cmd == 'filings':
            result = probe_filings(conn, cmd, args)
        elif args.probe_cmd == 'roles':
            result = probe_roles(conn, cmd, args)
        elif args.probe_cmd == 'concepts':
            result = probe_concepts(conn, cmd, args)
        else:
            result = err(f"cli.probe.run: unknown probe subcommand: {args.probe_cmd}")
        
        conn.close()
        return result
        
    except Exception as e:
        return err(f"cli.probe.run() error: {e}")


def probe_filings(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Probe filings: resolve + cache all recent filings for tickers
    """
    user_agent = config.get_user_agent(args.config)

    tickers = cli.shared.merge_stdin_field("ticker", cmd["data"], [args.ticker] if args.ticker else None)
    if not tickers:
        return err("cli.probe.probe_filings: no tickers provided. Use --ticker or pipe entity data.")

    filings = []
    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] Fetching filings for {ticker.upper()}...", end=" ", file=sys.stderr, flush=True)

        result = cache.resolve_entities(conn, user_agent, [ticker])
        if is_not_ok(result):
            print(f"failed: {result[1]}", file=sys.stderr)
            continue  # Best effort - continue with other tickers
        
        entities = result[1]
        if not entities:
            print("not found", file=sys.stderr)
            continue
        
        entity = entities[0]
        result = cache.resolve_filings(conn,
                                        user_agent,
                                        entity['cik'],
                                        form_types=set(cli.shared.PROBE_FORMS),
                                        after_date=args.after,
                                        force=args.force)
        if is_not_ok(result):
            print(f"failed: {result[1]}", file=sys.stderr)
            continue
        
        print(f"cached {len(result[1])} filings", file=sys.stderr)
        filings.extend(result[1])
    
    # Probe commands are for discovery/caching only - no data output
    return ok(None)


def probe_roles(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Probe roles: resolve + cache roles for specified filings, then output summary.
    """
    user_agent = config.get_user_agent(args.config)

    access_nos = cli.shared.merge_stdin_field("access_no",
                                              cmd["data"],
                                              [args.access] if args.access else None)

    if not access_nos:
        return err("cli.probe.probe_roles: no access numbers provided. Use --access or pipe filing data.")

    print(f"Processing {len(access_nos)} filing(s) for role discovery...", file=sys.stderr)
    results = []
    for i, access_no in enumerate(access_nos, 1):
        print(f"[{i:2d}/{len(access_nos)}] {access_no}...", end=" ", file=sys.stderr, flush=True)

        # Get CIK for this filing
        result = db.queries.filings.get_cik(conn, access_no)
        if is_not_ok(result) or not result[1]:
            print("skipped (no CIK)", file=sys.stderr)
            continue
        cik = result[1]

        # Resolve roles for this filing (cache if missing)
        result = cache.resolve_roles(conn, user_agent, cik, access_no)
        if is_not_ok(result):
            print(f"failed: {result[1]}", file=sys.stderr)
            continue
        
        roles = result[1]
        
        # Get filing info for context
        result = db.queries.filings.get_with_entity(conn, access_no)
        if is_not_ok(result) or not result[1]:
            print("skipped (no filing info)", file=sys.stderr)
            continue
        
        filing_info = result[1]
        print(f"cached {len(roles)} roles", file=sys.stderr)
        
        # Build results based on --list flag
        if args.list:
            # Detailed mode: one record per role
            for role_name in roles:
                results.append({
                    "name": filing_info["name"],
                    "ticker": filing_info["ticker"], 
                    "cik": cik,
                    "access_no": access_no,
                    "filing_date": filing_info["filing_date"],
                    "form_type": filing_info["form_type"],
                    "role_name": role_name })
        else:
            # Summary mode: one record per filing
            results.append({
                "name": filing_info["name"],
                "ticker": filing_info["ticker"],
                "cik": cik,
                "access_no": access_no,
                "filing_date": filing_info["filing_date"],
                "form_type": filing_info["form_type"],
                "roles_count": len(roles) })
    
    # Probe commands are for discovery/caching only - no data output
    return ok(None)


def probe_concepts(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Probe concepts: resolve + cache concepts for specified filing-role combinations.
    Returns summary view with concept counts.
    """
    user_agent = config.get_user_agent(args.config)

    role_pairs = []
    for item in cmd["data"]:
        if "access_no" in item and "role_name" in item:
            role_pairs.append({
                "access_no": item["access_no"],
                "role_name": item["role_name"],
                "cik": item.get("cik", ""),
                "name": item.get("name", ""),
                "ticker": item.get("ticker", ""),
                "filing_date": item.get("filing_date", ""),
                "form_type": item.get("form_type", "")
            })

    if not role_pairs:
        return err("cli.probe.probe_concepts: no filing-role pairs found. Pipe data from 'select roles'.")

    print(f"Processing {len(role_pairs)} filing-role combination(s)...", file=sys.stderr)

    results = []
    for i, pair in enumerate(role_pairs, 1):
        print(f"[{i:2d}/{len(role_pairs)}] {pair['access_no']} / {pair['role_name']}...",
              end=" ", file=sys.stderr, flush=True)

        # Resolve and cache concepts
        result = cache.resolve_concepts(conn, user_agent, pair["cik"], pair["access_no"], pair["role_name"])
        if is_not_ok(result):
            print(f"failed: {result[1]}", file=sys.stderr)
            continue  # Best effort - continue with other pairs
        
        concepts = result[1]
        concept_count = len(concepts)
        
        # Build summary record
        results.append({
            "name": pair["name"],
            "ticker": pair["ticker"],
            "cik": pair["cik"],
            "access_no": pair["access_no"],
            "filing_date": pair["filing_date"],
            "form_type": pair["form_type"],
            "role_name": pair["role_name"],
            "concepts_count": concept_count
        })
        
        print(f"cached {concept_count} concepts", file=sys.stderr)
    
    # Probe commands are for discovery/caching only - no data output
    return ok(None)
