"""
CLI: new

Creates patterns and groups. Simple entity creation only - no derivation.
Use 'add' command to link patterns to groups.
"""
import re
import sys
import sqlite3

# Local modules
from edgar import db
from edgar import db
from edgar import cache
from edgar import cli
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """Add new command with subcommands."""

    parser_new = subparsers.add_parser("new", help="create patterns and groups")
    new_subparsers = parser_new.add_subparsers(dest='new_cmd', help='new commands')

    # new concept
    parser_concept = new_subparsers.add_parser("concept", help="create concept pattern")
    parser_concept.add_argument("-t", "--ticker", metavar="X", required=True, help="company ticker symbol")
    parser_concept.add_argument("-n", "--name", metavar="X", required=True, help="concept name")
    parser_concept.add_argument("-p", "--pattern", metavar="X", required=True, help="regex pattern")
    parser_concept.add_argument("-u", "--uid", type=int, help="optional user-assigned ID")
    parser_concept.set_defaults(func=run)

    # new role
    parser_role = new_subparsers.add_parser("role", help="create role pattern")
    parser_role.add_argument("-t", "--ticker", metavar="X", required=True, help="company ticker symbol")
    parser_role.add_argument("-p", "--pattern", metavar="X", required=True, help="regex pattern")
    parser_role.add_argument("-u", "--uid", type=int, help="optional user-assigned ID")
    parser_role.set_defaults(func=run)

    # new group
    parser_group = new_subparsers.add_parser("group", help="create group, optionally derived from another")
    parser_group.add_argument("group_name", metavar="X", help="group name")
    parser_group.add_argument("-t", "--ticker", help="company ticker symbol (required with --from)")

    # Derivation source
    parser_group.add_argument("--from", dest="source_group", help="source group to derive from")

    # Concept filters (default, common case)
    parser_group.add_argument("--uid", "-u", nargs="+", type=int, help="filter concepts by user IDs")
    parser_group.add_argument("--names", nargs="+", help="filter concepts by names")
    parser_group.add_argument("--pattern", help="filter concepts by name regex")
    parser_group.add_argument("--exclude", help="exclude concepts by name regex")

    # Role filters (explicit, edge case)
    parser_group.add_argument("--role-uid", nargs="+", type=int, dest="role_uid", help="filter roles by user IDs")
    parser_group.add_argument("--role-pattern", dest="role_pattern", help="filter roles by pattern regex")
    parser_group.add_argument("--role-exclude", dest="role_exclude", help="exclude roles by pattern regex")

    parser_group.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[None, str]:
    """
    Create patterns or groups.

    Returns:
        ok(None) - Normal completion
        err(str) - Error occurred
    """

    if args.new_cmd == 'concept':
        return run_new_concept(cmd, args)
    elif args.new_cmd == 'role':
        return run_new_role(cmd, args)
    elif args.new_cmd == 'group':
        return run_new_group(cmd, args)
    else:
        return err(f"cli.new.run: unknown subcommand: {args.new_cmd}")


def run_new_concept(cmd: Cmd, args) -> Result[None, str]:
    """
    Create a new concept pattern.
    """
    # Validate regex
    try:
        re.compile(args.pattern)
    except re.error as e:
        return err(f"new concept: invalid regex pattern: {e}")

    try:
        conn = sqlite3.connect(args.db)

        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Get ticker from database
        result = db.queries.entity_select(conn, [args.ticker])
        if is_not_ok(result):
            conn.close()
            return result

        entities = result[1]
        if not entities:
            conn.close()
            return err(f"new concept: ticker '{args.ticker}' not found. Run 'probe filings' first.")

        entity = entities[0]
        cik = entity["cik"]
        company_name = entity["name"]

        # Insert concept pattern with optional uid
        result = db.queries.concept_pattern_insert_with_uid(
            conn, cik, args.name, args.pattern, args.uid
        )
        if is_not_ok(result):
            conn.close()
            return result

        pattern_id = result[1]

        # Report success
        print(f"Created concept pattern '{args.name}' for {args.ticker.upper()} ({company_name})", file=sys.stderr)
        print(f"Pattern ID: {pattern_id}, CIK: {cik}", file=sys.stderr)
        if args.uid is not None:
            print(f"User ID: {args.uid}", file=sys.stderr)
        print(f"Pattern: {args.pattern}", file=sys.stderr)

        conn.close()
        return ok(None)

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.new.run_new_concept: {e}")


def run_new_role(cmd: Cmd, args) -> Result[None, str]:
    """
    Create a new role pattern.
    """
    # Validate regex
    try:
        re.compile(args.pattern)
    except re.error as e:
        return err(f"new role: invalid regex pattern: {e}")

    try:
        conn = sqlite3.connect(args.db)

        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Get ticker from database
        result = db.queries.entity_select(conn, [args.ticker])
        if is_not_ok(result):
            conn.close()
            return result

        entities = result[1]
        if not entities:
            conn.close()
            return err(f"new role: ticker '{args.ticker}' not found. Run 'probe filings' first.")

        entity = entities[0]
        cik = entity["cik"]
        company_name = entity["name"]

        # Insert role pattern with optional uid
        result = db.queries.role_pattern_insert_with_uid(
            conn, cik, args.pattern, args.uid
        )
        if is_not_ok(result):
            conn.close()
            return result

        pattern_id = result[1]

        # Report success
        print(f"Created role pattern for {args.ticker.upper()} ({company_name})", file=sys.stderr)
        print(f"Pattern ID: {pattern_id}, CIK: {cik}", file=sys.stderr)
        if args.uid is not None:
            print(f"User ID: {args.uid}", file=sys.stderr)
        print(f"Pattern: {args.pattern}", file=sys.stderr)

        conn.close()
        return ok(None)

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.new.run_new_role: {e}")


def run_new_group(cmd: Cmd, args) -> Result[None, str]:
    """
    Create a group, optionally derived from another group.
    """
    try:
        conn = sqlite3.connect(args.db)

        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Check if derivation is requested
        has_from = args.source_group is not None
        has_concept_filters = any([
            args.uid is not None,
            args.names is not None,
            args.pattern is not None,
            args.exclude is not None
        ])
        has_role_filters = any([
            args.role_uid is not None,
            args.role_pattern is not None,
            args.role_exclude is not None
        ])

        # Validate derivation requirements
        if (has_concept_filters or has_role_filters) and not has_from:
            conn.close()
            return err("new group: filters require --from")

        if has_from and not args.ticker:
            conn.close()
            return err("new group: --from requires --ticker")

        # Create the group (always happens first)
        result = db.queries.group_insert_or_ignore(conn, args.group_name)
        if is_not_ok(result):
            conn.close()
            return result

        group_id = result[1]
        print(f"Created group '{args.group_name}'", file=sys.stderr)
        print(f"Group ID: {group_id}", file=sys.stderr)

        # If no derivation, we're done
        if not has_from:
            print(f"Use 'edgar add concept' and 'edgar add role' to link patterns.", file=sys.stderr)
            conn.close()
            return ok(None)

        # Get ticker from database for derivation
        result = db.queries.entity_select(conn, [args.ticker])
        if is_not_ok(result):
            conn.close()
            return result

        entities = result[1]
        if not entities:
            conn.close()
            return err(f"new group: ticker '{args.ticker}' not found. Run 'probe filings' first.")

        entity = entities[0]
        cik = entity["cik"]
        company_name = entity["name"]

        # Derive and link roles
        roles_linked = 0
        if has_role_filters:
            # Edge case: Filter roles explicitly
            result = cli.add.derive_and_link_roles(
                conn, group_id, cik, args.source_group,
                user_ids=args.role_uid,
                pattern=args.role_pattern,
                exclude_pattern=args.role_exclude
            )
            if is_not_ok(result):
                conn.close()
                return result
            roles_linked = result[1]
        else:
            # Default: Copy all roles from source group
            result = cli.add.derive_and_link_roles(
                conn, group_id, cik, args.source_group,
                user_ids=None,
                pattern=None,
                exclude_pattern=None
            )
            if is_not_ok(result):
                conn.close()
                return result
            roles_linked = result[1]

        # Derive and link concepts
        concepts_linked = 0
        if has_concept_filters:
            # Filter concepts
            result = cli.add.derive_and_link_concepts(
                conn, group_id, cik, args.source_group,
                user_ids=args.uid,
                concept_names=args.names,
                name_pattern=args.pattern,
                exclude_pattern=args.exclude
            )
            if is_not_ok(result):
                conn.close()
                return result
            concepts_linked = result[1]
        else:
            # Copy all concepts from source group
            result = cli.add.derive_and_link_concepts(
                conn, group_id, cik, args.source_group,
                user_ids=None,
                concept_names=None,
                name_pattern=None,
                exclude_pattern=None
            )
            if is_not_ok(result):
                conn.close()
                return result
            concepts_linked = result[1]

        # Report success
        print(f"Derived from group '{args.source_group}' for {args.ticker.upper()} ({company_name})", file=sys.stderr)
        print(f"Linked {roles_linked} role pattern(s)", file=sys.stderr)
        print(f"Linked {concepts_linked} concept pattern(s)", file=sys.stderr)

        conn.close()
        return ok(None)

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.new.run_new_group: {e}")
