"""
CLI: modify

Modify groups and patterns with preview/execute workflow.
Supports both standalone (--uid for patterns) and pipeline modes.
"""

import re
import sys
import sqlite3

# Local modules
from edgar import config
from edgar import db
from edgar import config
from edgar import db
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """Add modify command with subcommands."""
    
    parser_modify = subparsers.add_parser("modify", help="modify groups and patterns")
    modify_subparsers = parser_modify.add_subparsers(dest='modify_cmd', help='modify commands')
    
    # modify group
    parser_group = modify_subparsers.add_parser("group", help="modify group name or remove patterns from group")
    parser_group.add_argument("group_name", nargs="?", help="name of group to modify (optional for pipeline mode)")

    # Mode selection: rename or remove
    mode_group = parser_group.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--rename", nargs=2, metavar=("OLD", "NEW"), help="rename group from OLD to NEW")
    mode_group.add_argument("--remove-concept", action="store_true", help="remove concept patterns from group")
    mode_group.add_argument("--remove-role", action="store_true", help="remove role patterns from group")

    # Pattern selection (for remove modes)
    parser_group.add_argument("-u", "--uid", nargs="+", type=int, help="concept pattern user IDs to remove")
    parser_group.add_argument("-n", "--names", nargs="+", help="pattern names to remove")
    parser_group.add_argument("-t", "--ticker", help="ticker (required when using -u or -n)")

    parser_group.add_argument("-y", "--yes", action="store_true", help="execute modification (default: preview)")
    parser_group.set_defaults(func=run)
    
    # modify role
    parser_role = modify_subparsers.add_parser("role", help="modify role pattern regex")
    parser_role.add_argument("-n", "--name", help="pattern name to select pattern (for standalone mode)")
    parser_role.add_argument("-t", "--ticker", help="ticker to narrow down pattern selection")
    parser_role.add_argument("--pattern", help="new regex pattern")
    parser_role.add_argument("--new-name", dest="new_name", help="new pattern name")
    parser_role.add_argument("--note", help="new or updated note describing the pattern rationale")
    parser_role.add_argument("-y", "--yes", action="store_true", help="execute modification (default: preview)")
    parser_role.set_defaults(func=run)

    # modify concept
    parser_concept = modify_subparsers.add_parser("concept", help="modify concept name and/or pattern")
    parser_concept.add_argument("-u", "--uid", type=int, help="user ID to select pattern (for standalone mode)")
    parser_concept.add_argument("-t", "--ticker", help="ticker to narrow down pattern selection")
    parser_concept.add_argument("-n", "--name", help="new concept name")
    parser_concept.add_argument("--pattern", help="new regex pattern")
    parser_concept.add_argument("--new-uid", type=int, dest="new_uid", help="new user-assigned ID")
    parser_concept.add_argument("--note", help="new or updated note describing the pattern rationale")
    parser_concept.add_argument("-y", "--yes", action="store_true", help="execute modification (default: preview)")
    parser_concept.set_defaults(func=run)


def run(cmd: Cmd, args) -> Result[Cmd | None, str]:
    """Route to appropriate modify subcommand."""
    
    if args.modify_cmd == 'group':
        return run_modify_group(cmd, args)
    elif args.modify_cmd == 'role':
        return run_modify_role(cmd, args)
    elif args.modify_cmd == 'concept':
        return run_modify_concept(cmd, args)
    else:
        return err(f"cli.modify.run: unknown modify subcommand: {args.modify_cmd}")


def run_modify_group(cmd: Cmd, args) -> Result[Cmd | None, str]:
    """Modify group names or remove patterns with preview/execute workflow."""

    try:
        conn = sqlite3.connect(args.db_path)

        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result

        # Determine if rename or remove operation
        is_remove = args.remove_concept or args.remove_role

        if is_remove:
            # Remove mode: patterns from group
            return run_modify_group_remove(conn, args)
        else:
            # Rename mode: group name (existing behavior)
            # Collect groups to modify
            if args.group_name:
                # Standalone mode: lookup group by name
                result = db.queries.groups.get_id(conn, args.group_name)
                if is_not_ok(result):
                    conn.close()
                    return result
                group_id = result[1]
                if group_id is None:
                    conn.close()
                    return err(f"modify group: group '{args.group_name}' not found")
                result = db.queries.groups.get(conn, group_id)
                if is_not_ok(result):
                    conn.close()
                    return result
                groups = [result[1]]
            elif cmd["data"]:
                # Pipeline mode: validate data type
                if cmd["name"] != "groups":
                    conn.close()
                    return err(f"modify group: expected group data, got '{cmd['name']}'")
                groups = cmd["data"]
            else:
                conn.close()
                return err("modify group: no input. Use group_name or pipe group data")

            # Preview or execute
            old_name, new_name = args.rename
            if args.yes:
                result = _execute_modify_groups(conn, groups, new_name)
            else:
                result = _preview_modify_groups(groups, new_name)

            conn.close()
            return result

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.modify.run_modify_group: {e}")


def run_modify_group_remove(conn: sqlite3.Connection, args) -> Result[Cmd | None, str]:
    """Remove patterns from a group with preview/execute workflow."""

    try:
        # Get group by name
        result = db.queries.groups.get_id(conn, args.group_name)
        if is_not_ok(result):
            conn.close()
            return result

        group_id = result[1]
        if group_id is None:
            conn.close()
            return err(f"modify group: group '{args.group_name}' not found")

        # Determine pattern type
        if args.remove_concept:
            return _remove_concepts_from_group(conn, args, group_id)
        else:  # args.remove_role
            return _remove_roles_from_group(conn, args, group_id)

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.modify.run_modify_group_remove: {e}")


def _remove_concepts_from_group(conn: sqlite3.Connection, args, group_id: int) -> Result[Cmd | None, str]:
    """Remove concept patterns from group."""

    try:
        # Validate ticker is provided if using uid/names
        if (args.uid or args.names) and not args.ticker:
            conn.close()
            return err("modify group --remove-concept: --ticker is required when using -u or -n")

        # Get patterns to remove
        patterns = []

        if args.uid:
            # Fetch by uid
            result = db.queries.entities.get(conn, ticker=args.ticker)
            if is_not_ok(result):
                conn.close()
                return result
            entity = result[1]
            if not entity:
                conn.close()
                return err(f"modify group: ticker '{args.ticker}' not found")
            cik = entity["cik"]

            for uid in args.uid:
                result = db.queries.concept_patterns.get_by_uid(conn, cik, str(uid))
                if is_not_ok(result):
                    conn.close()
                    return result
                pattern = result[1]
                if not pattern:
                    conn.close()
                    return err(f"modify group: concept pattern with uid={uid} for {args.ticker} not found")
                patterns.append(pattern)

        elif args.names:
            # Fetch by name
            result = db.queries.entities.get(conn, ticker=args.ticker)
            if is_not_ok(result):
                conn.close()
                return result
            entity = result[1]
            if not entity:
                conn.close()
                return err(f"modify group: ticker '{args.ticker}' not found")
            cik = entity["cik"]

            for name in args.names:
                result = db.queries.concept_patterns.get_by_name(conn, cik, name)
                if is_not_ok(result):
                    conn.close()
                    return result
                pattern = result[1]
                if not pattern:
                    conn.close()
                    return err(f"modify group: concept pattern '{name}' for {args.ticker} not found")
                patterns.append(pattern)

        else:
            conn.close()
            return err("modify group --remove-concept: must provide -u (uid) or -n (names)")

        # Preview or execute
        if args.yes:
            result = _execute_remove_concepts(conn, group_id, args.group_name, patterns)
        else:
            result = _preview_remove_concepts(group_id, args.group_name, patterns)

        conn.close()
        return result

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.modify._remove_concepts_from_group: {e}")


def _remove_roles_from_group(conn: sqlite3.Connection, args, group_id: int) -> Result[Cmd | None, str]:
    """Remove role patterns from group."""

    try:
        # Validate ticker is provided if using names
        if args.names and not args.ticker:
            conn.close()
            return err("modify group --remove-role: --ticker is required when using -n")

        # Get patterns to remove
        patterns = []

        if args.names:
            # Fetch by name
            result = db.queries.entities.get(conn, ticker=args.ticker)
            if is_not_ok(result):
                conn.close()
                return result
            entity = result[1]
            if not entity:
                conn.close()
                return err(f"modify group: ticker '{args.ticker}' not found")
            cik = entity["cik"]

            for name in args.names:
                result = db.queries.role_patterns.get(conn, cik, name)
                if is_not_ok(result):
                    conn.close()
                    return result
                pattern = result[1]
                if not pattern:
                    conn.close()
                    return err(f"modify group: role pattern '{name}' for {args.ticker} not found")
                patterns.append(pattern)

        else:
            conn.close()
            return err("modify group --remove-role: must provide -n (names)")

        # Preview or execute
        if args.yes:
            result = _execute_remove_roles(conn, group_id, args.group_name, patterns)
        else:
            result = _preview_remove_roles(group_id, args.group_name, patterns)

        conn.close()
        return result

    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.modify._remove_roles_from_group: {e}")


def run_modify_role(cmd: Cmd, args) -> Result[Cmd | None, str]:
    """Modify role pattern regexes and/or name with preview/execute workflow."""

    # Validate at least one modification field provided
    if not args.pattern and args.new_name is None and not args.note:
        return err("modify role: must provide --pattern, --new-name, --note, or combination")

    # Validate regex if provided
    if args.pattern:
        try:
            re.compile(args.pattern)
        except re.error as e:
            return err(f"modify role: invalid regex pattern: {e}")
    
    try:
        conn = sqlite3.connect(args.db_path)
        
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result
        
        # Collect patterns to modify
        if args.name:
            # Standalone mode: fetch pattern by name
            cik = None
            if args.ticker:
                result = db.queries.entities.get(conn, ticker=args.ticker)
                if is_not_ok(result):
                    conn.close()
                    return result
                entity = result[1]
                if not entity:
                    conn.close()
                    return err(f"modify role: ticker '{args.ticker}' not found")
                cik = entity["cik"]

            result = db.queries.role_patterns.get_with_entity(conn, cik, args.name)
            if is_not_ok(result):
                conn.close()
                return result
            pattern = result[1]
            if not pattern:
                conn.close()
                ticker_msg = f" for {args.ticker}" if args.ticker else ""
                return err(f"modify role: pattern with name '{args.name}'{ticker_msg} not found")
            patterns = [pattern]
        elif cmd["data"]:
            # Pipeline mode: validate and filter to role patterns
            if cmd["name"] != "patterns":
                conn.close()
                return err(f"modify role: expected pattern data, got '{cmd['name']}'")
            patterns = [p for p in cmd["data"] if p.get("type") == "role"]
            if not patterns:
                conn.close()
                return err("modify role: no role patterns in piped data")
        else:
            conn.close()
            return err("modify role: no input. Use --name (with optional --ticker) or pipe pattern data")

        # Preview or execute
        if args.yes:
            result = _execute_modify_roles(conn, patterns, args.pattern, args.new_name, args.note)
        else:
            result = _preview_modify_roles(patterns, args.pattern, args.new_name, args.note)
        
        conn.close()
        return result
        
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.modify.run_modify_role: {e}")


def run_modify_concept(cmd: Cmd, args) -> Result[Cmd | None, str]:
    """Modify concept names, patterns, and/or user_id with preview/execute workflow."""

    # Validate at least one modification field provided
    if not args.name and not args.pattern and args.new_uid is None and not args.note:
        return err("modify concept: must provide --name, --pattern, --new-uid, --note, or combination")
    
    # Validate regex if provided
    if args.pattern:
        try:
            re.compile(args.pattern)
        except re.error as e:
            return err(f"modify concept: invalid regex pattern: {e}")
    
    try:
        conn = sqlite3.connect(args.db_path)
        
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result
        
        # Collect patterns to modify
        if args.uid:
            # Standalone mode: fetch pattern by user ID
            cik = None
            if args.ticker:
                result = db.queries.entities.get(conn, ticker=args.ticker)
                if is_not_ok(result):
                    conn.close()
                    return result
                entity = result[1]
                if not entity:
                    conn.close()
                    return err(f"modify concept: ticker '{args.ticker}' not found")
                cik = entity["cik"]

            result = db.queries.concept_patterns.get_with_entity(conn, cik, str(args.uid))
            if is_not_ok(result):
                conn.close()
                return result
            pattern = result[1]
            if not pattern:
                conn.close()
                ticker_msg = f" for {args.ticker}" if args.ticker else ""
                return err(f"modify concept: pattern with user ID {args.uid}{ticker_msg} not found")
            patterns = [pattern]
        elif cmd["data"]:
            # Pipeline mode: validate and filter to concept patterns
            if cmd["name"] != "patterns":
                conn.close()
                return err(f"modify concept: expected pattern data, got '{cmd['name']}'")
            patterns = [p for p in cmd["data"] if p.get("type") == "concept"]
            if not patterns:
                conn.close()
                return err("modify concept: no concept patterns in piped data")
        else:
            conn.close()
            return err("modify concept: no input. Use --uid (with optional --ticker) or pipe pattern data")

        # Preview or execute
        if args.yes:
            result = _execute_modify_concepts(conn, patterns, args.name, args.pattern, args.new_uid, args.note)
        else:
            result = _preview_modify_concepts(patterns, args.name, args.pattern, args.new_uid, args.note)
        
        conn.close()
        return result
        
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.modify.run_modify_concept: {e}")


# =============================================================================
# REMOVE PATTERN HELPERS (Preview & Execute)
# =============================================================================

def _preview_remove_concepts(group_id: int, group_name: str, patterns: list[dict]) -> Result[Cmd, str]:
    """Generate preview of concept pattern removal from group."""
    preview_data = []
    for pattern in patterns:
        preview_data.append({
            "operation": "remove_concept_from_group",
            "uid": pattern.get("uid"),
            "name": pattern.get("name"),
            "group": group_name,
            "status": "preview"
        })
    return ok({"name": "modify_preview", "data": preview_data})


def _execute_remove_concepts(conn: sqlite3.Connection, group_id: int, group_name: str, patterns: list[dict]) -> Result[Cmd, str]:
    """Execute removal of concept patterns from group."""
    results = []

    try:
        cursor = conn.cursor()
        for pattern in patterns:
            pid = pattern["pid"]

            # Delete from group_concept_patterns
            cursor.execute("DELETE FROM group_concept_patterns WHERE gid = ? AND pid = ?", (group_id, pid))

            results.append({
                "operation": "remove_concept_from_group",
                "uid": pattern.get("uid"),
                "name": pattern.get("name"),
                "group": group_name,
                "status": "removed"
            })

        conn.commit()
        return ok({"name": "modify_result", "data": results})

    except Exception as e:
        conn.rollback()
        return err(f"_execute_remove_concepts: failed to remove concepts: {e}")


def _preview_remove_roles(group_id: int, group_name: str, patterns: list[dict]) -> Result[Cmd, str]:
    """Generate preview of role pattern removal from group."""
    preview_data = []
    for pattern in patterns:
        preview_data.append({
            "operation": "remove_role_from_group",
            "name": pattern.get("name"),
            "group": group_name,
            "status": "preview"})

    return ok({"name": "modify_preview", "data": preview_data})


def _execute_remove_roles(conn: sqlite3.Connection, group_id: int, group_name: str, patterns: list[dict]) -> Result[Cmd, str]:
    """Execute removal of role patterns from group."""
    results = []

    try:
        cursor = conn.cursor()
        for pattern in patterns:
            pid = pattern["pid"]

            # Delete from group_role_patterns
            cursor.execute("DELETE FROM group_role_patterns WHERE gid = ? AND pid = ?", (group_id, pid))

            results.append({
                "operation": "remove_role_from_group",
                "name": pattern.get("name"),
                "group": group_name,
                "status": "removed"})

        conn.commit()
        return ok({"name": "modify_result", "data": results})

    except Exception as e:
        conn.rollback()
        return err(f"_execute_remove_roles: failed to remove roles: {e}")


# =============================================================================
# PREVIEW FUNCTIONS
# =============================================================================

def _preview_modify_groups(groups: list[dict], new_name: str) -> Result[Cmd, str]:
    """Generate preview of group modifications."""
    preview_data = []
    for group in groups:
        preview_data.append({
            "operation": "modify_group",
            "gid": group["gid"],
            "current_name": group["group_name"],
            "new_name": new_name,
            "status": "preview"
        })
    return ok({"name": "modify_preview", "data": preview_data})


def _preview_modify_roles(patterns: list[dict], new_pattern: str = None, new_name: str = None, new_note: str = None) -> Result[Cmd, str]:
    """Generate preview of role pattern modifications."""
    preview_data = []
    for pattern in patterns:
        record = {
            "operation": "modify_role_pattern",
            "name": pattern.get("name"),
            "ticker": pattern.get("ticker", ""),
            "cik": pattern.get("cik", ""),
            "status": "preview"
        }

        if new_pattern:
            record["current_pattern"] = pattern.get("pattern", "")
            record["new_pattern"] = new_pattern

        if new_name is not None:
            record["current_name"] = pattern.get("name")
            record["new_name"] = new_name

        if new_note is not None:
            record["current_note"] = pattern.get("note", "")
            record["new_note"] = new_note

        preview_data.append(record)
    return ok({"name": "modify_preview", "data": preview_data})


def _preview_modify_concepts(patterns: list[dict], new_name: str = None, new_pattern: str = None, new_user_id: int = None, new_note: str = None) -> Result[Cmd, str]:
    """Generate preview of concept pattern modifications."""
    preview_data = []
    for pattern in patterns:
        record = {
            "operation": "modify_concept_pattern",
            "uid": pattern.get("uid"),
            "ticker": pattern.get("ticker", ""),
            "cik": pattern.get("cik", ""),
            "status": "preview"
        }

        if new_name:
            record["current_name"] = pattern.get("name", "")
            record["new_name"] = new_name

        if new_pattern:
            record["current_pattern"] = pattern.get("pattern", "")
            record["new_pattern"] = new_pattern

        if new_user_id is not None:
            record["current_uid"] = pattern.get("uid")
            record["new_uid"] = new_user_id

        if new_note is not None:
            record["current_note"] = pattern.get("note", "")
            record["new_note"] = new_note

        preview_data.append(record)

    return ok({"name": "modify_preview", "data": preview_data})


# =============================================================================
# EXECUTE FUNCTIONS
# =============================================================================

def _execute_modify_groups(conn: sqlite3.Connection, groups: list[dict], new_name: str) -> Result[Cmd, str]:
    """Execute group name modifications."""
    results = []

    for group in groups:
        group_id = group["gid"]
        old_name = group["group_name"]

        result = db.queries.groups.update_name(conn, group_id, new_name)
        if is_not_ok(result):
            return result

        results.append({
            "operation": "modify_group",
            "gid": group_id,
            "old_name": old_name,
            "new_name": new_name,
            "status": "modified"
        })

    return ok({"name": "modify_result", "data": results})


def _execute_modify_roles(conn: sqlite3.Connection, patterns: list[dict], new_pattern: str = None, new_name: str = None, new_note: str = None) -> Result[Cmd, str]:
    """Execute role pattern modifications."""
    results = []

    for pattern in patterns:
        pattern_id = pattern["pid"]
        ticker = pattern.get("ticker", "")
        cik = pattern.get("cik", "")

        result = db.queries.role_patterns.update(conn, pattern_id, new_pattern, new_name, new_note)
        if is_not_ok(result):
            return result

        record = {
            "operation": "modify_role_pattern",
            "name": pattern.get("name"),
            "ticker": ticker,
            "cik": cik,
            "status": "modified"
        }

        if new_pattern:
            record["old_pattern"] = pattern.get("pattern", "")
            record["new_pattern"] = new_pattern

        if new_name is not None:
            record["old_name"] = pattern.get("name")
            record["new_name"] = new_name

        if new_note is not None:
            record["old_note"] = pattern.get("note", "")
            record["new_note"] = new_note

        results.append(record)

    return ok({"name": "modify_result", "data": results})


def _execute_modify_concepts(conn: sqlite3.Connection, patterns: list[dict],
                             new_name: str = None, new_pattern: str = None, new_user_id: int = None, new_note: str = None) -> Result[Cmd, str]:
    """Execute concept pattern modifications."""
    results = []

    for pattern in patterns:
        pattern_id = pattern["pid"]
        ticker = pattern.get("ticker", "")
        cik = pattern.get("cik", "")

        result = db.queries.concept_patterns.update(conn, pattern_id, new_pattern, new_name, new_user_id, new_note)
        if is_not_ok(result):
            return result

        record = {
            "operation": "modify_concept_pattern",
            "uid": pattern.get("uid"),
            "ticker": ticker,
            "cik": cik,
            "status": "modified"
        }

        if new_name:
            record["old_name"] = pattern.get("name", "")
            record["new_name"] = new_name

        if new_pattern:
            record["old_pattern"] = pattern.get("pattern", "")
            record["new_pattern"] = new_pattern

        if new_user_id is not None:
            record["old_uid"] = pattern.get("uid")
            record["new_uid"] = new_user_id

        if new_note is not None:
            record["old_note"] = pattern.get("note", "")
            record["new_note"] = new_note

        results.append(record)

    return ok({"name": "modify_result", "data": results})
