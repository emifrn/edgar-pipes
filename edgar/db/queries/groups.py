"""
db.queries.groups - Group query functions

Groups organize concept patterns into logical collections for financial reporting.

Functions:
    insert_or_ignore(conn, name) -> Result[int, str]
    get_id(conn, name) -> Result[Optional[int], str]
    get(conn, gid) -> Result[dict, str]
    select(conn) -> Result[list[dict], str]
    update_name(conn, gid, new_name) -> Result[None, str]
    link_concept_pattern(conn, gid, pid) -> Result[None, str]
    count_patterns(conn, gid) -> Result[int, str]
"""
import sqlite3
from typing import Any, Optional

from edgar import db
from edgar.result import Result, ok, err, is_ok


def insert_or_ignore(conn: sqlite3.Connection, name: str) -> Result[int, str]:
    """
    Insert group if it doesn't exist and return gid.

    Args:
        conn: Database connection
        name: Group name

    Returns:
        Result containing gid (group ID) or error message
    """
    group_data = [{"name": name}]
    result = db.store.insert_or_ignore(conn, "groups", group_data)
    if result[0] is False:
        return result

    # Get the gid (whether newly inserted or existing)
    query = "SELECT gid FROM groups WHERE name = ?"
    result = db.store.select(conn, query, (name,))
    if result[0] is False:
        return result

    groups = result[1]
    if groups:
        return ok(groups[0]["gid"])
    else:
        return err(f"groups.insert_or_ignore({name}): group not found after insert")


def get_id(conn: sqlite3.Connection, name: str) -> Result[Optional[int], str]:
    """
    Get gid by name. Returns None if not found.

    Args:
        conn: Database connection
        name: Group name

    Returns:
        Result containing gid or None if not found, or error message
    """
    query = "SELECT gid FROM groups WHERE name = ?"
    result = db.store.select(conn, query, (name,))
    if is_ok(result):
        groups = result[1]
        return ok(groups[0]["gid"] if groups else None)
    else:
        return result


def get(conn: sqlite3.Connection, gid: int) -> Result[dict, str]:
    """
    Get group by ID.

    Args:
        conn: Database connection
        gid: Group ID

    Returns:
        Result containing group dict with keys: gid, group_name
    """
    query = "SELECT gid, name as group_name FROM groups WHERE gid = ?"
    result = db.store.select(conn, query, (gid,))
    if is_ok(result):
        groups = result[1]
        if groups:
            return ok(groups[0])
        else:
            return err(f"groups.get: group ID {gid} not found")
    return result


def select(conn: sqlite3.Connection) -> Result[list[dict[str, Any]], str]:
    """
    Get all groups ordered by name.

    Args:
        conn: Database connection

    Returns:
        Result containing list of group dicts with keys: gid, group_name
    """
    query = "SELECT gid, name as group_name FROM groups ORDER BY name"
    return db.store.select(conn, query)


def update_name(conn: sqlite3.Connection, gid: int, new_name: str) -> Result[None, str]:
    """
    Update group name.

    Args:
        conn: Database connection
        gid: Group ID
        new_name: New group name

    Returns:
        Result containing None on success or error message
    """
    try:
        query = "UPDATE groups SET name = ? WHERE gid = ?"
        cursor = conn.execute(query, (new_name, gid))
        conn.commit()
        if cursor.rowcount == 0:
            return err(f"groups.update_name: no group with ID {gid}")
        cursor.close()
        return ok(None)
    except sqlite3.Error as e:
        return err(f"groups.update_name: sqlite error: {e}")


def link_concept_pattern(conn: sqlite3.Connection, gid: int, pid: int) -> Result[None, str]:
    """
    Link concept pattern to group (idempotent).

    Creates entry in group_concept_patterns junction table.

    Args:
        conn: Database connection
        gid: Group ID
        pid: Pattern ID (concept pattern)

    Returns:
        Result containing None on success or error message
    """
    link_data = [{"gid": gid, "pid": pid}]
    result = db.store.insert_or_ignore(conn, "group_concept_patterns", link_data)
    if is_ok(result):
        return ok(None)
    else:
        return result


def count_patterns(conn: sqlite3.Connection, gid: int) -> Result[int, str]:
    """
    Count concept patterns linked to a group.

    Args:
        conn: Database connection
        gid: Group ID

    Returns:
        Result containing pattern count or error message
    """
    query = "SELECT COUNT(*) FROM group_concept_patterns WHERE gid = ?"
    result = db.store.select(conn, query, (gid,))
    if is_ok(result):
        count = result[1][0]["COUNT(*)"]
        return ok(count)
    else:
        return result
