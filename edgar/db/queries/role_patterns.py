"""
Role pattern queries module.

Functions for managing role patterns - regex patterns used to match
XBRL role names for extracting structured data from filings.

Functions:
    get(conn, cik, name) -> Result[dict | None, str]
    get_with_entity(conn, cik, name) -> Result[dict | None, str]
    select(conn, group_name=None, cik=None) -> Result[list[dict], str]
    select_by_group(conn, gid, cik=None) -> Result[list[dict], str]
    insert(conn, cik, name, pattern) -> Result[int, str]
    update(conn, pid, pattern=None, name=None) -> Result[int, str]
    match_groups(conn, cik) -> Result[dict[str, list[str]], str]
    match_groups_for_filing(conn, cik, access_no) -> Result[dict[str, list[str]], str]
"""
import re
import sqlite3
from typing import Any, Optional

from edgar import db
from edgar.result import Result, ok, err, is_ok, is_not_ok


def get_with_entity(conn: sqlite3.Connection, cik: Optional[str], name: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get role pattern by name with entity details.

    Returns pattern with ticker and company name joined from entities table.
    If cik is provided, filters to that specific CIK.
    """
    query = """
        SELECT  rp.pid,
                rp.cik,
                rp.pattern,
                rp.name,
                rp.note,
                e.ticker,
                e.name as company_name
        FROM role_patterns rp
        JOIN entities e ON rp.cik = e.cik
        WHERE rp.name = ?
    """
    params = [name]

    if cik is not None:
        query += " AND rp.cik = ?"
        params.append(cik)

    result = db.store.select(conn, query, tuple(params))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def get(conn: sqlite3.Connection, cik: str, name: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get role pattern by CIK and name.
    """
    query = """
        SELECT pid,
               cik,
               pattern,
               name,
               note
        FROM role_patterns
        WHERE cik = ? AND name = ?
        """
    result = db.store.select(conn, query, (cik, name))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def select_by_group(conn: sqlite3.Connection, gid: int, cik: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get role patterns for a group.

    If cik is provided, only return patterns for that CIK.
    """
    query = """
        SELECT  rp.pid,
                rp.cik,
                rp.name,
                rp.pattern,
                rp.note
        FROM role_patterns rp
        JOIN group_role_patterns grp ON rp.pid = grp.pid
        WHERE grp.gid = ?
    """
    params = [gid]

    if cik is not None:
        query += " AND rp.cik = ?"
        params.append(cik)

    return db.store.select(conn, query, tuple(params))


def select(conn: sqlite3.Connection, group_name: Optional[str] = None, cik: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get role patterns with optional filters. Includes group name in results.

    Uses LEFT JOIN to include patterns not yet linked to any group.
    When multiple groups are linked to one pattern, they're concatenated with commas.

    Args:
        group_name: Filter to specific group (None = all groups)
        cik: Filter to specific company (None = all companies)

    Returns patterns with empty group_name for unlinked patterns.
    """
    base_query = """
        SELECT rp.pid,
               rp.cik,
               rp.name,
               rp.pattern,
               rp.note,
               COALESCE(GROUP_CONCAT(DISTINCT g.name), '') as group_name
        FROM role_patterns rp
        LEFT JOIN group_role_patterns grp ON rp.pid = grp.pid
        LEFT JOIN groups g ON grp.gid = g.gid
        """
    where_clauses = []
    params = []

    if group_name:
        where_clauses.append("g.name = ?")
        params.append(group_name)

    if cik:
        where_clauses.append("rp.cik = ?")
        params.append(cik)

    if where_clauses:
        query = base_query + " WHERE " + " AND ".join(where_clauses)
    else:
        query = base_query

    query += " GROUP BY rp.pid, rp.cik, rp.name, rp.pattern, rp.note"

    return db.store.select(conn, query, tuple(params))


def insert(conn: sqlite3.Connection, cik: str, name: str, pattern: str, note: Optional[str] = None) -> Result[int, str]:
    """
    Insert role pattern (without OR IGNORE).

    Raises error if pattern already exists.
    Returns pattern ID.
    """
    try:
        query = "INSERT INTO role_patterns (cik, name, pattern, note) VALUES (?, ?, ?, ?)"
        cursor = conn.execute(query, (cik, name, pattern, note))
        pid = cursor.lastrowid
        conn.commit()
        cursor.close()
        return ok(pid)
    except sqlite3.IntegrityError as e:
        return err(f"queries.role_patterns.insert: pattern already exists: {e}")
    except sqlite3.Error as e:
        return err(f"queries.role_patterns.insert: sqlite error: {e}")


def update(conn: sqlite3.Connection, pid: int, pattern: Optional[str] = None, name: Optional[str] = None, note: Optional[str] = None) -> Result[int, str]:
    """
    Update role pattern.

    Only updates fields that are provided (not None).
    Returns number of rows updated.
    """
    updates = []
    params = []

    if pattern is not None:
        updates.append("pattern = ?")
        params.append(pattern)

    if name is not None:
        updates.append("name = ?")
        params.append(name)

    if note is not None:
        updates.append("note = ?")
        params.append(note)

    if not updates:
        return ok(0)  # Nothing to update

    params.append(pid)
    query = f"UPDATE role_patterns SET {', '.join(updates)} WHERE pid = ?"

    try:
        cursor = conn.execute(query, tuple(params))
        count = cursor.rowcount
        conn.commit()
        cursor.close()
        return ok(count)
    except sqlite3.Error as e:
        return err(f"queries.role_patterns.update({pid}) sqlite error: {e}")


def match_groups(conn: sqlite3.Connection, cik: str) -> Result[dict[str, list[str]], str]:
    """
    Match role patterns against actual role names for a CIK across all groups.

    Returns dict mapping group_name -> list of matching role names.
    """
    # Get all groups
    result = db.queries.groups.select(conn)
    if is_not_ok(result):
        return result

    groups = result[1]

    # Get all role names for this CIK
    result = db.queries.roles.select_by_entity(conn, cik)
    if is_not_ok(result):
        return result

    role_names = result[1]

    # For each group, get its patterns and match against role names
    group_matches = {}

    for group in groups:
        gid = group["gid"]
        group_name = group["group_name"]

        # Get role patterns for this group
        result = select_by_group(conn, gid, cik)
        if is_not_ok(result):
            return result

        patterns = result[1]

        # Match patterns against role names
        matched_roles = []
        for pattern_row in patterns:
            pattern = pattern_row["pattern"]
            try:
                regex = re.compile(pattern)
                for role_name in role_names:
                    if regex.search(role_name) and role_name not in matched_roles:
                        matched_roles.append(role_name)
            except re.error:
                continue  # Skip invalid regex patterns

        if matched_roles:
            group_matches[group_name] = matched_roles

    return ok(group_matches)


def match_groups_for_filing(conn: sqlite3.Connection, cik: str, access_no: str) -> Result[dict[str, list[str]], str]:
    """
    Match role patterns against actual role names for a specific filing across all groups.

    More efficient than match_groups() when processing individual filings, as it only
    checks roles that actually exist in the filing.

    Args:
        conn: Database connection
        cik: Company CIK (needed to get role patterns)
        access_no: Filing accession number

    Returns:
        Result containing dict mapping group_name -> list of matching role names
    """
    # Get all groups
    result = db.queries.groups.select(conn)
    if is_not_ok(result):
        return result

    groups = result[1]

    # Get role names for this specific filing
    result = db.queries.roles.select_by_filing(conn, access_no)
    if is_not_ok(result):
        return result

    role_names = result[1]

    # For each group, get its patterns and match against role names
    group_matches = {}

    for group in groups:
        gid = group["gid"]
        group_name = group["group_name"]

        # Get role patterns for this group
        result = select_by_group(conn, gid, cik)
        if is_not_ok(result):
            return result

        patterns = result[1]

        # Match patterns against role names
        matched_roles = []
        for pattern_row in patterns:
            pattern = pattern_row["pattern"]
            try:
                regex = re.compile(pattern)
                for role_name in role_names:
                    if regex.search(role_name) and role_name not in matched_roles:
                        matched_roles.append(role_name)
            except re.error:
                continue  # Skip invalid regex patterns

        if matched_roles:
            group_matches[group_name] = matched_roles

    return ok(group_matches)
