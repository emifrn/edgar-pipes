"""
CLI: modify

Modify groups and patterns with preview/execute workflow.
Supports both standalone (--uid for patterns) and pipeline modes.
"""

import re
import sys
import sqlite3

# Local modules
from edgar import db
from edgar import db
from edgar.cli.shared import Cmd
from edgar.result import Result, ok, err, is_ok, is_not_ok


def add_arguments(subparsers):
    """Add modify command with subcommands."""
    
    parser_modify = subparsers.add_parser("modify", help="modify groups and patterns")
    modify_subparsers = parser_modify.add_subparsers(dest='modify_cmd', help='modify commands')
    
    # modify group
    parser_group = modify_subparsers.add_parser("group", help="modify group name")
    parser_group.add_argument("--gid", type=int, help="group ID (for standalone mode)")
    parser_group.add_argument("-n", "--name", required=True, help="new group name")
    parser_group.add_argument("-y", "--yes", action="store_true", help="execute modification (default: preview)")
    parser_group.set_defaults(func=run)
    
    # modify role
    parser_role = modify_subparsers.add_parser("role", help="modify role pattern regex")
    parser_role.add_argument("--name", "-n", help="pattern name to select pattern (for standalone mode)")
    parser_role.add_argument("-t", "--ticker", help="ticker to narrow down pattern selection")
    parser_role.add_argument("--pattern", help="new regex pattern")
    parser_role.add_argument("--new-name", dest="new_name", help="new pattern name")
    parser_role.add_argument("--note", help="new or updated note describing the pattern rationale")
    parser_role.add_argument("-y", "--yes", action="store_true", help="execute modification (default: preview)")
    parser_role.set_defaults(func=run)

    # modify concept
    parser_concept = modify_subparsers.add_parser("concept", help="modify concept name and/or pattern")
    parser_concept.add_argument("--uid", "-u", type=int, help="user ID to select pattern (for standalone mode)")
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
    """Modify group names with preview/execute workflow."""
    
    try:
        conn = sqlite3.connect(args.db)
        
        result = db.store.init(conn)
        if is_not_ok(result):
            conn.close()
            return result
        
        # Collect groups to modify
        if args.gid:
            # Standalone mode: fetch group by ID
            result = db.queries.groups.get(conn, args.gid)
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
            return err("modify group: no input. Use --gid or pipe group data")
        
        # Preview or execute
        if args.yes:
            result = _execute_modify_groups(conn, groups, args.name)
        else:
            result = _preview_modify_groups(groups, args.name)
        
        conn.close()
        return result
        
    except Exception as e:
        if 'conn' in locals():
            conn.close()
        return err(f"cli.modify.run_modify_group: {e}")


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
        conn = sqlite3.connect(args.db)
        
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
        conn = sqlite3.connect(args.db)
        
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
