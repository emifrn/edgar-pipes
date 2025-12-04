"""
CLI: build

Build database from ep.toml configuration. Validates schema and extracts facts.
"""
import sys
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

# Local modules
from edgar import config
from edgar import db
from edgar import cache
from edgar import xbrl
from edgar.cli.shared import Cmd, progress_bar
from edgar.cli.update import _update_filing
from edgar.result import Result, ok, err, is_not_ok, is_ok


# =============================================================================
# Context
# =============================================================================

@dataclass
class BuildContext:
    """Shared context for build operations."""
    conn: sqlite3.Connection
    cik: str
    user_agent: str
    cfg: dict
    verbose: bool = False


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


def resolve_deps(groups_config: dict, requested_groups: list[str]) -> set[str]:
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
    groups_with_deps = resolve_deps(groups_config, requested_groups)

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
        with progress_bar("Probing roles") as progress:
            task = progress.add_task("", total=len(all_filings), current="")

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

    # Step 4: Build schema for all groups (roles, concepts, group linkages)
    print(f"Building schema for {len(groups_to_process)} group(s)...")
    total_roles = 0
    total_concepts = 0
    for i, group_name in enumerate(groups_to_process, 1):
        result = schema(conn, cik, cfg, group_name, i, len(groups_to_process), verbose)
        if is_not_ok(result):
            print(f"ERROR: Failed to build schema for group '{group_name}': {result[1]}")
            conn.close()
            return result
        total_roles += result[1].get("roles", 0)
        total_concepts += result[1].get("concepts", 0)

    if not verbose:
        print(f"  Matched {total_roles} role pattern(s), {total_concepts} concept pattern(s)")
    print()

    # Step 5: Process filings in chronological order (outer loop)
    # For each filing, extract facts for ALL groups (inner loop)
    # This ensures: 1) Model loaded once per filing, 2) Q1 before Q2 for all groups
    result = extract(conn, cik, user_agent, cfg, groups_to_process, all_filings, verbose)
    if is_not_ok(result):
        conn.close()
        return result

    conn.commit()
    conn.close()

    print("\n✓ Build complete")
    return ok(None)


def schema(conn, cik: str, cfg: dict, group_name: str,
           group_index: int = 1, total_groups: int = 1,
           verbose: bool = False) -> Result[dict[str, int], str]:
    """
    Build schema for a single group: roles, concepts, and group linkages.
    Does NOT extract facts - that's done separately in extract.

    Returns:
        ok({"roles": N, "concepts": M}) on success, err(str) on failure
    """
    groups_config = cfg.get("groups", {})
    group_spec = groups_config.get(group_name, {})
    is_derived = "from" in group_spec
    role_count = 0
    concept_count = 0

    if verbose:
        parent_info = f" (derived from {group_spec['from']})" if is_derived else ""
        print(f"  [{group_index:2d}/{total_groups}] {group_name}{parent_info}")

    # Get role name (inherit from parent if needed)
    role_name = group_spec.get("role")
    if not role_name and is_derived:
        parent_spec = groups_config.get(group_spec["from"], {})
        role_name = parent_spec.get("role")

    # Insert role pattern
    if role_name:
        roles_to_insert = {role_name: cfg.get("roles", {}).get(role_name, {})}
        result = roles(conn, cik, roles_to_insert, verbose)
        if is_not_ok(result):
            return err(f"schema: failed to insert role '{role_name}': {result[1]}")
        role_count = result[1]

    # Insert concept patterns for this group
    concept_uids = group_spec.get("concepts", [])
    concepts_config = cfg.get("concepts", {})
    concepts_to_insert = {
        name: defn for name, defn in concepts_config.items()
        if defn.get("uid") in concept_uids
    }

    result = concepts(conn, cik, concepts_to_insert, verbose)
    if is_not_ok(result):
        return err(f"schema: failed to insert concepts: {result[1]}")
    concept_count = result[1]

    # Insert group and link to role/concepts
    result = groups(conn, cik, cfg, [group_name])
    if is_not_ok(result):
        return err(f"schema: failed to insert group: {result[1]}")

    return ok({"roles": role_count, "concepts": concept_count})


def extract(conn, cik: str, user_agent: str, cfg: dict, groups_to_process: list[str],
                       all_filings: list, verbose: bool = False) -> Result[None, str]:
    """
    Process all filings in chronological order, extracting facts for ALL groups per filing.
    This ensures: 1) Arelle model loaded once per filing, 2) Q1 before Q2 for all groups.

    Args:
        conn: Database connection
        cik: Company CIK
        user_agent: SEC API user agent
        cfg: Full ep.toml configuration
        groups_to_process: List of group names to process
        all_filings: List of filings (already in chronological ASC order)
        verbose: Show detailed output if True

    Returns:
        ok(None) on success, err(str) on failure
    """
    groups_config = cfg.get("groups", {})

    # Build map of group -> pattern_ids for processed checking
    group_pattern_map = {}
    for group_name in groups_to_process:
        # Skip derived groups - they share facts with parent
        if "from" in groups_config.get(group_name, {}):
            continue

        concept_uids = groups_config[group_name].get("concepts", [])
        pattern_ids = []
        for uid in concept_uids:
            result = db.queries.concept_patterns.get_by_uid(conn, cik, uid)
            if is_ok(result) and result[1]:
                pattern_ids.append(result[1]["pid"])
        group_pattern_map[group_name] = pattern_ids

    stats_by_group = {g: {"candidates": 0, "chosen": 0, "inserted": 0} for g in group_pattern_map}

    if verbose:
        print(f"Processing {len(all_filings)} filing(s) for {len(group_pattern_map)} main group(s)...\n")

        for idx, filing in enumerate(all_filings, 1):
            result = extract_one(
                conn, cik, user_agent, cfg, filing, group_pattern_map,
                stats_by_group, idx, len(all_filings), verbose
            )
            if is_not_ok(result):
                print(f"  [{idx}/{len(all_filings)}] {filing['access_no']}: ERROR: {result[1]}")

        # Print summary
        for group_name, stats in stats_by_group.items():
            if stats["inserted"] > 0:
                print(f"  {group_name}: {stats['inserted']} facts inserted")
        print()
    else:
        # Progress bar mode
        with progress_bar("Processing") as progress:
            task = progress.add_task("", total=len(all_filings), current="")

            for filing in all_filings:
                access_no = filing["access_no"]
                filing_date = filing.get("filing_date", "?")

                result = extract_one(
                    conn, cik, user_agent, cfg, filing, group_pattern_map,
                    stats_by_group, 0, 0, False
                )

                if is_ok(result):
                    total_inserted = result[1]
                    progress.update(task, advance=1,
                                  current=f"{access_no} {filing_date}: {total_inserted} facts")
                else:
                    progress.update(task, advance=1,
                                  current=f"{access_no} {filing_date}: ERROR")

        # Print summary
        total_inserted = sum(s["inserted"] for s in stats_by_group.values())
        print(f"  ✓ Processed {len(all_filings)} filing(s), inserted {total_inserted} facts\n")

    return ok(None)


def extract_one(conn, cik: str, user_agent: str, cfg: dict, filing: dict,
                                  group_pattern_map: dict, stats_by_group: dict,
                                  idx: int, total: int, verbose: bool) -> Result[int, str]:
    """
    Process a single filing for all groups. Loads Arelle model ONCE.

    Returns:
        ok(total_inserted) on success, err(str) on failure
    """
    access_no = filing["access_no"]
    filing_date = filing.get("filing_date", "?")

    # Get role mappings for all groups for this filing
    result = db.queries.role_patterns.match_groups_for_filing(conn, cik, access_no)
    if is_not_ok(result):
        return err(f"failed to match roles: {result[1]}")

    role_map = result[1]
    if not role_map:
        if verbose:
            print(f"  [{idx}/{total}] {access_no} {filing_date}: SKIP (no matching roles)")
        return ok(0)

    # Load Arelle model ONCE for this filing
    result = db.queries.filings.get_xbrl_url(conn, access_no)
    if is_not_ok(result):
        return err(f"failed to get XBRL URL: {result[1]}")

    url = result[1]
    if not url:
        return err("no XBRL URL cached")

    result = xbrl.arelle.load_model(url)
    if is_not_ok(result):
        return err(f"failed to load model: {result[1]}")

    model = result[1]

    # Extract DEI once
    dei = xbrl.arelle.extract_dei(model, access_no)
    result = db.queries.filings.insert_dei(conn, dei)
    if is_not_ok(result):
        return err(f"failed to insert DEI: {result[1]}")

    fiscal_period = dei.get("fiscal_period", "?")
    total_inserted = 0

    # Process each group that has matching roles
    for group_name, pattern_ids in group_pattern_map.items():
        # Check if already processed for this group
        result = db.queries.filing_patterns_processed.is_fully_processed(conn, access_no, pattern_ids)
        if is_ok(result) and result[1]:
            continue  # Already processed for this group

        # Check if this group has matching roles
        if group_name not in role_map:
            # Mark as processed even if no roles (fact doesn't exist in this filing)
            for pid in pattern_ids:
                db.queries.filing_patterns_processed.insert(conn, access_no, pid)
            continue

        # Filter role_map to just this group
        role_map_filtered = {group_name: role_map[group_name]}

        # Probe concepts for this group's roles
        for role_tail in role_map_filtered[group_name]:
            cache.resolve_concepts(conn, user_agent, cik, access_no, role_tail)

        # Extract facts for this group (passing already-loaded model and DEI)
        result = _update_filing(conn, cik, access_no, role_map_filtered, model=model, dei=dei)

        if is_ok(result):
            stats = result[1]
            stats_by_group[group_name]["candidates"] += stats["candidates"]
            stats_by_group[group_name]["chosen"] += stats["chosen"]
            stats_by_group[group_name]["inserted"] += stats["inserted"]
            total_inserted += stats["inserted"]

            if verbose:
                print(f"  [{idx}/{total}] {access_no} {filing_date} {fiscal_period} [{group_name}]: "
                      f"cand={stats['candidates']} chosen={stats['chosen']} inserted={stats['inserted']}")
        else:
            if verbose:
                print(f"  [{idx}/{total}] {access_no} {filing_date} [{group_name}]: ERROR: {result[1]}")

        # Mark as processed for this group (even if extraction failed)
        for pid in pattern_ids:
            db.queries.filing_patterns_processed.insert(conn, access_no, pid)

    return ok(total_inserted)


def roles(conn, cik: str, roles_config: dict, verbose: bool = False) -> Result[int, str]:
    """Populate role patterns from ep.toml (idempotent). Returns count inserted."""
    for role_name, role_spec in roles_config.items():
        pattern = role_spec["pattern"]
        note = role_spec.get("note", "")

        if verbose:
            print(f"  Role: {role_name} → {pattern}")

        result = db.queries.role_patterns.insert(conn, cik, role_name, pattern, note)
        if is_not_ok(result) and "already exists" not in result[1]:
            return err(f"roles: failed to insert '{role_name}': {result[1]}")

    return ok(len(roles_config))


def concepts(conn, cik: str, concepts_config: dict, verbose: bool = False) -> Result[int, str]:
    """Populate concept patterns from ep.toml (idempotent). Returns count inserted."""
    for concept_name, concept_spec in concepts_config.items():
        uid = concept_spec["uid"]
        pattern = concept_spec["pattern"]
        note = concept_spec.get("note", "")

        if verbose:
            print(f"  Concept: {concept_name} (uid={uid}) → {pattern}")

        result = db.queries.concept_patterns.insert(conn, cik, concept_name, pattern, uid, note)
        if is_not_ok(result) and "already exists" not in result[1]:
            return err(f"concepts: failed to insert '{concept_name}': {result[1]}")

    return ok(len(concepts_config))


def groups(conn, cik: str, cfg: dict, groups_to_process: list[str]) -> Result[None, str]:
    """Populate groups and link to roles/concepts from ep.toml (idempotent)."""
    groups_config = cfg.get("groups", {})

    for group_name, group_spec in groups_config.items():
        if group_name not in groups_to_process:
            continue

        result = db.queries.groups.insert_or_ignore(conn, group_name)
        if is_not_ok(result):
            return err(f"groups: failed to insert '{group_name}': {result[1]}")

        gid = result[1]

        # Determine role (inherit from parent if using 'from')
        role_name = group_spec.get("role")
        if not role_name and "from" in group_spec:
            parent_spec = groups_config.get(group_spec["from"])
            if parent_spec:
                role_name = parent_spec.get("role")

        # Link role to group
        if role_name:
            result = db.queries.role_patterns.get(conn, cik, role_name)
            if is_not_ok(result):
                return err(f"groups: role pattern '{role_name}' not found: {result[1]}")

            role_pattern = result[1]
            if not role_pattern:
                return err(f"groups: role pattern '{role_name}' not found for '{group_name}'")

            link_data = [{"gid": gid, "pid": role_pattern["pid"]}]
            result = db.store.insert_or_ignore(conn, "group_role_patterns", link_data)
            if is_not_ok(result):
                return err(f"groups: failed to link role '{role_name}' to '{group_name}': {result[1]}")

        # Link concepts to group
        for uid in group_spec.get("concepts", []):
            result = db.queries.concept_patterns.get_by_uid(conn, cik, str(uid))
            if is_not_ok(result):
                return err(f"groups: concept uid={uid} not found: {result[1]}")

            concept_pattern = result[1]
            if not concept_pattern:
                return err(f"groups: concept uid={uid} not found for '{group_name}'")

            result = db.queries.groups.link_concept_pattern(conn, gid, concept_pattern["pid"])
            if is_not_ok(result):
                return err(f"groups: failed to link concept uid={uid} to '{group_name}': {result[1]}")

    return ok(None)
