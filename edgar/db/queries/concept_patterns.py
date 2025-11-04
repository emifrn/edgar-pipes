"""
Concept pattern queries module.

Functions for managing concept patterns - regex patterns used to match
XBRL concept/tag names for extracting structured data from filings.
"""
import sqlite3
from typing import Any, Optional

from edgar import db
from edgar.result import Result, ok, err, is_ok, is_not_ok


def get_with_entity(conn: sqlite3.Connection, cik: Optional[str], uid: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get concept pattern by user ID with entity details.

    Returns pattern with ticker and company name joined from entities table.
    If cik is provided, filters to that specific CIK.
    """
    query = """
        SELECT  cp.pid,
                cp.cik,
                cp.pattern,
                cp.uid,
                cp.name,
                e.ticker,
                e.name as company_name
        FROM concept_patterns cp
        JOIN entities e ON cp.cik = e.cik
        WHERE cp.uid = ?
    """
    params = [uid]

    if cik is not None:
        query += " AND cp.cik = ?"
        params.append(cik)

    result = db.store.select(conn, query, tuple(params))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def get_by_uid(conn: sqlite3.Connection, cik: str, uid: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get concept pattern by CIK and user ID.
    """
    query = "SELECT pid, cik, pattern, uid, name FROM concept_patterns WHERE cik = ? AND uid = ?"
    result = db.store.select(conn, query, (cik, uid))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def get_by_name(conn: sqlite3.Connection, cik: str, name: str) -> Result[Optional[dict[str, Any]], str]:
    """
    Get concept pattern by CIK and name.
    """
    query = "SELECT pid, cik, pattern, uid, name FROM concept_patterns WHERE cik = ? AND name = ?"
    result = db.store.select(conn, query, (cik, name))
    if is_ok(result):
        patterns = result[1]
        return ok(patterns[0] if patterns else None)
    else:
        return result


def insert(conn: sqlite3.Connection, cik: str, name: str, pattern: str, uid: Optional[int] = None) -> Result[int, str]:
    """
    Insert concept pattern with UID (without OR IGNORE).

    Raises error if pattern already exists.
    Returns pattern ID.
    """
    try:
        query = "INSERT INTO concept_patterns (cik, name, pattern, uid) VALUES (?, ?, ?, ?)"
        cursor = conn.execute(query, (cik, name, pattern, uid))
        pid = cursor.lastrowid
        conn.commit()
        cursor.close()
        return ok(pid)
    except sqlite3.IntegrityError as e:
        return err(f"queries.concept_patterns.insert: pattern already exists: {e}")
    except sqlite3.Error as e:
        return err(f"queries.concept_patterns.insert: sqlite error: {e}")


def select_by_group(conn: sqlite3.Connection, gid: int, cik: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get concept patterns for a group.

    If cik is provided, only return patterns for that CIK.
    """
    query = """
        SELECT  cp.pid,
                cp.cik,
                cp.pattern,
                cp.uid,
                cp.name
        FROM concept_patterns cp
        JOIN group_concept_patterns gcp ON cp.pid = gcp.pid
        WHERE gcp.gid = ?
    """
    params = [gid]

    if cik is not None:
        query += " AND cp.cik = ?"
        params.append(cik)

    return db.store.select(conn, query, tuple(params))


def select(conn: sqlite3.Connection, group_name: Optional[str] = None, cik: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get concept patterns with optional filters. Includes group name in results.

    Uses LEFT JOIN to include patterns not yet linked to any group.
    When multiple groups are linked to one pattern, they're concatenated with commas.

    Args:
        group_name: Filter to specific group (None = all groups)
        cik: Filter to specific company (None = all companies)

    Returns patterns with empty group_name for unlinked patterns.
    """
    base_query = """
        SELECT cp.pid,
               cp.cik,
               cp.name,
               cp.pattern,
               cp.uid,
               COALESCE(GROUP_CONCAT(DISTINCT g.name), '') as group_name
        FROM concept_patterns cp
        LEFT JOIN group_concept_patterns gcp ON cp.pid = gcp.pid
        LEFT JOIN groups g ON gcp.gid = g.gid
        """

    where_clauses = []
    params = []

    if group_name:
        where_clauses.append("g.name = ?")
        params.append(group_name)

    if cik:
        where_clauses.append("cp.cik = ?")
        params.append(cik)

    if where_clauses:
        query = base_query + " WHERE " + " AND ".join(where_clauses)
    else:
        query = base_query

    query += " GROUP BY cp.pid, cp.cik, cp.name, cp.pattern, cp.uid"

    return db.store.select(conn, query, tuple(params))


def update(conn: sqlite3.Connection, pid: int, pattern: Optional[str] = None, name: Optional[str] = None, uid: Optional[int] = None) -> Result[int, str]:
    """
    Update concept pattern.

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

    if uid is not None:
        updates.append("uid = ?")
        params.append(uid)

    if not updates:
        return ok(0)  # Nothing to update

    params.append(pid)
    query = f"UPDATE concept_patterns SET {', '.join(updates)} WHERE pid = ?"

    try:
        cursor = conn.execute(query, tuple(params))
        count = cursor.rowcount
        conn.commit()
        cursor.close()
        return ok(count)
    except sqlite3.Error as e:
        return err(f"queries.concept_patterns.update({pid}) sqlite error: {e}")
