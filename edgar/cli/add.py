"""
CLI: add

Links patterns to groups using three modes:
1. Direct ID linking: --uid 1 2 3
2. Direct name linking: --names Cash Inventory
3. Filtered derivation: --from Balance [--uid ...] [--names ...] [--pattern ...] [--exclude ...]

All filters use AND logic when combined.
"""

import re
import sys
import sqlite3

# Local modules
from edgar import config
from edgar import db
from edgar import cache
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """
    Add pattern management commands to argument parser.
    """
    # Main add command with subcommands
    parser_add = subparsers.add_parser("add", help="add patterns to groups")
    add_subparsers = parser_add.add_subparsers(dest='add_cmd', help='add commands')

    # add concept command
    parser_add_concept = add_subparsers.add_parser("concept", help="link concept patterns to group")
    parser_add_concept.add_argument("-g", "--group", metavar="X", required=True, help="target group name")
    parser_add_concept.add_argument("-t", "--ticker", metavar="X", required=True, help="company ticker symbol")

    # Source selection (optional)
    parser_add_concept.add_argument("-f", "--from", metavar="X", dest="source_group", help="source group to derive from")

    # Selection and filter arguments (work independently or with --from)
    parser_add_concept.add_argument("-u", "--uid", metavar="X", nargs="+", type=int, help="select/filter by user IDs")
    parser_add_concept.add_argument("-n", "--names", metavar="X", nargs="+", help="select/filter by concept names")
    parser_add_concept.add_argument("-p", "--pattern", metavar="X", help="filter by concept name regex")
    parser_add_concept.add_argument("-e", "--exclude", metavar="X", help="exclude by concept name regex")
    parser_add_concept.set_defaults(func=run)

    # add role command
    parser_add_role = add_subparsers.add_parser("role", help="link role patterns to group")
    parser_add_role.add_argument("-g", "--group", metavar="X", required=True, help="target group name")
    parser_add_role.add_argument("-t", "--ticker", metavar="X", required=True, help="company ticker symbol")

    # Source selection (optional)
    parser_add_role.add_argument("-f", "--from", metavar="X", dest="source_group", help="source group to derive from")

    # Selection and filter arguments
    parser_add_role.add_argument("-n", "--names", metavar="X", nargs="+", help="select/filter by role names")
    parser_add_role.add_argument("-p", "--pattern", metavar="X", nargs="+", help="filter by role name regex")
    parser_add_role.add_argument("-e", "--exclude", help="exclude by role name regex")
    parser_add_role.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """Route to appropriate add subcommand."""

    if args.add_cmd == 'concept':
        return run_add_concept(cmd, args)
    elif args.add_cmd == 'role':
        return run_add_role(cmd, args)
    else:
        return err(f"cli.add.run: unknown add subcommand: {args.add_cmd}")


def run_add_concept(cmd: Cmd, args) -> Result[None, str]:
    """
    Link concept patterns to a group using one of three modes:
    1. Direct ID: --id 1 2 3 (no --from)
    2. Direct names: --names Cash Inventory (no --from)
    3. Derivation: --from Balance [filters...] (filters optional, AND logic)
    """
    try:
        conn = sqlite3.connect(args.db_path)

        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Get ticker from database
        ticker = args.ticker if args.ticker else (
            args.default_ticker or None
        )
        if not ticker:
            conn.close()
            return err("add concept: ticker required. Use --ticker or set default ticker in ft.toml.")

        result = db.queries.entities.select(conn, [ticker])
        if is_not_ok(result):
            conn.close()
            return result

        entities = result[1]
        if not entities:
            conn.close()
            return err(f"add concept: ticker '{ticker}' not found. Run 'probe filings' first.")

        entity = entities[0]
        cik = entity["cik"]
        company_name = entity["name"]

        # Get target group_id
        result = db.queries.groups.get_id(conn, args.group)
        if is_not_ok(result):
            conn.close()
            return result

        target_group_id = result[1]
        if target_group_id is None:
            conn.close()
            return err(f"add concept: group '{args.group}' not found. Use 'edgar new group {args.group}' first.")

        # Validate at least one selection method
        has_from = args.source_group is not None
        has_id = args.uid is not None
        has_names = args.names is not None
        has_pattern = args.pattern is not None
        has_exclude = args.exclude is not None

        if not has_from and not has_id and not has_names:
            conn.close()
            return err("add concept: must specify --id, --names, or --from")

        # Validate filters only used with --from
        if not has_from and (has_pattern or has_exclude):
            conn.close()
            return err("add concept: --pattern and --exclude can only be used with --from")

        # Determine mode and execute
        if has_from:
            # Mode 3: Filtered derivation
            result = derive_and_link_concepts(
                conn, target_group_id, cik, args.source_group,
                user_ids=args.uid,
                concept_names=args.names if has_names else None,
                name_pattern=args.pattern,
                exclude_pattern=args.exclude
            )
        elif has_id:
            # Mode 1: Direct ID linking
            result = link_concepts_by_uid(conn, target_group_id, cik, args.uid)
        else:
            # Mode 2: Direct name linking
            result = link_concepts_by_names(conn, target_group_id, cik, args.names)

        if is_not_ok(result):
            conn.close()
            return result

        linked_count = result[1]

        # Report success
        print(f"Linked {linked_count} concept pattern(s) to group '{args.group}' for {ticker.upper()} ({company_name})", file=sys.stderr)

        conn.close()
        return ok(None)

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.add.run_add_concept: {e}")


def run_add_role(cmd: Cmd, args) -> Result[None, str]:
    """
    Link role patterns to a group using one of two modes:
    1. Direct names: --names Balance Sheet (no --from)
    2. Derivation: --from Balance [filters...] (filters optional, AND logic)
    """
    try:
        conn = sqlite3.connect(args.db_path)

        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Get ticker from database
        ticker = args.ticker if args.ticker else (
            args.default_ticker or None
        )
        if not ticker:
            conn.close()
            return err("add role: ticker required. Use --ticker or set default ticker in ft.toml.")

        result = db.queries.entities.select(conn, [ticker])
        if is_not_ok(result):
            conn.close()
            return result

        entities = result[1]
        if not entities:
            conn.close()
            return err(f"add role: ticker '{ticker}' not found. Run 'probe filings' first.")

        entity = entities[0]
        cik = entity["cik"]
        company_name = entity["name"]

        # Get target group_id
        result = db.queries.groups.get_id(conn, args.group)
        if is_not_ok(result):
            conn.close()
            return result

        target_group_id = result[1]
        if target_group_id is None:
            conn.close()
            return err(f"add role: group '{args.group}' not found. Use 'edgar new group {args.group}' first.")

        # Validate at least one selection method
        has_from = args.source_group is not None
        has_names = args.names is not None
        has_pattern = args.pattern is not None
        has_exclude = args.exclude is not None

        if not has_from and not has_names:
            conn.close()
            return err("add role: must specify --names or --from")

        # Validate filters only used with --from
        if not has_from and (has_pattern or has_exclude):
            conn.close()
            return err("add role: --pattern and --exclude can only be used with --from")

        # Determine mode and execute
        if has_from:
            # Mode 2: Filtered derivation
            result = derive_and_link_roles(
                conn, target_group_id, cik, args.source_group,
                role_names=args.names if has_names else None,
                pattern=args.pattern,
                exclude_pattern=args.exclude
            )
        else:
            # Mode 1: Direct name linking
            result = link_roles_by_names(conn, target_group_id, cik, args.names)

        if is_not_ok(result):
            conn.close()
            return result

        linked_count = result[1]

        # Report success
        print(f"Linked {linked_count} role pattern(s) to group '{args.group}' for {ticker.upper()} ({company_name})", file=sys.stderr)

        conn.close()
        return ok(None)

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.add.run_add_role: {e}")


# =============================================================================
# MODE 1: DIRECT ID LINKING
# =============================================================================

def link_concepts_by_uid(conn: sqlite3.Connection, group_id: int, cik: str, user_ids: list[int]) -> Result[int, str]:
    """
    Link concept patterns to group by uid.
    """
    patterns = []
    for user_id in user_ids:
        result = db.queries.concept_patterns.get_by_uid(conn, cik, str(user_id))
        if is_not_ok(result):
            return result

        pattern = result[1]
        if pattern is None:
            return err(f"link_concepts_by_uid: no concept pattern with uid={user_id} for CIK {cik}")

        patterns.append(pattern)

    return link_patterns_to_group(conn, group_id, patterns, "group_concept_patterns")


def link_roles_by_names(conn: sqlite3.Connection, group_id: int, cik: str, names: list[str]) -> Result[int, str]:
    """
    Link role patterns to group by name.
    """
    patterns = []
    for name in names:
        result = db.queries.role_patterns.get(conn, cik, name)
        if is_not_ok(result):
            return result

        pattern = result[1]
        if pattern is None:
            return err(f"link_roles_by_names: no role pattern with name='{name}' for CIK {cik}")

        patterns.append(pattern)

    return link_patterns_to_group(conn, group_id, patterns, "group_role_patterns")


# =============================================================================
# MODE 2: DIRECT NAME LINKING
# =============================================================================

def link_concepts_by_names(conn: sqlite3.Connection, group_id: int, cik: str, names: list[str]) -> Result[int, str]:
    """
    Link concept patterns to group by name.
    """
    patterns = []
    for name in names:
        result = db.queries.concept_patterns.get_by_name(conn, cik, name)
        if is_not_ok(result):
            return result

        pattern = result[1]
        if pattern is None:
            return err(f"link_concepts_by_names: no concept pattern with name='{name}' for CIK {cik}")

        patterns.append(pattern)

    return link_patterns_to_group(conn, group_id, patterns, "group_concept_patterns")


# =============================================================================
# MODE 3: FILTERED DERIVATION
# =============================================================================

def derive_and_link_concepts(conn: sqlite3.Connection, target_group_id: int, cik: str,
                             source_group_name: str, user_ids: list[int] = None,
                             concept_names: list[str] = None, name_pattern: str = None,
                             exclude_pattern: str = None) -> Result[int, str]:
    """
    Derive concept patterns from source group and link to target group.
    All filters use AND logic.
    """
    # Get source group ID
    result = db.queries.groups.get_id(conn, source_group_name)
    if is_not_ok(result):
        return result

    source_group_id = result[1]
    if source_group_id is None:
        return err(f"derive_and_link_concepts: source group '{source_group_name}' not found")

    # Get patterns from source group
    result = db.queries.concept_patterns.select_by_group(conn, source_group_id, cik)
    if is_not_ok(result):
        return result

    patterns = result[1]

    # Apply filters with AND logic
    filtered = apply_concept_filters(patterns, user_ids, concept_names, name_pattern, exclude_pattern)

    if not filtered:
        print(f"Warning: No patterns matched filters from source group '{source_group_name}'", file=sys.stderr)
        return ok(0)

    return link_patterns_to_group(conn, target_group_id, filtered, "group_concept_patterns")


def derive_and_link_roles(conn: sqlite3.Connection, target_group_id: int, cik: str,
                          source_group_name: str, role_names: list[str] = None,
                          pattern: str = None, exclude_pattern: str = None) -> Result[int, str]:
    """
    Derive role patterns from source group and link to target group.
    All filters use AND logic.
    """
    # Get source group ID
    result = db.queries.groups.get_id(conn, source_group_name)
    if is_not_ok(result):
        return result

    source_group_id = result[1]
    if source_group_id is None:
        return err(f"derive_and_link_roles: source group '{source_group_name}' not found")

    # Get patterns from source group
    result = db.queries.role_patterns.select_by_group(conn, source_group_id, cik)
    if is_not_ok(result):
        return result

    patterns = result[1]

    # Apply filters with AND logic
    filtered = apply_role_filters(patterns, role_names, pattern, exclude_pattern)

    if not filtered:
        print(f"Warning: No patterns matched filters from source group '{source_group_name}'", file=sys.stderr)
        return ok(0)

    return link_patterns_to_group(conn, target_group_id, filtered, "group_role_patterns")


# =============================================================================
# FILTER HELPERS (AND LOGIC)
# =============================================================================

def apply_concept_filters(patterns: list[dict], 
                          user_ids: list[int] = None,
                          concept_names: list[str] = None, 
                          name_pattern: str = None,
                          exclude_pattern: str = None) -> list[dict]:
    """
    Apply filters to concept patterns using AND logic.
    All specified filters must match for a pattern to be included.
    """
    filtered = []
    for pattern in patterns:
        # Filter by user_ids (AND)
        if user_ids is not None:
            pattern_user_id = pattern.get("uid")
            if pattern_user_id not in user_ids:
                continue

        # Filter by concept_names (AND)
        if concept_names is not None:
            if pattern["name"] not in concept_names:
                continue

        # Filter by name_pattern regex (AND)
        if name_pattern is not None:
            if not re.search(name_pattern, pattern["name"]):
                continue

        # Exclude by exclude_pattern regex (AND)
        if exclude_pattern is not None:
            if re.search(exclude_pattern, pattern["name"]):
                continue

        filtered.append(pattern)

    return filtered


def apply_role_filters(patterns: list[dict],
                       role_names: list[str] = None,
                       pattern: str = None,
                       exclude_pattern: str = None) -> list[dict]:
    """
    Apply filters to role patterns using AND logic.
    All specified filters must match for a pattern to be included.
    """
    filtered = []
    for p in patterns:
        # Filter by role_names (AND)
        if role_names is not None:
            if p["name"] not in role_names:
                continue

        # Filter by pattern regex (AND) - matches against role pattern name
        if pattern is not None:
            if not re.search(pattern, p["name"]):
                continue

        # Exclude by exclude_pattern regex (AND) - matches against role pattern name
        if exclude_pattern is not None:
            if re.search(exclude_pattern, p["name"]):
                continue

        filtered.append(p)

    return filtered


# =============================================================================
# COMMON HELPERS
# =============================================================================

def link_patterns_to_group(conn: sqlite3.Connection, 
                           target_group_id: int, 
                           patterns: list[dict], 
                           link_table: str) -> Result[int, str]:
    """
    Link patterns to target group.
    """
    count = 0
    for pattern in patterns:
        if link_table == "group_concept_patterns":
            result = db.queries.groups.link_concept_pattern(conn, target_group_id, pattern["pid"])
        else:  # group_role_patterns
            link_data = [{"gid": target_group_id, "pid": pattern["pid"]}]
            result = db.store.insert_or_ignore(conn, link_table, link_data)

        if is_not_ok(result):
            return result
        count += 1

    return ok(count)
