import re
import sys
import sqlite3
from typing import Any, Optional

# Local modules
from edgar import db
from edgar import xbrl
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """Add select command and subcommands to argument parser."""
    
    parser_select = subparsers.add_parser("select", help="query cached data with filters")
    select_subparsers = parser_select.add_subparsers(dest='select_cmd', help='select commands')
    
    # Entities subcommand
    parser_entities = select_subparsers.add_parser("entities", help="list companies in database")
    parser_entities.add_argument("-t", "--ticker", metavar='X', help="company stock symbol (e.g., AAPL)")
    parser_entities.add_argument("-c", "--cols", nargs="+", metavar='X', help="columns to include in output")
    parser_entities.set_defaults(func=run)
    
    # Filings subcommand
    parser_filings = select_subparsers.add_parser("filings", help="filter company filings by criteria")
    parser_filings.add_argument("-t", "--ticker", metavar='X', help="company stock symbol (e.g., AAPL)")
    parser_filings.add_argument("-c", "--cols", nargs="+", metavar='X', help="columns to include in output")
    parser_filings.add_argument("--date", nargs="+", metavar="X", help="filter by filing date constraints ('>2024-01-01', '<=2024-12-31')")
    parser_filings.add_argument("--form", nargs="+", metavar="X", help="SEC form types (10-K, 10-Q, etc.)")
    parser_filings.add_argument("--limit", metavar="X", type=int, help="maximum results to return")
    parser_filings.add_argument("--stubs", action="store_true", help="only filings missing fact data")
    parser_filings.set_defaults(func=run)
    
    # Roles subcommand
    parser_roles = select_subparsers.add_parser("roles", help="filter XBRL roles by pattern")

    # Data sources
    group_sources = parser_roles.add_argument_group('data sources')
    group_sources.add_argument("-t", "--ticker", metavar="X", help="company ticker symbol")
    group_sources.add_argument("-a", "--access", metavar="X", help="SEC accession number (e.g., 0000320193-24-000007)")
    group_sources.add_argument("-g", "--group", metavar="X", help="logical group name for pattern-based filtering")

    # Filtering
    group_filters = parser_roles.add_argument_group('filtering')
    group_filters.add_argument("-p", "--pattern", metavar="X", help="role names regex pattern")

    # Output control
    group_output = parser_roles.add_argument_group('output control')
    group_output.add_argument("-c", "--cols", metavar="X", nargs="+", help="columns to include in output")
    group_output.add_argument("-m", "--missing", action="store_true", help="show filings that have no roles matching the criteria")
    group_output.add_argument("-u", "--uniq", action="store_true", help="show only unique values (removes duplicates)")

    parser_roles.set_defaults(func=run)

    # Concepts subcommand
    parser_concepts = select_subparsers.add_parser("concepts", help="filter financial concepts")

    # Data sources
    group_sources = parser_concepts.add_argument_group('data sources')
    group_sources.add_argument("-t", "--ticker", metavar="X", help="company ticker symbol for group-based queries")
    group_sources.add_argument("-a", "--access", metavar="X", help="SEC accession number")
    group_sources.add_argument("-r", "--role", metavar="X", help="specific role name")
    group_sources.add_argument("-g", "--group", metavar="X", help="logical group name for pattern-based filtering")

    # Filtering
    group_filters = parser_concepts.add_argument_group('filtering')
    group_filters.add_argument("-p", "--pattern", metavar="X", help="regex pattern for concept tags")
    group_filters.add_argument("-n", "--name", metavar="X", help="semantic concept name filter (e.g., 'cash', 'inventory')")
    group_filters.add_argument("-l", "--label", action="store_true", help="search concept labels instead of tags")

    # Output control
    group_output = parser_concepts.add_argument_group('output control')
    group_output.add_argument("-c", "--cols", nargs="+", metavar='X', help="columns to include in output")
    group_output.add_argument("-m", "--missing", action="store_true", help="show filing-role pairs that have no concepts matching the criteria")
    group_output.add_argument("-u", "--uniq", action="store_true", help="show only unique values (removes duplicates)")

    parser_concepts.set_defaults(func=run)

    # Groups subcommand
    parser_groups = select_subparsers.add_parser("groups", help="list logical groups")
    parser_groups.add_argument("-p", "--pattern", metavar='X', help="regex pattern to match group names")
    parser_groups.add_argument("-c", "--cols", nargs="+", metavar='X', help="columns to include in output")
    parser_groups.add_argument("-n", "--name", metavar='X', help="specific group name to select")
    parser_groups.set_defaults(func=run)

    # Patterns subcommand
    parser_patterns = select_subparsers.add_parser("patterns", help="view patterns defined for groups")
    parser_patterns.add_argument("-t", "--ticker", help="company ticker symbol")
    parser_patterns.add_argument("-g", "--group", help="logical group name")
    parser_patterns.add_argument("-p", "--pattern", metavar='X', help="regex pattern to filter concept names (applies to concept patterns only)")
    parser_patterns.add_argument("-c", "--cols", nargs="+", metavar='X', help="columns to include in output")
    parser_patterns.add_argument("--uid", "-u", nargs="+", type=int, metavar='X', help="user IDs to select")
    parser_patterns.add_argument("--type", metavar='X', choices=["roles", "concepts", "all"], default="all", help="pattern type to show, valid choices: roles, concepts, all. Default: all")
    parser_patterns.set_defaults(func=run)


def _deduplicate_rows(rows: list[dict]) -> list[dict]:
    """
    Remove duplicate rows based on all column values.
    Preserves order of first occurrence.
    """
    if not rows:
        return rows

    seen = set()
    unique_rows = []

    for row in rows:
        # Create hashable tuple from row values (sorted by keys for consistency)
        row_tuple = tuple(sorted(row.items()))

        if row_tuple not in seen:
            seen.add(row_tuple)
            unique_rows.append(row)

    return unique_rows


def run(cmd: Cmd, args) -> Result[Cmd | None, str]:
    """Route to appropriate select subcommand with input data from main."""

    try:
        conn = sqlite3.connect(args.db)

        # Initialize database if needed
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result
        
        # Route to subcommand handler
        if args.select_cmd == 'entities':
            result = select_entities(conn, cmd, args)
        elif args.select_cmd == 'filings':
            result = select_filings(conn, cmd, args)
        elif args.select_cmd == 'roles':
            result = select_roles(conn, cmd, args)
        elif args.select_cmd == 'concepts':
            result = select_concepts(conn, cmd, args)
        elif args.select_cmd == 'groups':
            result = select_groups(conn, cmd, args)
        elif args.select_cmd == 'patterns':
            result = select_patterns(conn, cmd, args)            
        else:
            result = err(f"cli.select.run: unknown select subcommand: {args.select_cmd}")
        
        conn.close()
        return result
        
    except Exception as e:
        return err(f"cli.select.run() error: {e}")


def select_entities(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Select entities from database and return pipeline data.
    """
    
    # Determine what to query
    tickers = [args.ticker] if args.ticker else None
    result = db.queries.entities.select(conn, tickers)
    if is_not_ok(result):
        return result
    
    entities = result[1]
    
    # Handle empty results
    if not entities and args.ticker:
        return err(f"cli.select.select_entities: ticker '{args.ticker}' not found in database")
    
    # Apply column processing
    default_cols = ['cik', 'ticker', 'name']
    result = cli.shared.process_cols(entities, args.cols, default_cols)
    if is_not_ok(result):
        return result
    entities, _ = result[1]

    # Return pipeline data as dictionary
    return ok({"name": "entities", "data": entities})


def select_filings(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Select filings with specified filters and return command data.
    If no CIK filter provided (no ticker, no stdin data), returns all filings.
    """

    # Convert explicit ticker to CIKs if provided
    explicit_ciks = None
    if args.ticker:
        result = db.queries.entities.select(conn, [args.ticker])
        if is_not_ok(result):
            return result
        entities = result[1]
        if not entities:
            return err(f"cli.select.select_filings: ticker '{args.ticker}' not found in database")
        explicit_ciks = [e['cik'] for e in entities]

    ciks = cli.shared.merge_stdin_field("cik", cmd["data"], explicit_ciks)

    # Execute database query
    # If ciks is None, select_by_entity will return all filings
    date_filters = cli.shared.parse_date_constraints(args.date, 'filing_date')
    result = db.queries.filings.select_by_entity(conn,
                                                 ciks = ciks,
                                                 form_types = args.form,
                                                 date_filters = date_filters,
                                                 stubs_only = args.stubs)
    if is_not_ok(result):
        return result

    filings = result[1]

    # Apply limit if specified
    if args.limit:
        filings = filings[:args.limit]

    # Process --cols if specified
    default_cols = ['name', 'ticker', 'cik', 'access_no', 'filing_date', 'form_type']
    result = cli.shared.process_cols(filings, args.cols, default_cols)
    if is_not_ok(result):
        return result

    filings, _ = result[1]

    return ok({"name": "filings", "data": filings})


def select_groups(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Select groups from database with optional name/pattern filtering.
    """
    
    # Query all groups
    result = db.queries.groups.select(conn)
    if is_not_ok(result):
        return result
    
    groups = result[1]
    
    # Apply name filter if specified
    if args.name:
        groups = [g for g in groups if g["group_name"] == args.name]
    
    # Apply pattern filter if specified
    if args.pattern:
        try:
            regex = re.compile(args.pattern)
            groups = [g for g in groups if regex.search(g["group_name"])]
        except re.error as e:
            return err(f"cli.select.select_groups: invalid regex pattern '{args.pattern}': {e}")
    
    # Apply column processing
    default_cols = ['gid', 'group_name']
    result = cli.shared.process_cols(groups, args.cols, default_cols)
    if is_not_ok(result):
        return result
    groups, _ = result[1]

    return ok({"name": "groups", "data": groups})


def _get_access_nos_from_ticker(conn: sqlite3.Connection, ticker: str) -> Result[list[str], str]:
    """
    Get all cached access numbers for a ticker's filings.
    """
    
    # Resolve ticker to CIK
    result = db.queries.entities.get(conn, ticker=ticker)
    if is_not_ok(result):
        return result
    
    entity = result[1]
    if not entity:
        return err(f"cli.select._get_access_nos_from_ticker: ticker '{ticker}' not found in database")
    
    cik = entity["cik"]
    
    # Get all filings for this CIK
    result = db.queries.filings.select_by_entity(conn, ciks=[cik])
    if is_not_ok(result):
        return result
    
    filings = result[1]
    access_nos = [filing["access_no"] for filing in filings]
    
    return ok(access_nos)


def _get_access_nos_for_roles(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[list[str], str]:
    """
    Resolve access numbers from various data sources for roles query.
    Priority: explicit --access, pipeline data, ticker-based fallback.
    """
    
    # Check for explicit access number
    if args.access:
        access_nos = cli.shared.merge_stdin_field("access_no", cmd["data"], [args.access])
    else:
        access_nos = cli.shared.merge_stdin_field("access_no", cmd["data"], None)
    
    # If we have access numbers from explicit arg or pipeline, use them
    if access_nos:
        return ok(access_nos)
    
    # Fallback to ticker-based lookup
    if args.ticker:
        return _get_access_nos_from_ticker(conn, args.ticker)
    
    # No data source available
    return err("cli.select.select_roles: no access numbers provided. Use --access, pipe filing data, or use --ticker.")


def _get_group_role_patterns(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[list[str], str]:
    """
    Get role patterns for a group. Extracts CIK from ticker or pipeline data.
    """
    
    cik = None
    
    # Try explicit ticker first
    if args.ticker:
        result = db.queries.entities.get(conn, ticker=args.ticker)
        if is_not_ok(result):
            return result
        
        entity = result[1]
        if not entity:
            return err(f"cli.select._get_group_role_patterns: ticker '{args.ticker}' not found in database")
        
        cik = entity["cik"]
    
    # Try to extract CIK from pipeline data
    elif cmd["data"]:
        # Get CIK from first record in pipeline data
        first_record = cmd["data"][0]
        cik = first_record.get("cik")
        
        if not cik:
            return err("cli.select._get_group_role_patterns: --group requires --ticker or pipeline data with CIK information")
    
    else:
        return err("cli.select._get_group_role_patterns: --group requires --ticker or pipeline data to resolve company")
    
    # Get group_id
    result = db.queries.groups.get_id(conn, args.group)
    if is_not_ok(result):
        return result
    
    group_id = result[1]
    if group_id is None:
        return err(f"cli.select._get_group_role_patterns: group '{args.group}' not found")
    
    # Get role patterns for this group/cik
    result = db.queries.role_patterns.select_by_group(conn, group_id, cik)
    if is_not_ok(result):
        return result
    
    patterns = result[1]
    if not patterns:
        return err(f"cli.select._get_group_role_patterns: group '{args.group}' has no role patterns defined for CIK {cik}")
    
    # Extract just the pattern strings
    pattern_strings = [p["pattern"] for p in patterns]
    return ok(pattern_strings)


def select_roles(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Select roles with specified filters and return command data.
    """
    
    # Step 1: Determine data source and get access numbers
    result = _get_access_nos_for_roles(conn, cmd, args)
    if is_not_ok(result):
        return result
    
    access_nos = result[1]
    
    # Step 2: Apply group-based filtering (if requested)
    if args.group:
        result = _get_group_role_patterns(conn, cmd, args)
        if is_not_ok(result):
            return result
        group_patterns = result[1]
        
        if group_patterns:
            group_pattern = "|".join(group_patterns)
            result = db.queries.roles.select_with_entity(conn, access_nos, group_pattern)
        else:
            result = db.queries.roles.select_with_entity(conn, access_nos, None)
    else:
        result = db.queries.roles.select_with_entity(conn, access_nos, None)
    
    if is_not_ok(result):
        return result
    
    roles = result[1]
    
    # Step 3: Apply explicit pattern filter (if requested)
    if args.pattern:
        try:
            regex = re.compile(args.pattern)
            roles = [role for role in roles if regex.search(role['role_name'])]
        except re.error as e:
            return err(f"cli.select.select_roles: invalid regex pattern '{args.pattern}': {e}")

    if args.missing:
        # Find filings that don't appear in the matching roles
        matched_access_nos = set(role["access_no"] for role in roles)
        missing_access_nos = [x for x in access_nos if x not in matched_access_nos]
        
        # Get filing records for the missing access numbers
        result = db.queries.filings.select_by_entity(conn, access_nos=missing_access_nos)
        if is_not_ok(result):
            return result
        
        missing_filings = result[1]
        
        # Apply column processing with filing columns
        default_cols = ['name', 'ticker', 'cik', 'access_no', 'filing_date', 'form_type']
        result = cli.shared.process_cols(missing_filings, args.cols, default_cols)
        if is_not_ok(result):
            return result
        missing_filings, _ = result[1]
        
        return ok({"name": "filings", "data": missing_filings})
    else:
        # Normal behavior - return role records
        default_cols = ['name', 'ticker', 'cik', 'access_no', 'filing_date', 'form_type', 'role_name']
        result = cli.shared.process_cols(roles, args.cols, default_cols)
        if is_not_ok(result):
            return result
        roles, _ = result[1]

        # Apply uniqueness filter if requested
        if args.uniq:
            roles = _deduplicate_rows(roles)

        return ok({"name": "roles", "data": roles})   


def _get_concept_source(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[list[dict], str]:
    """Extract concepts from filing-role combinations or ticker-group."""
    
    # Check for explicit sources first
    query_pairs = []
    
    if args.access and args.role:
        query_pairs.append((args.access, args.role))
    
    for item in cmd["data"]:
        if "access_no" in item and "role_name" in item:
            query_pairs.append((item["access_no"], item["role_name"]))
    
    # If we have explicit sources, use them
    if query_pairs:
        return _get_concept_source_from_filings_and_roles(conn, query_pairs)
    
    # Fallback to ticker and group if provided
    if args.ticker and args.group:
        return _get_concept_source_from_ticker_and_group(conn, args)
    
    # No sources available
    return err("cli.select.select_concepts: no filing-role pairs provided. Use --access + --role, pipe filing-role data, or use --ticker + --group.")


def _get_concept_source_from_filings_and_roles(conn: sqlite3.Connection, query_pairs: list[tuple[str, str]]) -> Result[list[dict], str]:
    """Extract concepts from explicit filing-role combinations."""
    
    concepts = []
    for access_no, role_name in query_pairs:
        result = db.queries.concepts.select_by_role(conn, access_no, role_name)
        if is_not_ok(result):
            continue
        
        filing_concepts = result[1]
        for concept in filing_concepts:
            concept['access_no'] = access_no
            concept['role_name'] = role_name
            concept['taxonomy_name'] = xbrl.facts.taxonomy_name(concept['taxonomy'])
            concept['concept_name'] = None
            concept['pattern'] = None
        concepts.extend(filing_concepts)   

    return ok(concepts)


def _get_concept_source_from_ticker_and_group(conn: sqlite3.Connection, args) -> Result[list[dict], str]:
    """Extract concepts using ticker and group patterns (applies to all cached filings)."""
    
    # 1. Resolve ticker to entity
    result = db.queries.entities.get(conn, ticker=args.ticker)
    if is_not_ok(result):
        return result
    
    entity = result[1]
    if not entity:
        return err(f"cli.select._get_concept_source_from_ticker_and_group: ticker '{args.ticker}' not found in database")
    
    cik = entity["cik"]
    
    # 2. Get group_id
    result = db.queries.groups.get_id(conn, args.group)
    if is_not_ok(result):
        return result
    
    group_id = result[1]
    if group_id is None:
        return err(f"cli.select._get_concept_source_from_ticker_and_group: group '{args.group}' not found")
    
    # 3. Check if group has role patterns (warn if not)
    result = db.queries.role_patterns.select_by_group(conn, group_id, cik)
    if is_not_ok(result):
        return result
    
    role_patterns = result[1]
    if not role_patterns:
        return err(f"cli.select._get_concept_source_from_ticker_and_group: group '{args.group}' has no role patterns defined for {args.ticker.upper()}.")
    
    # 4. Use dynamic concept matching to get all matching concepts
    search_field = "name" if args.label else "tag"
    result = db.queries.concepts.select_by_pattern(conn, group_id, cik, args.name, search_field)
    if is_not_ok(result):
        return result

    concepts = result[1]

    # 5. Format results consistently with explicit extraction
    # Note: access_no and role_name will be empty for ticker-based queries
    # since concepts come from multiple filings/roles
    for concept in concepts:
        concept['access_no'] = ""  # Multiple filings
        concept['role_name'] = ""  # Multiple roles
        concept['taxonomy_name'] = xbrl.facts.taxonomy_name(concept['taxonomy'])
        # concept_name and pattern are already set by select_by_pattern
    
    return ok(concepts)


def _filter_concepts_by_group(conn: sqlite3.Connection, concepts: list[dict], args) -> Result[list[dict], str]:
    """Filter concepts using group patterns."""
    
    if not concepts:
        return ok([])
    
    cik = concepts[0].get("cik")
    if not cik:
        return err("_filter_concepts_by_group: concepts missing CIK field")
    
    result = db.queries.groups.get_id(conn, args.group)
    if is_not_ok(result):
        return result
    
    group_id = result[1]
    if group_id is None:
        return err(f"_filter_concepts_by_group: group '{args.group}' not found")
    
    # Get all concept patterns for this group/cik
    result = db.queries.concept_patterns.select_by_group(conn, group_id, cik)
    if is_not_ok(result):
        return result
    
    patterns = result[1]
    
    # Apply name filter if specified
    if args.name:
        patterns = [p for p in patterns if p["name"] == args.name]
    
    if not patterns:
        return ok([])
    
    # Apply each pattern to the concepts
    filtered_concepts = []
    for pattern_record in patterns:
        pattern_text = pattern_record["pattern"]
        pattern_name = pattern_record["name"]
        
        try:
            regex = re.compile(pattern_text)
        except re.error as e:
            return err(f"_filter_concepts_by_group: invalid regex '{pattern_text}': {e}")
        
        for concept in concepts:
            field_value = concept.get("name", "") if args.label else concept.get("tag", "")
            if regex.search(field_value):    
                filtered_concept = dict(concept)
                filtered_concept["concept_name"] = pattern_name
                filtered_concept["pattern"] = pattern_text
                filtered_concepts.append(filtered_concept)
    
    return ok(filtered_concepts)


def _filter_concepts_by_pattern(concepts: list[dict], pattern: str, use_label: bool) -> Result[list[dict], str]:
    """Filter concepts using regex pattern on tag field."""

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return err(f"_filter_concepts_by_pattern: invalid regex pattern '{pattern}': {e}")

    filtered_concepts = []
    for concept in concepts:
        field_value = concept.get('name', '') if use_label else concept.get('tag', '')
        if regex.search(field_value):
            filtered_concepts.append(concept)

    return ok(filtered_concepts)


def select_concepts(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Unified concept selection with filtering options.
    
    Supports multiple extraction modes:
    1. Explicit filing-role: --access + --role or pipeline data
    2. Ticker+group: --ticker + --group
    
    Filtering chain (all optional, can be combined):
    1. Extract concepts from sources
    2. Apply group pattern filtering (--group)  
    3. Apply additional regex filtering (--pattern)
    
    Examples:
      edgar select concepts --access X --role Y --pattern ".*Cash.*"
      edgar select concepts --ticker AEO --group balance --name "cash"
      edgar select concepts --ticker AEO --group balance --pattern ".*Assets.*"
    """
    
    # Step 1: Extract concepts from sources (explicit or ticker-based)
    result = _get_concept_source(conn, cmd, args)
    if is_not_ok(result):
        return result
    
    concepts = result[1]
    
    # Track the universe of filing-role pairs for missing functionality
    universe_pairs = set()
    for concept in concepts:
        access_no = concept.get('access_no', '')
        role_name = concept.get('role_name', '')
        if access_no and role_name:  # Only explicit filing-role pairs
            universe_pairs.add((access_no, role_name))
    
    # Step 2: Apply group pattern filtering (if requested)
    if args.group:
        result = _filter_concepts_by_group(conn, concepts, args)
        if is_not_ok(result):
            return result
        concepts = result[1]
    
    # Step 3: Apply additional regex pattern filtering (if requested)
    if args.pattern:
        result = _filter_concepts_by_pattern(concepts, args.pattern, args.label)
        if is_not_ok(result):
            return result
        concepts = result[1]
    
    # Step 4: Handle missing flag or return normal results
    if args.missing:
        # Only works with explicit filing-role pairs
        if not universe_pairs:
            return err("cli.select.select_concepts: --missing requires explicit filing-role pairs. Use --access + --role or pipe filing-role data.")
        
        # Find filing-role pairs that don't appear in matching concepts
        matched_pairs = set()
        for concept in concepts:
            access_no = concept.get('access_no', '')
            role_name = concept.get('role_name', '')
            if access_no and role_name:
                matched_pairs.add((access_no, role_name))
        
        missing_pairs = universe_pairs - matched_pairs
        
        # Convert missing pairs back to role records
        missing_roles = []
        for access_no, role_name in missing_pairs:
            # Get filing info for context
            result = db.queries.filings.get_with_entity(conn, access_no)
            if is_not_ok(result) or not result[1]:
                continue
                
            filing_info = result[1]
            missing_roles.append({
                "name": filing_info["name"],
                "ticker": filing_info["ticker"],
                "cik": filing_info["cik"],
                "access_no": access_no,
                "filing_date": filing_info["filing_date"],
                "form_type": filing_info["form_type"],
                "role_name": role_name
            })
        
        # Apply column processing with role columns
        default_cols = ['access_no', 'filing_date', 'form_type', 'role_name']
        result = cli.shared.process_cols(missing_roles, args.cols, default_cols)
        if is_not_ok(result):
            return result
        missing_roles, _ = result[1]
        
        return ok({"name": "roles", "data": missing_roles})
    else:
        # Normal behavior - return concept records
        default_cols = [
            'cid', 'cik', 'access_no', 'role_name',
            'taxonomy_name', 'tag', 'name', 'concept_name', 'pattern'
        ]
        result = cli.shared.process_cols(concepts, args.cols, default_cols)
        if is_not_ok(result):
            return result
        concepts, _ = result[1]

        # Apply uniqueness filter if requested
        if args.uniq:
            concepts = _deduplicate_rows(concepts)

        return ok({"name": "concepts", "data": concepts})


def _filter_patterns_by_name(patterns: list[dict], pattern: str) -> Result[list[dict], str]:
    """Filter concept patterns by name using regex."""
    try:
        regex = re.compile(pattern)
        filtered = [p for p in patterns if p["type"] == "concept" and p["name"] and regex.search(p["name"])]
        return ok(filtered)
    except re.error as e:
        return err(f"_filter_patterns_by_name: invalid regex pattern '{pattern}': {e}")


def select_patterns(conn: sqlite3.Connection, cmd: Cmd, args) -> Result[Cmd, str]:
    """
    Select patterns with flexible filtering:
    - All patterns: ep select patterns --type roles|concepts|all
    - By ticker: ep select patterns -t TICKER --type roles
    - By group: ep select patterns -g GROUP --type roles
    - By ticker+group: ep select patterns -t TICKER -g GROUP
    - By UID: ep select patterns --uid 1 2 3
    """

    # Route to appropriate fetch strategy
    if args.uid:
        # UID-based lookup (concept patterns only)
        result = _fetch_patterns_by_uid(conn, args.uid, args.type, args.ticker)
    else:
        # General pattern selection (ticker and/or group optional)
        result = _fetch_patterns_general(conn, args.ticker, args.group, args.type)

    if is_not_ok(result):
        return result

    patterns = result[1]

    # Apply concept name filtering if specified
    if args.pattern:
        result = _filter_patterns_by_name(patterns, args.pattern)
        if is_not_ok(result):
            return result
        patterns = result[1]

    # Consistent columns (only show user-visible IDs)
    # Note: pid is included in data for delete command but hidden from default display
    default_cols = ['uid', 'type', 'ticker', 'cik', 'group_name', 'name', 'pattern', 'note']

    result = cli.shared.process_cols(patterns, args.cols, default_cols)
    if is_not_ok(result):
        return result
    patterns, valid_cols = result[1]

    # Rebuild rows with only display columns (exclude internal pid)
    display_patterns = [{col: row[col] for col in valid_cols if col in row} for row in patterns]

    return ok({"name": "patterns", "data": display_patterns})


def format_pattern_record(pattern: dict, pattern_type: str, **kwargs) -> dict:
    """Format pattern record with consistent structure."""
    return {
        "pid": pattern["pid"],  # Required for delete command
        "uid": pattern.get("uid"),
        "type": pattern_type,
        "ticker": kwargs.get("ticker", ""),
        "cik": kwargs.get("cik", ""),
        "group_name": kwargs.get("group_name", ""),
        "name": kwargs.get("name", ""),
        "pattern": pattern["pattern"],
        "note": pattern.get("note", ""),
    }


def _fetch_patterns_general(conn: sqlite3.Connection, ticker: Optional[str], group: Optional[str],
                            pattern_type: str) -> Result[list[dict], str]:
    """
    Fetch patterns with flexible filtering.

    Args:
        ticker: Filter by company ticker (None = all companies)
        group: Filter by group name (None = all groups)
        pattern_type: Type of patterns to fetch (roles/concepts/all)

    Returns patterns with entity information joined.
    """

    # Resolve ticker to CIK if provided
    cik = None
    if ticker:
        result = db.queries.entities.get(conn, ticker=ticker)
        if is_not_ok(result):
            return result

        entity = result[1]
        if not entity:
            return err(f"_fetch_patterns_general: ticker '{ticker}' not found")

        cik = entity["cik"]

    patterns = []

    # Fetch role patterns
    if pattern_type in ["roles", "all"]:
        result = db.queries.role_patterns.select(conn, group, cik)
        if is_not_ok(result):
            return result

        for p in result[1]:
            # Join entity info for each pattern
            entity_result = db.queries.entities.get(conn, cik=p["cik"])
            pattern_ticker = ""
            if is_ok(entity_result) and entity_result[1]:
                pattern_ticker = entity_result[1]["ticker"]

            patterns.append(format_pattern_record(
                p, "role",
                ticker=pattern_ticker,
                cik=p["cik"],
                group_name=p["group_name"],
                name=p["name"]
            ))

    # Fetch concept patterns
    if pattern_type in ["concepts", "all"]:
        result = db.queries.concept_patterns.select(conn, group, cik)
        if is_not_ok(result):
            return result

        for p in result[1]:
            # Join entity info for each pattern
            entity_result = db.queries.entities.get(conn, cik=p["cik"])
            pattern_ticker = ""
            if is_ok(entity_result) and entity_result[1]:
                pattern_ticker = entity_result[1]["ticker"]

            patterns.append(format_pattern_record(
                p, "concept",
                ticker=pattern_ticker,
                cik=p["cik"],
                group_name=p["group_name"],
                name=p["name"]
            ))

    return ok(patterns)


def _fetch_patterns_by_uid(conn: sqlite3.Connection,
                                user_ids: list[int],
                                pattern_type: str,
                                ticker_filter: str = None) -> Result[list[dict], str]:
    """
    Fetch patterns by user ID without group filtering (global lookup).
    If ticker_filter specified, only returns patterns belonging to that company.
    """
    
    # Resolve ticker filter to CIK if provided
    filter_cik = None
    if ticker_filter:
        result = db.queries.entities.get(conn, ticker=ticker_filter)
        if is_not_ok(result):
            return result
        
        entity = result[1]
        if not entity:
            return err(f"_fetch_patterns_by_id: ticker '{ticker_filter}' not found")
        
        filter_cik = entity["cik"]
    
    patterns = []

    for user_id in user_ids:
        # NOTE: Role patterns don't have UIDs (they use names instead)
        # Only concept patterns support UID lookup
        if pattern_type in ["roles"]:
            return err(f"_fetch_patterns_by_uid: role patterns don't support UID lookup (use --type concepts)")

        # Try concept pattern
        if pattern_type in ["concepts", "all"]:
            result = db.queries.concept_patterns.get_with_entity(conn, filter_cik, str(user_id))
            if is_not_ok(result):
                return result

            if result[1]:
                p = result[1]

                patterns.append(format_pattern_record(
                    p, "concept",
                    ticker=p["ticker"],
                    cik=p["cik"],
                    group_name="",
                    name=p["name"]
                ))
            else:
                return err(f"_fetch_patterns_by_uid: user ID {user_id} not found")
    
    return ok(patterns)
