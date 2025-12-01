"""
CLI: build

Build database from ep.toml configuration. Validates schema and extracts facts.
"""
import sys
import sqlite3
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn

# Local modules
from edgar import config
from edgar import db
from edgar import cache
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_not_ok, is_ok


# =============================================================================
# Build Functions
# =============================================================================

def add_arguments(subparsers):
    """Add build command to argument parser."""
    parser_build = subparsers.add_parser("build", help="build database from ep.toml configuration")
    parser_build.add_argument("groups", nargs="*", help="groups to build (default: all groups)")
    parser_build.add_argument("-c", "--check", action="store_true", help="validate ep.toml and report status (no build)")
    parser_build.add_argument("-s", "--status", action="store_true", help="show build status (groups, filings, facts)")
    parser_build.add_argument("-v", "--verbose", action="store_true", help="show detailed output (role/concept patterns, full stats)")
    parser_build.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """
    Build database from ep.toml configuration.

    Args:
        cmd: Command context
        args: Parsed arguments

    Returns:
        ok(None) - Normal completion
        err(str) - Error occurred
    """
    # Load ep.toml configuration
    try:
        root, cfg = config.load_toml()
    except RuntimeError as e:
        return err(f"cli.build.run: {e}")

    # Validate configuration
    errors, warnings = config.validate(cfg)

    # Print warnings
    if warnings:
        print(f"⚠ Found {len(warnings)} warning(s):")
        for warning in warnings:
            print(f"  {warning}")
        print()

    # Print errors (if any)
    if errors:
        print(f"✗ Found {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        print(file=sys.stderr)
        return err("cli.build.run: validation failed")

    # If --check flag, just validate and report
    if args.check:
        return run_check(root, cfg)

    # If --status flag, show build status
    if args.status:
        return run_status(root, cfg)

    # Otherwise, build database
    groups = args.groups if args.groups else []
    verbose = args.verbose
    return run_build(root, cfg, groups, verbose)


def resolve_group_dependencies(groups_config: dict, requested_groups: list[str]) -> set[str]:
    """
    Resolve group dependencies by recursively including parent groups.

    Args:
        groups_config: Groups section from ep.toml
        requested_groups: List of group names requested by user

    Returns:
        Set of all groups including dependencies
    """
    result = set()

    def add_with_parents(group_name: str):
        if group_name in result:
            return  # Already processed

        result.add(group_name)

        # Check if this group has a parent
        group_spec = groups_config.get(group_name, {})
        parent_name = group_spec.get("from")

        if parent_name:
            # Recursively add parent and its dependencies
            add_with_parents(parent_name)

    for group_name in requested_groups:
        add_with_parents(group_name)

    return result


def order_groups(groups_config: dict, groups: set[str]) -> list[str]:
    """
    Order groups so main groups come before derived groups (topological sort).

    Args:
        groups_config: Groups section from ep.toml
        groups: Set of group names to order

    Returns:
        Ordered list of group names
    """
    # Separate main groups (no 'from') and derived groups (have 'from')
    main_groups = []
    derived_groups = []

    for group_name in groups:
        group_spec = groups_config.get(group_name, {})
        if "from" in group_spec:
            derived_groups.append(group_name)
        else:
            main_groups.append(group_name)

    # Sort each category alphabetically for deterministic ordering
    main_groups.sort()
    derived_groups.sort()

    # Main groups first, then derived
    return main_groups + derived_groups


def run_check(root, cfg: dict) -> Result[None, str]:
    """Validate ep.toml and report status."""
    ticker = config.get_ticker(cfg)
    cik = config.get_cik(cfg)
    db_path = config.get_db_path(root, cfg)

    print("✓ Configuration is valid\n")
    print(f"Workspace: {root}")
    print(f"  Ticker: {ticker}")
    print(f"  CIK: {cik}")
    print(f"  Database: {db_path}")

    # Count schema elements
    num_roles = len(cfg.get("roles", {}))
    num_concepts = len(cfg.get("concepts", {}))
    num_groups = len(cfg.get("groups", {}))

    print(f"\nSchema:")
    print(f"  Roles: {num_roles}")
    print(f"  Concepts: {num_concepts}")
    print(f"  Groups: {num_groups}")

    return ok(None)


def run_status(root, cfg: dict) -> Result[None, str]:
    """Show build status: groups, filings, and facts."""
    ticker = config.get_ticker(cfg)
    db_path = config.get_db_path(root, cfg)

    print(f"Database: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)

    # Check if database is initialized
    result = db.store.select(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name='groups'", ())
    if is_not_ok(result) or not result[1]:
        conn.close()
        print("Database not initialized. Run 'ep build' first.")
        return ok(None)

    # Get entity info (CIK) from database
    result = db.queries.entities.select(conn, tickers=[ticker])
    if is_not_ok(result) or not result[1]:
        conn.close()
        print(f"Entity '{ticker}' not found in database. Run 'ep build' first.")
        return ok(None)

    entity = result[1][0]
    cik = entity["cik"]

    print(f"Ticker: {ticker} (CIK: {cik})\n")

    # Get all groups
    result = db.queries.groups.select(conn)
    if is_not_ok(result):
        conn.close()
        return err(f"Failed to query groups: {result[1]}")

    groups = result[1]
    if not groups:
        conn.close()
        print("No groups defined. Run 'ep build' first.")
        return ok(None)

    # Get total filings
    result = db.queries.filings.select_by_entity(conn, ciks=[cik])
    if is_not_ok(result):
        conn.close()
        return err(f"Failed to query filings: {result[1]}")

    all_filings = result[1]
    total_filings = len(all_filings)

    print("Groups:")

    for group in groups:
        gid = group["gid"]
        group_name = group["group_name"]

        # Get pattern count for this group
        result = db.queries.groups.count_patterns(conn, gid)
        if is_ok(result):
            pattern_count = result[1]
        else:
            pattern_count = 0

        # Get processed filings count for this group
        result = db.queries.concept_patterns.select_by_group(conn, gid, cik)
        if is_ok(result):
            concept_patterns = result[1]
            pattern_ids = [p["pid"] for p in concept_patterns]

            processed_count = 0
            for filing in all_filings:
                result = db.queries.filing_patterns_processed.is_fully_processed(
                    conn, filing["access_no"], pattern_ids)
                if is_ok(result) and result[1]:
                    processed_count += 1
        else:
            processed_count = 0

        # Format output
        print(f"  {group_name:30s} {pattern_count:3d} patterns  {processed_count:3d}/{total_filings:<3d} filings")

    # Get total facts count
    result = db.queries.facts.count(conn, cik)
    if is_ok(result):
        total_facts = result[1]
    else:
        total_facts = 0

    print(f"\nTotal: {len(groups)} groups, {total_filings} filings, {total_facts:,} facts")

    conn.close()
    return ok(None)


def run_build(root, cfg: dict, groups: list[str], verbose: bool = False) -> Result[None, str]:
    """Build database from ep.toml configuration."""
    ticker = config.get_ticker(cfg)
    db_path = config.get_db_path(root, cfg)

    print(f"Building database: {db_path}")
    print(f"Ticker: {ticker}\n")

    # Determine which groups to process
    groups_config = cfg.get("groups", {})

    if not groups:
        # No groups specified - process all groups
        requested_groups = list(groups_config.keys())
        print(f"Processing all {len(requested_groups)} groups...")
    else:
        # Validate requested groups exist
        invalid_groups = [g for g in groups if g not in groups_config]
        if invalid_groups:
            available = ", ".join(sorted(groups_config.keys()))
            return err(f"cli.build.run_build: unknown groups: {', '.join(invalid_groups)}. Available groups: {available}")

        requested_groups = groups
        print(f"Processing {len(requested_groups)} group(s): {', '.join(requested_groups)}...")

    # Resolve dependencies: include parent groups for derived groups
    groups_with_deps = resolve_group_dependencies(groups_config, requested_groups)

    # Order groups: main groups first, then derived (topological sort)
    groups_to_process = order_groups(groups_config, groups_with_deps)

    if len(groups_to_process) > len(requested_groups):
        added = set(groups_to_process) - set(requested_groups)
        print(f"Added {len(added)} parent group(s): {', '.join(sorted(added))}\n")

    # Separate main and derived groups for display
    main_groups = [g for g in groups_to_process if "from" not in groups_config.get(g, {})]
    derived_groups = [g for g in groups_to_process if "from" in groups_config.get(g, {})]

    if main_groups:
        print(f"Main groups ({len(main_groups)}):")
        for group in main_groups:
            print(f"  - {group}")
        print()

    if derived_groups:
        print(f"Derived groups ({len(derived_groups)}):")
        # Group by parent
        by_parent = {}
        for group in derived_groups:
            parent = groups_config[group]["from"]
            if parent not in by_parent:
                by_parent[parent] = []
            by_parent[parent].append(group)

        # Print grouped by parent
        for parent in sorted(by_parent.keys()):
            print(f"  from {parent}:")
            for group in by_parent[parent]:
                print(f"    - {group}")
        print()

    # Connect to database
    user_agent = config.get_user_agent(cfg)
    conn = sqlite3.connect(db_path)

    # Initialize database schema
    result = db.store.init(conn)
    if is_not_ok(result):
        conn.close()
        return err(f"cli.build.run_build: failed to initialize database: {result[1]}")

    # Resolve company entity (fetch from SEC if not in database)
    result = cache.resolve_entities(conn, user_agent, [ticker])
    if is_not_ok(result):
        conn.close()
        return err(f"cli.build.run_build: failed to resolve entity: {result[1]}")

    entities, source = result[1]
    if not entities:
        conn.close()
        return err(f"cli.build.run_build: ticker '{ticker}' not found in SEC database")

    entity = entities[0]
    cik = entity["cik"]

    if source == "sec":
        print(f"Fetched company: {entity['name']} (CIK: {cik})\n")
    else:
        print(f"Found company: {entity['name']} (CIK: {cik})\n")

    # Determine cutoff date for filing fetch (default: 10 years ago)
    from datetime import datetime, timedelta
    cutoff = cfg.get("cutoff")
    if not cutoff:
        ten_years_ago = datetime.now() - timedelta(days=365*10)
        cutoff = ten_years_ago.strftime("%Y-%m-%d")

    # Fetch all filings once (always check SEC for latest filings)
    print(f"Fetching filings from SEC (after {cutoff})...", end=" ", flush=True)
    date_filters = [("filing_date", ">", cutoff)]
    result = cache.resolve_filings(conn, user_agent, cik, form_types={'10-Q', '10-K'}, date_filters=date_filters, force=True)
    if is_not_ok(result):
        conn.close()
        return err(f"cli.build.run_build: failed to fetch filings: {result[1]}")

    all_filings, source = result[1]
    if source == "sec":
        print(f"cached {len(all_filings)} filings\n")
    else:
        print(f"found {len(all_filings)} filings\n")

    if not all_filings:
        conn.commit()
        conn.close()
        print("✓ Build complete (no filings to process)")
        return ok(None)

    # Step 4.5: Probe all roles for all filings upfront (cache role names)
    total_roles = 0
    fetched_count = 0
    cached_count = 0

    if verbose:
        # Verbose mode - show each filing
        print(f"Probing roles for {len(all_filings)} filing(s)...")
        for i, filing in enumerate(all_filings, 1):
            access_no = filing["access_no"]
            filing_date = filing.get("filing_date", "?")
            print(f"  [{i:2d}/{len(all_filings)}] {access_no} {filing_date}...", end=" ", flush=True)

            result = cache.resolve_roles(conn, user_agent, cik, access_no)
            if is_not_ok(result):
                print(f"failed: {result[1]}")
                continue

            roles, source = result[1]
            total_roles += len(roles)

            if source == "sec":
                print(f"cached {len(roles)} roles")
                fetched_count += 1
            else:
                print(f"found {len(roles)} roles")
                cached_count += 1
    else:
        # Non-verbose mode - use progress bar
        with Progress(
            TextColumn("  Probing roles:"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TextColumn("[cyan]{task.fields[current]}"),
        ) as progress:
            task = progress.add_task("Probing", total=len(all_filings), current="")

            for filing in all_filings:
                access_no = filing["access_no"]
                filing_date = filing.get("filing_date", "?")

                result = cache.resolve_roles(conn, user_agent, cik, access_no)
                if is_not_ok(result):
                    progress.update(task, advance=1, current=f"{access_no} {filing_date}: ERROR")
                    continue

                roles, source = result[1]
                total_roles += len(roles)

                if source == "sec":
                    progress.update(task, advance=1, current=f"{access_no} {filing_date}: cached {len(roles)} roles")
                    fetched_count += 1
                else:
                    progress.update(task, advance=1, current=f"{access_no} {filing_date}: found {len(roles)} roles")
                    cached_count += 1

    if fetched_count > 0 and cached_count > 0:
        print(f"✓ Probed {len(all_filings)} filings: {total_roles} total roles ({fetched_count} from SEC, {cached_count} from DB)\n")
    elif fetched_count > 0:
        print(f"✓ Probed {len(all_filings)} filings: {total_roles} total roles (all from SEC)\n")
    else:
        print(f"✓ Probed {len(all_filings)} filings: {total_roles} total roles (all from DB)\n")

    # Process groups one at a time
    for i, group_name in enumerate(groups_to_process, 1):
        result = build_group(conn, cik, ticker, user_agent, cfg, group_name, all_filings, i, len(groups_to_process), verbose)
        if is_not_ok(result):
            print(f"ERROR: Failed to build group '{group_name}': {result[1]}")
            # Continue with other groups instead of failing completely
            continue

    conn.commit()
    conn.close()

    print("\n✓ Build complete")
    return ok(None)


def build_group(conn, cik: str, ticker: str, user_agent: str, cfg: dict, group_name: str, all_filings: list,
                group_index: int = 1, total_groups: int = 1, verbose: bool = False) -> Result[None, str]:
    """
    Build a single group: populate schema and extract facts.

    Args:
        conn: Database connection
        cik: Company CIK
        ticker: Company ticker
        user_agent: SEC API user agent
        cfg: Full ep.toml configuration
        group_name: Name of group to build
        all_filings: List of all available filings
        group_index: Current group number (1-based)
        total_groups: Total number of groups being processed
        verbose: Show detailed output if True

    Returns:
        ok(None) on success, err(str) on failure
    """
    from edgar import xbrl
    from edgar.cli.update import _update_filing

    groups_config = cfg.get("groups", {})
    group_spec = groups_config.get(group_name, {})

    # Check if this is a derived group (has 'from' field)
    is_derived = "from" in group_spec

    # Print header (different format for derived vs main groups)
    if not is_derived:
        print(f"[{group_name}]")

    # Step 1: Populate schema for this group
    # Get role name (inherit from parent if needed)
    role_name = group_spec.get("role")
    if not role_name and "from" in group_spec:
        parent_name = group_spec["from"]
        parent_spec = groups_config.get(parent_name, {})
        role_name = parent_spec.get("role")

    # Insert role pattern if not already present
    if role_name:
        roles_to_insert = {role_name: cfg.get("roles", {}).get(role_name, {})}
        result = roles(conn, cik, roles_to_insert, verbose)
        if is_not_ok(result):
            return err(f"build_group: failed to insert role '{role_name}': {result[1]}")

    # Insert concept patterns for concepts in this group
    concept_uids = group_spec.get("concepts", [])
    concepts_config = cfg.get("concepts", {})
    concepts_to_insert = {}

    for concept_name, concept_def in concepts_config.items():
        if concept_def.get("uid") in concept_uids:
            concepts_to_insert[concept_name] = concept_def

    result = concepts(conn, cik, concepts_to_insert, verbose)
    if is_not_ok(result):
        return err(f"build_group: failed to insert concepts: {result[1]}")

    # Insert group and link to role/concepts
    result = groups(conn, cik, cfg, [group_name])
    if is_not_ok(result):
        return err(f"build_group: failed to insert group: {result[1]}")

    # If this is a derived group, we're done - facts are already extracted by parent
    if is_derived:
        parent_name = group_spec["from"]
        print(f"[{group_index:2d}/{total_groups}] {group_name} derived from {parent_name}")
        return ok(None)

    # Step 2: Get pattern IDs for this group to check processed status
    concept_uids = group_spec.get("concepts", [])
    pattern_ids = []
    for uid in concept_uids:
        result_pattern = db.queries.concept_patterns.get_by_uid(conn, cik, uid)
        if is_ok(result_pattern) and result_pattern[1]:
            pattern_ids.append(result_pattern[1]["pid"])

    # Check if all filings are already processed
    all_processed = True
    for filing in all_filings:
        result = db.queries.filing_patterns_processed.is_fully_processed(conn, filing["access_no"], pattern_ids)
        if is_ok(result) and not result[1]:
            all_processed = False
            break

    if all_processed and pattern_ids:
        print(f"  ✓ All {len(all_filings)} filings already processed\n")
        return ok(None)

    # Step 3: Extract facts from filings for this group
    stats_total = {"candidates": 0, "chosen": 0, "inserted": 0}

    if verbose:
        # Verbose mode - show detailed output for each filing
        print(f"  Processing {len(all_filings)} filing(s)...\n")

        for idx, filing in enumerate(all_filings, 1):
            access_no = filing["access_no"]
            filing_date = filing.get("filing_date", "?")

            # Check if this filing is already processed
            result = db.queries.filing_patterns_processed.is_fully_processed(conn, access_no, pattern_ids)
            if is_ok(result) and result[1]:
                print(f"  [{idx}/{len(all_filings)}] {access_no} {filing_date}: already processed")
                continue

            # Match roles against this specific group (roles already probed upfront)
            result = db.queries.role_patterns.match_groups_for_filing(conn, cik, access_no)
            if is_not_ok(result):
                print(f"  [{idx}/{len(all_filings)}] {access_no} {filing_date}: ERROR matching roles")
                continue

            role_map = result[1]
            if not role_map or group_name not in role_map:
                print(f"  [{idx}/{len(all_filings)}] {access_no} {filing_date}: SKIP (no matching roles)")
                continue

            # Filter to only this group
            role_map_filtered = {group_name: role_map[group_name]}

            # Probe concepts for matched roles
            for role_tail in role_map_filtered[group_name]:
                result = cache.resolve_concepts(conn, user_agent, cik, access_no, role_tail)
                if is_not_ok(result):
                    print(f"  [{idx}/{len(all_filings)}] {access_no} {filing_date}: WARN probing concepts for {role_tail}")
                # Don't need to extract the data here, just ensuring concepts are cached

            # Extract facts for this group
            result = _update_filing(conn, cik, access_no, role_map_filtered)

            if is_ok(result):
                stats = result[1]
                stats_total["candidates"] += stats["candidates"]
                stats_total["chosen"] += stats["chosen"]
                stats_total["inserted"] += stats["inserted"]
                print(f"  [{idx}/{len(all_filings)}] {access_no} {filing_date} {stats['fiscal_period']}: "
                      f"cand={stats['candidates']} chosen={stats['chosen']} inserted={stats['inserted']}")
            else:
                print(f"  [{idx}/{len(all_filings)}] {access_no} {filing_date}: ERROR extracting facts: {result[1]}")

            # Mark all concept patterns for this group as processed (regardless of success/failure)
            # This enables incremental builds to skip this filing next time
            for pid in pattern_ids:
                db.queries.filing_patterns_processed.insert(conn, access_no, pid)

        print(f"  ✓ Processed {len(all_filings)} filing(s): "
              f"{stats_total['candidates']} candidates, "
              f"{stats_total['chosen']} chosen, "
              f"{stats_total['inserted']} inserted\n")
    else:
        # Non-verbose mode - use progress bar
        with Progress(
            TextColumn("  Processing:"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("({task.completed}/{task.total})"),
            TextColumn("[cyan]{task.fields[current]}"),
            TimeRemainingColumn(),
        ) as progress:
            task = progress.add_task("Processing", total=len(all_filings), current="")

            for filing in all_filings:
                access_no = filing["access_no"]
                filing_date = filing.get("filing_date", "?")

                # Check if this filing is already processed
                result = db.queries.filing_patterns_processed.is_fully_processed(conn, access_no, pattern_ids)
                if is_ok(result) and result[1]:
                    progress.update(task, advance=1, current=f"{access_no} {filing_date}: already processed")
                    continue

                # Match roles against this specific group (roles already probed upfront)
                result = db.queries.role_patterns.match_groups_for_filing(conn, cik, access_no)
                if is_not_ok(result):
                    progress.update(task, advance=1, current=f"{access_no} {filing_date}: ERROR")
                    continue

                role_map = result[1]
                if not role_map or group_name not in role_map:
                    progress.update(task, advance=1, current=f"{access_no} {filing_date}: SKIP")
                    continue

                # Filter to only this group
                role_map_filtered = {group_name: role_map[group_name]}

                # Probe concepts for matched roles
                for role_tail in role_map_filtered[group_name]:
                    result = cache.resolve_concepts(conn, user_agent, cik, access_no, role_tail)
                    # Don't need to extract the data here, just ensuring concepts are cached

                # Extract facts for this group
                result = _update_filing(conn, cik, access_no, role_map_filtered)

                if is_ok(result):
                    stats = result[1]
                    stats_total["candidates"] += stats["candidates"]
                    stats_total["chosen"] += stats["chosen"]
                    stats_total["inserted"] += stats["inserted"]
                    progress.update(task, advance=1,
                                  current=f"{access_no} {filing_date} {stats['fiscal_period']}: {stats['inserted']} facts")
                else:
                    progress.update(task, advance=1, current=f"{access_no} {filing_date}: ERROR")

                # Mark all concept patterns for this group as processed (regardless of success/failure)
                # This enables incremental builds to skip this filing next time
                for pid in pattern_ids:
                    db.queries.filing_patterns_processed.insert(conn, access_no, pid)

        print(f"  ✓ Processed {len(all_filings)} filing(s), inserted {stats_total['inserted']} facts\n")

    return ok(None)


def roles(conn, cik: str, roles_config: dict, verbose: bool = False) -> Result[None, str]:
    """
    Populate role patterns from ep.toml (idempotent).

    Called as: build.roles(conn, cik, roles_config, verbose)

    Args:
        conn: Database connection
        cik: Company CIK
        roles_config: Roles section from ep.toml
        verbose: Show detailed output if True

    Returns:
        ok(None) on success, err(str) on failure
    """
    if verbose:
        # Detailed output - show each role pattern
        for role_name, role_spec in roles_config.items():
            pattern = role_spec["pattern"]
            note = role_spec.get("note", "")

            print(f"  Role pattern:")
            print(f"    Name: {role_name}")
            print(f"    Pattern: {pattern}")
            if note:
                print(f"    Note: {note}")

            # Try to insert (idempotent - ignore if exists)
            result = db.queries.role_patterns.insert(conn, cik, role_name, pattern, note)
            if is_not_ok(result):
                # If already exists, that's fine
                if "already exists" not in result[1]:
                    return err(f"build.roles: failed to insert '{role_name}': {result[1]}")
    else:
        # Summary output - just show count
        for role_name, role_spec in roles_config.items():
            pattern = role_spec["pattern"]
            note = role_spec.get("note", "")

            # Try to insert (idempotent - ignore if exists)
            result = db.queries.role_patterns.insert(conn, cik, role_name, pattern, note)
            if is_not_ok(result):
                # If already exists, that's fine
                if "already exists" not in result[1]:
                    return err(f"build.roles: failed to insert '{role_name}': {result[1]}")

        # Print summary
        if roles_config:
            print(f"  Matched {len(roles_config)} role pattern(s)")

    return ok(None)


def concepts(conn, cik: str, concepts_config: dict, verbose: bool = False) -> Result[None, str]:
    """
    Populate concept patterns from ep.toml (idempotent).

    Called as: build.concepts(conn, cik, concepts_config, verbose)

    Args:
        conn: Database connection
        cik: Company CIK
        concepts_config: Concepts section from ep.toml
        verbose: Show detailed output if True

    Returns:
        ok(None) on success, err(str) on failure
    """
    if verbose:
        # Detailed output - show each concept pattern
        for concept_name, concept_spec in concepts_config.items():
            uid = concept_spec["uid"]
            pattern = concept_spec["pattern"]
            note = concept_spec.get("note", "")

            print(f"  Concept pattern:")
            print(f"    Name: {concept_name}")
            print(f"    Pattern: {pattern}")
            if note:
                print(f"    Note: {note}")
            print(f"    UID: {uid}")

            # Try to insert (idempotent - ignore if exists)
            result = db.queries.concept_patterns.insert(conn, cik, concept_name, pattern, uid, note)
            if is_not_ok(result):
                # If already exists, that's fine
                if "already exists" not in result[1]:
                    return err(f"build.concepts: failed to insert '{concept_name}': {result[1]}")
    else:
        # Summary output - just show count
        for concept_name, concept_spec in concepts_config.items():
            uid = concept_spec["uid"]
            pattern = concept_spec["pattern"]
            note = concept_spec.get("note", "")

            # Try to insert (idempotent - ignore if exists)
            result = db.queries.concept_patterns.insert(conn, cik, concept_name, pattern, uid, note)
            if is_not_ok(result):
                # If already exists, that's fine
                if "already exists" not in result[1]:
                    return err(f"build.concepts: failed to insert '{concept_name}': {result[1]}")

        # Print summary
        if concepts_config:
            print(f"  Matched {len(concepts_config)} concept pattern(s)")

    return ok(None)


def groups(conn, cik: str, cfg: dict, groups_to_process: list[str]) -> Result[None, str]:
    """
    Populate groups and link them to roles/concepts from ep.toml (idempotent).

    Called as: build.groups(conn, cik, cfg, groups_to_process)

    Args:
        conn: Database connection
        cik: Company CIK
        cfg: Full ep.toml configuration
        groups_to_process: List of group names to process

    Returns:
        ok(None) on success, err(str) on failure
    """
    groups_config = cfg.get("groups", {})

    for group_name, group_spec in groups_config.items():
        # Skip groups not in the target list
        if group_name not in groups_to_process:
            continue
        # Insert group (idempotent)
        result = db.queries.groups.insert_or_ignore(conn, group_name)
        if is_not_ok(result):
            return err(f"build.groups: failed to insert group '{group_name}': {result[1]}")

        gid = result[1]

        # Determine role (inherit from parent if using 'from')
        role_name = group_spec.get("role")
        if not role_name and "from" in group_spec:
            # Inherit role from parent group
            parent_group_name = group_spec["from"]
            parent_group_spec = groups_config.get(parent_group_name)
            if parent_group_spec:
                role_name = parent_group_spec.get("role")

        # Link role to group
        if role_name:
            # Get role pattern ID
            result = db.queries.role_patterns.get(conn, cik, role_name)
            if is_not_ok(result):
                return err(f"build.groups: failed to get role pattern '{role_name}': {result[1]}")

            role_pattern = result[1]
            if not role_pattern:
                return err(f"build.groups: role pattern '{role_name}' not found for group '{group_name}'")

            pid = role_pattern["pid"]

            # Link gid ↔ pid (idempotent)
            link_data = [{"gid": gid, "pid": pid}]
            result = db.store.insert_or_ignore(conn, "group_role_patterns", link_data)
            if is_not_ok(result):
                return err(f"build.groups: failed to link role '{role_name}' to group '{group_name}': {result[1]}")

        # Link concepts to group
        concept_uids = group_spec.get("concepts", [])
        for uid in concept_uids:
            # Get concept pattern ID by UID
            result = db.queries.concept_patterns.get_by_uid(conn, cik, str(uid))
            if is_not_ok(result):
                return err(f"build.groups: failed to get concept pattern uid={uid}: {result[1]}")

            concept_pattern = result[1]
            if not concept_pattern:
                return err(f"build.groups: concept pattern uid={uid} not found for group '{group_name}'")

            pid = concept_pattern["pid"]

            # Link gid ↔ pid (idempotent)
            result = db.queries.groups.link_concept_pattern(conn, gid, pid)
            if is_not_ok(result):
                return err(f"build.groups: failed to link concept uid={uid} to group '{group_name}': {result[1]}")

    return ok(None)
