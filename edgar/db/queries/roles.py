"""
db.queries.roles - Role query functions

Roles represent the different sections/statements in XBRL filings
(e.g., Balance Sheet, Income Statement, etc.)

Functions:
    insert_or_ignore(conn, access_no, role_name) -> Result[int, str]
    select_by_filing(conn, access_no) -> Result[list[str], str]
    select_by_entity(conn, cik) -> Result[list[str], str]
    select_with_entity(conn, access_nos, pattern=None) -> Result[list[dict], str]
    count(conn, access_no) -> Result[int, str]
"""

import re
import sqlite3
from typing import Any, Optional

# Local modules
from edgar import db
from edgar.result import Result, ok, err, is_ok, is_not_ok


def insert_or_ignore(conn: sqlite3.Connection, access_no: str, role_name: str) -> Result[int, str]:
    """
    Insert role for a filing if it doesn't exist, return rid.

    Args:
        conn: Database connection
        access_no: Filing accession number
        role_name: Name of the role/statement

    Returns:
        Result containing rid (role ID) or error message
    """
    # First try to insert
    data = [{"access_no": access_no, "name": role_name}]
    result = db.store.insert_or_ignore(conn, "roles", data)
    if is_not_ok(result):
        return result

    # Get the rid (whether newly inserted or existing)
    query = "SELECT rid FROM roles WHERE access_no = ? AND name = ?"
    result = db.store.select(conn, query, (access_no, role_name))
    if is_not_ok(result):
        return result

    if result[1]:
        return ok(result[1][0]["rid"])
    else:
        return err(f"roles.insert_or_ignore: role not found after insert")


def select_by_filing(conn: sqlite3.Connection, access_no: str) -> Result[list[str], str]:
    """
    Get role names for a filing.

    Args:
        conn: Database connection
        access_no: Filing accession number

    Returns:
        Result containing list of role names or error message
    """
    query = "SELECT name FROM roles WHERE access_no = ? ORDER BY name"
    result = db.store.select(conn, query, (access_no,))
    if is_ok(result):
        roles = result[1]
        return ok([role["name"] for role in roles])
    else:
        return result


def select_with_entity(conn: sqlite3.Connection,
                       access_nos: list[str],
                       pattern: Optional[str] = None) -> Result[list[dict[str, Any]], str]:
    """
    Get role information with entity details for specified filings.
    Returns role records with full entity and filing context joined from entities table.

    Args:
        conn: Database connection
        access_nos: List of filing accession numbers
        pattern: Optional regex pattern to filter role names

    Returns:
        Result containing list of role dictionaries with keys:
        - name (entity name)
        - ticker
        - cik
        - access_no
        - filing_date
        - form_type
        - role_name
    """
    if not access_nos:
        return ok([])

    placeholders = ",".join("?" * len(access_nos))
    query = f"""
        SELECT  e.name,
                e.ticker,
                e.cik,
                f.access_no,
                f.filing_date,
                f.form_type,
                fr.name as role_name
        FROM roles fr
        JOIN filings f ON fr.access_no = f.access_no
        JOIN entities e ON f.cik = e.cik
        WHERE f.access_no IN ({placeholders})
        ORDER BY f.filing_date DESC, e.ticker, fr.name
        """

    result = db.store.select(conn, query, tuple(access_nos))
    if is_not_ok(result):
        return result

    roles = result[1]

    if pattern:
        try:
            rexp = re.compile(pattern)
            filtered_roles = [role for role in roles if rexp.search(role['role_name'])]
            return ok(filtered_roles)
        except re.error as e:
            return err(f"roles.select_with_entity: invalid regex pattern '{pattern}': {e}")

    return ok(roles)


def select_by_entity(conn: sqlite3.Connection, cik: str) -> Result[list[str], str]:
    """
    Get all unique role names for an entity across all their filings.

    Args:
        conn: Database connection
        cik: Company CIK

    Returns:
        Result containing list of unique role names or error message
    """
    query = """
        SELECT DISTINCT r.name
        FROM roles r
        JOIN filings f ON r.access_no = f.access_no
        WHERE f.cik = ?
        ORDER BY r.name
    """
    result = db.store.select(conn, query, (cik,))
    if is_ok(result):
        roles = result[1]
        return ok([role["name"] for role in roles])
    else:
        return result


def count(conn: sqlite3.Connection, access_no: str) -> Result[int, str]:
    """
    Get count of roles for a filing.

    Args:
        conn: Database connection
        access_no: Filing accession number

    Returns:
        Result containing role count or error message
    """
    query = "SELECT COUNT(*) as count FROM roles WHERE access_no = ?"
    result = db.store.select(conn, query, (access_no,))
    if is_ok(result):
        rows = result[1]
        return ok(rows[0]["count"] if rows else 0)
    else:
        return result
